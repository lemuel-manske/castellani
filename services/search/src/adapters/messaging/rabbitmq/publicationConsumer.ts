import type { ConfirmChannel, ConsumeMessage } from "amqplib";
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
] as const;
const PUBLICATION_QUEUE = "castellani.search.publication.v1";
const RETRY_EXCHANGE = "castellani.search.publication.retry";
const RETRY_QUEUE = "castellani.search.publication.retry.v1";
const DEAD_LETTER_EXCHANGE = "castellani.search.publication.dead";
const DEAD_LETTER_QUEUE = "castellani.search.publication.dead.v1";
const MAX_DELIVERY_RETRIES = 5;
const RETRY_DELAY_MILLISECONDS = 5_000;

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

function isNonEmptyString(value: unknown): value is string {
  return typeof value === "string" && value.length > 0;
}

function isPublicationIdentity(value: unknown): value is PublicationIdentity {
  return (
    isRecord(value) &&
    isNonEmptyString(value.archiveId) &&
    Number.isSafeInteger(value.decisionVersion) &&
    Number(value.decisionVersion) >= 1 &&
    isNonEmptyString(value.packageDigest)
  );
}

function isCompensationDecision(
  value: unknown,
): value is CompensationDecision {
  return (
    isRecord(value) &&
    isNonEmptyString(value.archiveId) &&
    Number.isSafeInteger(value.decisionVersion) &&
    Number(value.decisionVersion) >= 1 &&
    isNonEmptyString(value.reasonCode)
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
    !isNonEmptyString(envelope.messageId) ||
    !isNonEmptyString(envelope.correlationId) ||
    !isNonEmptyString(envelope.occurredAt) ||
    !Number.isFinite(Date.parse(envelope.occurredAt)) ||
    envelope.version !== 1 ||
    !isRecord(envelope.payload) ||
    envelope.correlationId !== envelope.payload.archiveId
  ) {
    return null;
  }

  if (
    envelope.type === "ArchivePublicationDecided" ||
    envelope.type === "ArchivePublished"
  ) {
    return isPublicationIdentity(envelope.payload)
      ? { type: envelope.type, payload: envelope.payload }
      : null;
  }

  if (envelope.type === "ArchiveCompensationDecided") {
    return isCompensationDecision(envelope.payload)
      ? { type: envelope.type, payload: envelope.payload }
      : null;
  }

  return null;
}

function retryCount(message: ConsumeMessage, retryQueue: string): number {
  const deaths = message.properties.headers?.["x-death"];

  if (!Array.isArray(deaths)) {
    return 0;
  }

  const retryDeath = deaths.find(
    (death) => isRecord(death) && death.queue === retryQueue,
  );

  if (!isRecord(retryDeath)) {
    return 0;
  }

  const count = retryDeath.count;
  return typeof count === "number" || typeof count === "bigint"
    ? Number(count)
    : 0;
}

function publishDeadLetter(
  channel: ConfirmChannel,
  topology: PublicationConsumerTopology,
  message: ConsumeMessage,
): Promise<void> {
  return new Promise((resolve, reject) => {
    channel.publish(
      topology.deadLetterExchange,
      "",
      message.content,
      {
        contentType: message.properties.contentType ?? "application/json",
        messageId: message.properties.messageId,
        correlationId: message.properties.correlationId,
        headers: message.properties.headers,
        persistent: true,
      },
      (error) => (error ? reject(error) : resolve()),
    );
  });
}

async function handlePublicationMessage(
  channel: ConfirmChannel,
  message: ConsumeMessage | null,
  handle: (event: PublicationEvent) => Promise<void>,
  topology: PublicationConsumerTopology,
): Promise<void> {
  if (message === null) {
    return;
  }

  const event = parsePublicationEvent(message.content);
  const retries = retryCount(message, topology.retryQueue);

  if (event === null || retries >= MAX_DELIVERY_RETRIES) {
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
    topology.routingKeys.map((routingKey) =>
      channel.bindQueue(topology.retryQueue, topology.retryExchange, routingKey),
    ),
  );

  await channel.assertQueue(topology.queue, {
    durable: true,
    arguments: {
      "x-dead-letter-exchange": topology.retryExchange,
    },
  });

  await Promise.all(
    topology.routingKeys.map((routingKey) =>
      channel.bindQueue(topology.queue, topology.eventsExchange, routingKey),
    ),
  );

  await channel.prefetch(1);
  await channel.consume(topology.queue, (message) => {
    void handlePublicationMessage(channel, message, handle, topology);
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
