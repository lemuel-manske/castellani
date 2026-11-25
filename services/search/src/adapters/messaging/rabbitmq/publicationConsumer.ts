import type { ConfirmChannel, ConsumeMessage } from "amqplib";

import {
  ARCHIVE_COMPENSATION_DECIDED_EVENT,
  ARCHIVE_PUBLICATION_DECIDED_EVENT,
  ARCHIVE_PUBLISHED_EVENT,
  CRAWL_COMPLETED_EVENT,
  type CompensationDecision,
  type CompletionCrawl,
  type PublicationIdentity,
} from "../../../domain.js";
import { PublicationConflictError } from "../../../domain/publication.js";

import type { PublicationEvent } from "../../../application/processPublicationEvent.js";

import { validateMessage } from "../../../contracts.js";

import { PUBLICATION_TOPOLOGY } from "./topology.js";

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
    message.type === ARCHIVE_PUBLICATION_DECIDED_EVENT ||
    message.type === ARCHIVE_PUBLISHED_EVENT
  ) {
    return {
      ...envelope,
      type: message.type,
      payload: message.payload as unknown as PublicationIdentity,
    };
  }

  if (message.type === ARCHIVE_COMPENSATION_DECIDED_EVENT) {
    return {
      ...envelope,
      type: message.type,
      payload: message.payload as unknown as CompensationDecision,
    };
  }

  if (message.type === CRAWL_COMPLETED_EVENT) {
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
