import type { ConfirmChannel, ConsumeMessage } from "amqplib";
import { isArtifactReference } from "../../../ports/artifacts.js";
import {
  isCompensationDecision,
  isPublicationIdentity,
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

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
function nonEmpty(value: unknown): value is string {
  return typeof value === "string" && value.length > 0;
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
    return isPublicationIdentity(payload) ? { type: envelope.type, payload } : null;
  }

  if (envelope.type === "ArchiveCompensationDecided") {
    return isCompensationDecision(payload) ? { type: envelope.type, payload } : null;
  }

  if (envelope.type === "CrawlCompleted") {
    return nonEmpty(payload.archiveId) &&
      nonEmpty(payload.manifestDigest) &&
      isArtifactReference(payload.manifest)
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
function retryCount(message: ConsumeMessage): number {
  const deaths: unknown = message.properties.headers?.["x-death"];

  if (!Array.isArray(deaths)) return 0;

  const death = (deaths as unknown[]).find(
    (entry: unknown) => isRecord(entry) && entry.queue === RETRY_QUEUE,
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
  message: ConsumeMessage,
): Promise<void> {
  return new Promise((resolve, reject) =>
    channel.publish(
      DEAD_LETTER_EXCHANGE,
      "",
      message.content,
      {
        contentType:
          typeof message.properties.contentType === "string"
            ? message.properties.contentType
            : "application/json",
        ...(typeof message.properties.messageId === "string"
          ? { messageId: message.properties.messageId }
          : {}),
        ...(typeof message.properties.correlationId === "string"
          ? { correlationId: message.properties.correlationId }
          : {}),
        ...(message.properties.headers === undefined
          ? {}
          : { headers: message.properties.headers }),
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
): Promise<void> {
  if (message === null) return;

  const event = parsePublicationEvent(message.content);

  if (
    event === null ||
    retryCount(message) >= MAX_DELIVERY_RETRIES
  ) {
    try {
      await publishDeadLetter(channel, message);
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
        await publishDeadLetter(channel, message);
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
): Promise<void> {
  await channel.assertExchange(EVENTS_EXCHANGE, "topic", {
    durable: true,
  });
  await channel.assertExchange(RETRY_EXCHANGE, "direct", {
    durable: true,
  });
  await channel.assertExchange(DEAD_LETTER_EXCHANGE, "fanout", {
    durable: true,
  });
  await channel.assertQueue(DEAD_LETTER_QUEUE, { durable: true });
  await channel.bindQueue(
    DEAD_LETTER_QUEUE,
    DEAD_LETTER_EXCHANGE,
    "",
  );
  await channel.assertQueue(RETRY_QUEUE, {
    durable: true,
    arguments: {
      "x-message-ttl": RETRY_DELAY_MILLISECONDS,
      "x-dead-letter-exchange": EVENTS_EXCHANGE,
    },
  });
  await Promise.all(
    PUBLICATION_ROUTING_KEYS.map((key) =>
      channel.bindQueue(RETRY_QUEUE, RETRY_EXCHANGE, key),
    ),
  );
  await channel.assertQueue(PUBLICATION_QUEUE, {
    durable: true,
    arguments: { "x-dead-letter-exchange": RETRY_EXCHANGE },
  });
  await Promise.all(
    PUBLICATION_ROUTING_KEYS.map((key) =>
      channel.bindQueue(PUBLICATION_QUEUE, EVENTS_EXCHANGE, key),
    ),
  );
  await channel.prefetch(1);
  await channel.consume(PUBLICATION_QUEUE, (message) => {
    void handleMessage(channel, message, handle);
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
