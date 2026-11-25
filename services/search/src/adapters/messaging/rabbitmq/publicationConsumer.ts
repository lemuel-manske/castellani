import type { ConfirmChannel, ConsumeMessage } from "amqplib";

import type {
  CompensationDecision,
  CompletionCrawl,
  PublicationIdentity,
} from "../../../domain.js";
import { PublicationConflictError } from "../../../domain/publication.js";

import type { PublicationEvent } from "../../../application/processPublicationEvent.js";

import { validateMessage } from "../../../contracts.js";

import { EVENTS_EXCHANGE, PUBLICATION_TOPOLOGY } from "./topology.js";

const MAX_DELIVERY_RETRIES = 5;

function parsePublicationEvent(body: Uint8Array): PublicationEvent | null {
  const message = validateMessage(body);

  if (message == null) {
    return null;
  }

  if (message.payload["archiveId"] !== message.correlationId) {
    return null;
  }

  const envelope = {
    version: 1 as const,
    messageId: message.messageId,
    correlationId: message.correlationId,
    occurredAt: message.occurredAt,
  };

  if (
    message.type === "ArchivePublicationDecided" ||
    message.type === "ArchivePublished"
  ) {
    return {
      ...envelope,
      type: message.type,
      payload: message.payload as unknown as PublicationIdentity,
    };
  }

  if (message.type === "ArchiveCompensationDecided") {
    return {
      ...envelope,
      type: message.type,
      payload: message.payload as unknown as CompensationDecision,
    };
  }

  if (message.type === "CrawlCompleted") {
    return {
      ...envelope,
      type: message.type,
      payload: message.payload as unknown as CompletionCrawl,
    };
  }

  return null;
}

function retryCount(message: ConsumeMessage): number {
  const deaths = message.properties.headers?.["x-death"];

  if (!Array.isArray(deaths)) {
    return 0;
  }

  const death = deaths.find(
    (entry) => entry.queue === PUBLICATION_TOPOLOGY.retryQueue,
  );

  if (!death) {
    return 0;
  }

  const count = death.count;

  return count;
}

function publishDeadLetter(
  channel: ConfirmChannel,
  message: ConsumeMessage,
): Promise<void> {
  return new Promise((resolve, reject) =>
    channel.publish(
      PUBLICATION_TOPOLOGY.deadLetterExchange,
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

  if (event === null || retryCount(message) >= MAX_DELIVERY_RETRIES) {
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

  await channel.assertExchange(PUBLICATION_TOPOLOGY.retryExchange, "direct", {
    durable: true,
  });

  await channel.assertExchange(
    PUBLICATION_TOPOLOGY.deadLetterExchange,
    "fanout",
    {
      durable: true,
    },
  );

  await channel.assertQueue(PUBLICATION_TOPOLOGY.deadLetterQueue, {
    durable: true,
  });

  await channel.bindQueue(
    PUBLICATION_TOPOLOGY.deadLetterQueue,
    PUBLICATION_TOPOLOGY.deadLetterExchange,
    "",
  );

  await channel.assertQueue(PUBLICATION_TOPOLOGY.retryQueue, {
    durable: true,
    arguments: {
      "x-message-ttl": PUBLICATION_TOPOLOGY.retryDelayMilliseconds,
      "x-dead-letter-exchange": EVENTS_EXCHANGE,
    },
  });

  await Promise.all(
    PUBLICATION_TOPOLOGY.routingKeys.map((key) =>
      channel.bindQueue(
        PUBLICATION_TOPOLOGY.retryQueue,
        PUBLICATION_TOPOLOGY.retryExchange,
        key,
      ),
    ),
  );

  await channel.assertQueue(PUBLICATION_TOPOLOGY.queue, {
    durable: true,
    arguments: { "x-dead-letter-exchange": PUBLICATION_TOPOLOGY.retryExchange },
  });

  await Promise.all(
    PUBLICATION_TOPOLOGY.routingKeys.map((key) =>
      channel.bindQueue(PUBLICATION_TOPOLOGY.queue, EVENTS_EXCHANGE, key),
    ),
  );

  await channel.prefetch(1);

  await channel.consume(PUBLICATION_TOPOLOGY.queue, (message) => {
    void handleMessage(channel, message, handle);
  });
}

export {
  MAX_DELIVERY_RETRIES,
  parsePublicationEvent,
  startPublicationConsumer,
};
