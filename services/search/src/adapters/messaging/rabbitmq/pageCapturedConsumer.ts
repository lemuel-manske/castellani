import type { ConfirmChannel, ConsumeMessage } from "amqplib";

import { PAGE_CAPTURED_EVENT } from "../../../domain.js";

import type {
  PageCapturedEvent,
  PageCapturedResult,
} from "../../../application/types.js";

import { validateMessage } from "../../../contracts.js";

import { PAGE_CAPTURED_TOPOLOGY } from "./topology.js";

const MAX_DELIVERY_RETRIES = 5;

function parsePageCaptured(body: Uint8Array): PageCapturedEvent | null {
  const message = validateMessage(body, PAGE_CAPTURED_EVENT);

  if (message == null) {
    return null;
  }

  if (message.payload["archiveId"] !== message.correlationId) {
    return null;
  }

  return {
    type: PAGE_CAPTURED_EVENT,
    version: 1,
    messageId: message.messageId,
    correlationId: message.correlationId,
    occurredAt: message.occurredAt,
    payload: message.payload as unknown as PageCapturedEvent["payload"],
  };
}

function deliveryRetryCount(message: ConsumeMessage): number {
  const deaths = message.properties.headers?.["x-death"];

  if (!Array.isArray(deaths)) {
    return 0;
  }

  const death = deaths.find(
    (death) => death.queue === PAGE_CAPTURED_TOPOLOGY.retryQueue,
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
  return new Promise((resolve, reject) => {
    channel.publish(
      PAGE_CAPTURED_TOPOLOGY.deadLetterExchange,
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
    );
  });
}

async function handlePageCapturedMessage(
  channel: ConfirmChannel,
  message: ConsumeMessage | null,
  handle: (event: PageCapturedEvent) => Promise<PageCapturedResult>,
): Promise<void> {
  if (message === null) {
    return;
  }

  const event = parsePageCaptured(message.content);

  const retries = deliveryRetryCount(message);

  if (event === null || retries >= MAX_DELIVERY_RETRIES) {
    try {
      await publishDeadLetter(channel, message);

      channel.ack(message);
    } catch {
      channel.nack(message, false, true);
    }

    return;
  }

  try {
    const result = await handle(event);

    if (result.status === "BUSY") {
      channel.nack(message, false, false);

      return;
    }

    channel.ack(message);
  } catch {
    channel.nack(message, false, false);
  }
}

async function startPageCapturedConsumer(
  channel: ConfirmChannel,
  handle: (event: PageCapturedEvent) => Promise<PageCapturedResult>,
): Promise<void> {
  await channel.prefetch(1);

  await channel.consume(PAGE_CAPTURED_TOPOLOGY.queue, (message) => {
    void handlePageCapturedMessage(channel, message, handle);
  });
}

export { MAX_DELIVERY_RETRIES, parsePageCaptured, startPageCapturedConsumer };
