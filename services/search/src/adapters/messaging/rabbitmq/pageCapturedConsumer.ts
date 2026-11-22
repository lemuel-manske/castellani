import type { ArtifactReference } from "../../../ports/artifacts.js";
import type { Channel, ConsumeMessage } from "amqplib";
import type { PageCapturedEvent } from "../../../application/processPageCaptured.js";

const EXPECTED_VERSION = 1;

const EVENTS_EXCHANGE = "castellani.events";
const PAGE_CAPTURED_ROUTING_KEY = "PageCaptured";
const PAGE_CAPTURED_QUEUE = "castellani.search.page-captured";
const DEAD_LETTER_EXCHANGE = "castellani.search.dead";
const DEAD_LETTER_QUEUE = "castellani.search.page-captured.dead";

interface PageCapturedConsumerTopology {
  eventsExchange: string;
  routingKey: string;
  queue: string;
  deadLetterExchange: string;
  deadLetterQueue: string;
}

const DEFAULT_TOPOLOGY: PageCapturedConsumerTopology = {
  eventsExchange: EVENTS_EXCHANGE,
  routingKey: PAGE_CAPTURED_ROUTING_KEY,
  queue: PAGE_CAPTURED_QUEUE,
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

async function handlePageCapturedMessage(
  channel: Channel,
  message: ConsumeMessage | null,
  handle: (event: PageCapturedEvent) => Promise<unknown>,
): Promise<void> {
  if (message === null) {
    return;
  }

  const event = parsePageCaptured(message.content);

  if (event === null) {
    channel.nack(message, false, false);
    return;
  }

  try {
    const result = await handle(event);

    if (isRecord(result) && result.status === "BUSY") {
      await new Promise((resolve) => setTimeout(resolve, 1000));
      channel.nack(message, false, true);
      return;
    }

    channel.ack(message);
  } catch {
    await new Promise((resolve) => setTimeout(resolve, 1000));
    channel.nack(message, false, true);
  }
}

async function startPageCapturedConsumer(
  channel: Channel,
  handle: (event: PageCapturedEvent) => Promise<unknown>,
  topology: PageCapturedConsumerTopology = DEFAULT_TOPOLOGY,
): Promise<void> {
  await channel.assertExchange(topology.eventsExchange, "topic", {
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

  await channel.assertQueue(topology.queue, {
    durable: true,
    arguments: { "x-dead-letter-exchange": topology.deadLetterExchange },
  });

  await channel.bindQueue(
    topology.queue,
    topology.eventsExchange,
    topology.routingKey,
  );

  await channel.prefetch(1);

  await channel.consume(topology.queue, (message) => {
    void handlePageCapturedMessage(channel, message, handle);
  });
}

export {
  DEAD_LETTER_EXCHANGE,
  DEAD_LETTER_QUEUE,
  EVENTS_EXCHANGE,
  EXPECTED_VERSION,
  PAGE_CAPTURED_QUEUE,
  PAGE_CAPTURED_ROUTING_KEY,
  parsePageCaptured,
  startPageCapturedConsumer,
};

export type { PageCapturedConsumerTopology };
