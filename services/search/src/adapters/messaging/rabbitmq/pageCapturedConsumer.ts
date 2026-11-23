import type { ConfirmChannel, ConsumeMessage } from "amqplib";
import { isPageCapturedEvent } from "../../../application/types.js";
import type { PageCapturedEvent } from "../../../application/types.js";

const MAX_DELIVERY_RETRIES = 5;
const RETRY_DELAY_MILLISECONDS = 5_000;

const EVENTS_EXCHANGE = "castellani.events";
const PAGE_CAPTURED_ROUTING_KEY = "PageCaptured";
const PAGE_CAPTURED_QUEUE = "castellani.search.page-captured.v2";
const RETRY_EXCHANGE = "castellani.search.retry";
const RETRY_QUEUE = "castellani.search.page-captured.retry.v2";
const DEAD_LETTER_EXCHANGE = "castellani.search.dead";
const DEAD_LETTER_QUEUE = "castellani.search.page-captured.dead";

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
    (death: unknown) => isRecord(death) && death.queue === RETRY_QUEUE,
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
      "x-dead-letter-routing-key": PAGE_CAPTURED_ROUTING_KEY,
    },
  });

  await channel.bindQueue(
    RETRY_QUEUE,
    RETRY_EXCHANGE,
    PAGE_CAPTURED_ROUTING_KEY,
  );

  await channel.assertQueue(PAGE_CAPTURED_QUEUE, {
    durable: true,
    arguments: {
      "x-dead-letter-exchange": RETRY_EXCHANGE,
      "x-dead-letter-routing-key": PAGE_CAPTURED_ROUTING_KEY,
    },
  });

  await channel.bindQueue(
    PAGE_CAPTURED_QUEUE,
    EVENTS_EXCHANGE,
    PAGE_CAPTURED_ROUTING_KEY,
  );

  await channel.prefetch(1);

  await channel.consume(PAGE_CAPTURED_QUEUE, (message) => {
    void handlePageCapturedMessage(channel, message, handle);
  });
}

export {
  DEAD_LETTER_EXCHANGE,
  DEAD_LETTER_QUEUE,
  EVENTS_EXCHANGE,
  MAX_DELIVERY_RETRIES,
  PAGE_CAPTURED_QUEUE,
  PAGE_CAPTURED_ROUTING_KEY,
  RETRY_EXCHANGE,
  RETRY_QUEUE,
  parsePageCaptured,
  startPageCapturedConsumer,
};

