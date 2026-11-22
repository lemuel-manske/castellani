import type { ConfirmChannel, ConsumeMessage } from "amqplib";
import type { ArtifactReference } from "../../../ports/artifacts.js";
import type {
  CompensationDecision,
  PublicationIdentity,
} from "../../../domain.js";
import { PublicationConflictError } from "../../../domain/publication.js";
import type { PublicationEvent } from "../../../application/processPublicationEvent.js";

const EVENTS_EXCHANGE = "castellani.events";
const PUBLICATION_ROUTING_KEYS = [
  "ArchivePublicationDecided",
  "ArchivePublished",
  "ArchiveCompensationDecided",
  "CrawlCompleted",
] as const;
const PUBLICATION_QUEUE = "castellani.search.publication.v1";
const RETRY_EXCHANGE = "castellani.search.publication.retry";
const RETRY_QUEUE = "castellani.search.publication.retry.v1";
const DEAD_LETTER_EXCHANGE = "castellani.search.publication.dead";
const DEAD_LETTER_QUEUE = "castellani.search.publication.dead.v1";
const MAX_DELIVERY_RETRIES = 5;
const RETRY_DELAY_MILLISECONDS = 5000;

interface PublicationConsumerTopology {
  eventsExchange: string;
  routingKeys: readonly string[];
  queue: string;
  retryExchange: string;
  retryQueue: string;
  deadLetterExchange: string;
  deadLetterQueue: string;
}

const DEFAULT_TOPOLOGY: PublicationConsumerTopology = {
  eventsExchange: EVENTS_EXCHANGE,
  routingKeys: PUBLICATION_ROUTING_KEYS,
  queue: PUBLICATION_QUEUE,
  retryExchange: RETRY_EXCHANGE,
  retryQueue: RETRY_QUEUE,
  deadLetterExchange: DEAD_LETTER_EXCHANGE,
  deadLetterQueue: DEAD_LETTER_QUEUE,
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
function nonEmpty(value: unknown): value is string {
  return typeof value === "string" && value.length > 0;
}
function isIdentity(value: unknown): value is PublicationIdentity {
  return (
    isRecord(value) &&
    nonEmpty(value.archiveId) &&
    typeof value.decisionVersion === "number" &&
    Number.isSafeInteger(value.decisionVersion) &&
    value.decisionVersion >= 1 &&
    nonEmpty(value.packageDigest)
  );
}
function isCompensation(value: unknown): value is CompensationDecision {
  return (
    isRecord(value) &&
    nonEmpty(value.archiveId) &&
    typeof value.decisionVersion === "number" &&
    Number.isSafeInteger(value.decisionVersion) &&
    value.decisionVersion >= 1 &&
    nonEmpty(value.reasonCode)
  );
}
function isArtifact(value: unknown): value is ArtifactReference {
  return (
    isRecord(value) &&
    nonEmpty(value.bucket) &&
    nonEmpty(value.key) &&
    nonEmpty(value.sha256) &&
    /^[a-f0-9]{64}$/.test(value.sha256) &&
    typeof value.sizeBytes === "number" &&
    Number.isSafeInteger(value.sizeBytes) &&
    value.sizeBytes >= 0 &&
    (value.versionId === undefined || nonEmpty(value.versionId))
  );
}
function parsePublicationEvent(body: Uint8Array): PublicationEvent | null {
  let envelope: unknown;

  try {
    envelope = JSON.parse(Buffer.from(body).toString("utf8")) as unknown;
  } catch {
    return null;
  }

  if (
    !isRecord(envelope) ||
    !nonEmpty(envelope.messageId) ||
    !nonEmpty(envelope.correlationId) ||
    !nonEmpty(envelope.occurredAt) ||
    !Number.isFinite(Date.parse(envelope.occurredAt)) ||
    envelope.version !== 1 ||
    !isRecord(envelope.payload) ||
    envelope.correlationId !== envelope.payload.archiveId
  )
    return null;

  const payload = envelope.payload;

  if (
    envelope.type === "ArchivePublicationDecided" ||
    envelope.type === "ArchivePublished"
  ) {
    return isIdentity(payload) ? { type: envelope.type, payload } : null;
  }

  if (envelope.type === "ArchiveCompensationDecided") {
    return isCompensation(payload) ? { type: envelope.type, payload } : null;
  }

  if (envelope.type === "CrawlCompleted") {
    return nonEmpty(payload.archiveId) &&
      nonEmpty(payload.manifestDigest) &&
      isArtifact(payload.manifest)
      ? {
          type: "CrawlCompleted",
          payload: {
            archiveId: payload.archiveId,
            manifestDigest: payload.manifestDigest,
            manifest: payload.manifest,
          },
        }
      : null;
  }

  return null;
}
function retryCount(message: ConsumeMessage, queue: string): number {
  const deaths: unknown = message.properties.headers?.["x-death"];

  if (!Array.isArray(deaths)) return 0;

  const death = (deaths as unknown[]).find(
    (entry: unknown) => isRecord(entry) && entry.queue === queue,
  );

  if (!isRecord(death)) return 0;

  const count = death.count;

  return typeof count === "number"
    ? count
    : typeof count === "bigint"
      ? Number(count)
      : 0;
}
function publishDeadLetter(
  channel: ConfirmChannel,
  topology: PublicationConsumerTopology,
  message: ConsumeMessage,
): Promise<void> {
  return new Promise((resolve, reject) =>
    channel.publish(
      topology.deadLetterExchange,
      "",
      message.content,
      {
        contentType:
          typeof message.properties.contentType === "string"
            ? message.properties.contentType
            : "application/json",
        messageId: message.properties.messageId as string | undefined,
        correlationId: message.properties.correlationId as string | undefined,
        headers: message.properties.headers as
          Record<string, unknown> | undefined,
        persistent: true,
      },
      (error) => {
        if (error) {
          reject(error instanceof Error ? error : new Error(String(error)));
          return;
        }

        resolve();
      },
    ),
  );
}
async function handleMessage(
  channel: ConfirmChannel,
  message: ConsumeMessage | null,
  handle: (event: PublicationEvent) => Promise<void>,
  topology: PublicationConsumerTopology,
): Promise<void> {
  if (message === null) return;

  const event = parsePublicationEvent(message.content);

  if (
    event === null ||
    retryCount(message, topology.retryQueue) >= MAX_DELIVERY_RETRIES
  ) {
    try {
      await publishDeadLetter(channel, topology, message);
      channel.ack(message);
    } catch {
      channel.nack(message, false, true);
    }
    return;
  }

  try {
    await handle(event);
    channel.ack(message);
  } catch (error) {
    if (error instanceof PublicationConflictError) {
      try {
        await publishDeadLetter(channel, topology, message);
        channel.ack(message);
      } catch {
        channel.nack(message, false, true);
      }
      return;
    }

    channel.nack(message, false, false);
  }
}
async function startPublicationConsumer(
  channel: ConfirmChannel,
  handle: (event: PublicationEvent) => Promise<void>,
  topology: PublicationConsumerTopology = DEFAULT_TOPOLOGY,
): Promise<void> {
  await channel.assertExchange(topology.eventsExchange, "topic", {
    durable: true,
  });
  await channel.assertExchange(topology.retryExchange, "direct", {
    durable: true,
  });
  await channel.assertExchange(topology.deadLetterExchange, "fanout", {
    durable: true,
  });
  await channel.assertQueue(topology.deadLetterQueue, { durable: true });
  await channel.bindQueue(
    topology.deadLetterQueue,
    topology.deadLetterExchange,
    "",
  );
  await channel.assertQueue(topology.retryQueue, {
    durable: true,
    arguments: {
      "x-message-ttl": RETRY_DELAY_MILLISECONDS,
      "x-dead-letter-exchange": topology.eventsExchange,
    },
  });
  await Promise.all(
    topology.routingKeys.map((key) =>
      channel.bindQueue(topology.retryQueue, topology.retryExchange, key),
    ),
  );
  await channel.assertQueue(topology.queue, {
    durable: true,
    arguments: { "x-dead-letter-exchange": topology.retryExchange },
  });
  await Promise.all(
    topology.routingKeys.map((key) =>
      channel.bindQueue(topology.queue, topology.eventsExchange, key),
    ),
  );
  await channel.prefetch(1);
  await channel.consume(topology.queue, (message) => {
    void handleMessage(channel, message, handle, topology);
  });
}
export {
  DEAD_LETTER_EXCHANGE,
  DEAD_LETTER_QUEUE,
  EVENTS_EXCHANGE,
  MAX_DELIVERY_RETRIES,
  PUBLICATION_QUEUE,
  PUBLICATION_ROUTING_KEYS,
  RETRY_EXCHANGE,
  RETRY_QUEUE,
  parsePublicationEvent,
  startPublicationConsumer,
};
export type { PublicationConsumerTopology };
