import type { ConfirmChannel, ConsumeMessage } from "amqplib";
import { isPageCapturedEvent } from "../../../application/types.js";
import type { PageCapturedEvent } from "../../../application/types.js";
import {
  EVENTS_EXCHANGE,
  PAGE_CAPTURED_TOPOLOGY,
} from "./topology.js";

const MAX_DELIVERY_RETRIES = 5;

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function parsePageCaptured(body: Uint8Array): PageCapturedEvent | null {
  let value: unknown;

  try {
    value = JSON.parse(Buffer.from(body).toString("utf8")) as unknown;
  } catch {
    return null;
  }

  if (!isPageCapturedEvent(value)) {
    return null;
  }

  const event = value;

  if (event.payload.archiveId !== event.correlationId) {
    return null;
  }

  return event;
}

function deliveryRetryCount(message: ConsumeMessage): number {
  const deaths: unknown = message.properties.headers?.["x-death"];

  if (!Array.isArray(deaths)) {
    return 0;
  }

  const retryDeath = (deaths as unknown[]).find(
    (death: unknown) =>
      isRecord(death) && death.queue === PAGE_CAPTURED_TOPOLOGY.retryQueue,
  );

  if (!isRecord(retryDeath)) {
    return 0;
  }

  const count = retryDeath.count;

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
  handle: (event: PageCapturedEvent) => Promise<unknown>,
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

    if (isRecord(result) && result.status === "BUSY") {
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
  handle: (event: PageCapturedEvent) => Promise<unknown>,
): Promise<void> {
  await channel.assertExchange(EVENTS_EXCHANGE, "topic", {
    durable: true,
  });

  await channel.assertExchange(
    PAGE_CAPTURED_TOPOLOGY.retryExchange,
    "direct",
    {
      durable: true,
    },
  );

  await channel.assertExchange(
    PAGE_CAPTURED_TOPOLOGY.deadLetterExchange,
    "fanout",
    {
      durable: true,
    },
  );

  await channel.assertQueue(PAGE_CAPTURED_TOPOLOGY.deadLetterQueue, {
    durable: true,
  });

  await channel.bindQueue(
    PAGE_CAPTURED_TOPOLOGY.deadLetterQueue,
    PAGE_CAPTURED_TOPOLOGY.deadLetterExchange,
    "",
  );

  await channel.assertQueue(PAGE_CAPTURED_TOPOLOGY.retryQueue, {
    durable: true,
    arguments: {
      "x-message-ttl": PAGE_CAPTURED_TOPOLOGY.retryDelayMilliseconds,
      "x-dead-letter-exchange": EVENTS_EXCHANGE,
      "x-dead-letter-routing-key": PAGE_CAPTURED_TOPOLOGY.routingKey,
    },
  });

  await channel.bindQueue(
    PAGE_CAPTURED_TOPOLOGY.retryQueue,
    PAGE_CAPTURED_TOPOLOGY.retryExchange,
    PAGE_CAPTURED_TOPOLOGY.routingKey,
  );

  await channel.assertQueue(PAGE_CAPTURED_TOPOLOGY.queue, {
    durable: true,
    arguments: {
      "x-dead-letter-exchange": PAGE_CAPTURED_TOPOLOGY.retryExchange,
      "x-dead-letter-routing-key": PAGE_CAPTURED_TOPOLOGY.routingKey,
    },
  });

  await channel.bindQueue(
    PAGE_CAPTURED_TOPOLOGY.queue,
    EVENTS_EXCHANGE,
    PAGE_CAPTURED_TOPOLOGY.routingKey,
  );

  await channel.prefetch(1);

  await channel.consume(PAGE_CAPTURED_TOPOLOGY.queue, (message) => {
    void handlePageCapturedMessage(channel, message, handle);
  });
}

export { MAX_DELIVERY_RETRIES, parsePageCaptured, startPageCapturedConsumer };

