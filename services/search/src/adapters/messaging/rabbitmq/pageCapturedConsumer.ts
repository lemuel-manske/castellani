import type { ArtifactReference } from "../../../ports/artifacts.js";
import type { ConfirmChannel, ConsumeMessage } from "amqplib";
import type { PageCapturedEvent } from "../../../application/processPageCaptured.js";

const EXPECTED_VERSION = 1;
const MAX_DELIVERY_RETRIES = 5;
const RETRY_DELAY_MILLISECONDS = 5_000;

const EVENTS_EXCHANGE = "castellani.events";
const PAGE_CAPTURED_ROUTING_KEY = "PageCaptured";
const PAGE_CAPTURED_QUEUE = "castellani.search.page-captured.v2";
const RETRY_EXCHANGE = "castellani.search.retry";
const RETRY_QUEUE = "castellani.search.page-captured.retry.v2";
const DEAD_LETTER_EXCHANGE = "castellani.search.dead";
const DEAD_LETTER_QUEUE = "castellani.search.page-captured.dead";

interface PageCapturedConsumerTopology {
  eventsExchange: string;
  routingKey: string;
  queue: string;
  retryExchange: string;
  retryQueue: string;
  deadLetterExchange: string;
  deadLetterQueue: string;
}

const DEFAULT_TOPOLOGY: PageCapturedConsumerTopology = {
  eventsExchange: EVENTS_EXCHANGE,
  routingKey: PAGE_CAPTURED_ROUTING_KEY,
  queue: PAGE_CAPTURED_QUEUE,
  retryExchange: RETRY_EXCHANGE,
  retryQueue: RETRY_QUEUE,
  deadLetterExchange: DEAD_LETTER_EXCHANGE,
  deadLetterQueue: DEAD_LETTER_QUEUE,
};

function isString(value: unknown): value is string {
  return typeof value === "string" && value.length > 0;
}

function isArtifactReference(value: unknown): value is ArtifactReference {
  if (!isRecord(value)) {
    return false;
  }

  return (
    isString(value.bucket) &&
    isString(value.key) &&
    isString(value.sha256) &&
    /^[a-f0-9]{64}$/.test(value.sha256) &&
    typeof value.sizeBytes === "number" &&
    Number.isSafeInteger(value.sizeBytes) &&
    value.sizeBytes >= 0 &&
    (value.versionId === undefined || isString(value.versionId))
  );
}

function isPageCapturedEvent(value: unknown): value is PageCapturedEvent {
  if (!isRecord(value) || !isRecord(value.payload)) {
    return false;
  }

  const payload = value.payload;

  return (
    isString(value.messageId) &&
    isString(value.correlationId) &&
    value.type === "PageCaptured" &&
    value.version === EXPECTED_VERSION &&
    isString(value.occurredAt) &&
    isString(payload.archiveId) &&
    isString(payload.snapshotId) &&
    isString(payload.urlKey) &&
    isString(payload.url) &&
    isString(payload.finalUrl) &&
    Array.isArray(payload.redirectChain) &&
    payload.redirectChain.every(isString) &&
    isString(payload.capturedAt) &&
    (payload.contentType === undefined ||
      typeof payload.contentType === "string") &&
    Array.isArray(payload.warcArtifacts) &&
    payload.warcArtifacts.length > 0 &&
    payload.warcArtifacts.every(isArtifactReference)
  );
}

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

function deliveryRetryCount(
  message: ConsumeMessage,
  retryQueue: string,
): number {
  const deaths: unknown = message.properties.headers?.["x-death"];

  if (!Array.isArray(deaths)) {
    return 0;
  }

  const retryDeath = (deaths as unknown[]).find(
    (death: unknown) => isRecord(death) && death.queue === retryQueue,
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
  topology: PageCapturedConsumerTopology,
  message: ConsumeMessage,
): Promise<void> {
  return new Promise((resolve, reject) => {
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
    );
  });
}

async function handlePageCapturedMessage(
  channel: ConfirmChannel,
  message: ConsumeMessage | null,
  handle: (event: PageCapturedEvent) => Promise<unknown>,
  topology: PageCapturedConsumerTopology,
): Promise<void> {
  if (message === null) {
    return;
  }

  const event = parsePageCaptured(message.content);
  const retries = deliveryRetryCount(message, topology.retryQueue);

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
  topology: PageCapturedConsumerTopology = DEFAULT_TOPOLOGY,
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
      "x-dead-letter-routing-key": topology.routingKey,
    },
  });

  await channel.bindQueue(
    topology.retryQueue,
    topology.retryExchange,
    topology.routingKey,
  );

  await channel.assertQueue(topology.queue, {
    durable: true,
    arguments: {
      "x-dead-letter-exchange": topology.retryExchange,
      "x-dead-letter-routing-key": topology.routingKey,
    },
  });

  await channel.bindQueue(
    topology.queue,
    topology.eventsExchange,
    topology.routingKey,
  );

  await channel.prefetch(1);

  await channel.consume(topology.queue, (message) => {
    void handlePageCapturedMessage(channel, message, handle, topology);
  });
}

export {
  DEAD_LETTER_EXCHANGE,
  DEAD_LETTER_QUEUE,
  EVENTS_EXCHANGE,
  EXPECTED_VERSION,
  MAX_DELIVERY_RETRIES,
  PAGE_CAPTURED_QUEUE,
  PAGE_CAPTURED_ROUTING_KEY,
  RETRY_EXCHANGE,
  RETRY_QUEUE,
  parsePageCaptured,
  startPageCapturedConsumer,
};

export type { PageCapturedConsumerTopology };
