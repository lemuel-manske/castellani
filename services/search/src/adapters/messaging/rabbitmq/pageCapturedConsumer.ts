import type { Channel, ConsumeMessage } from "amqplib";
import type { ArtifactReference } from "../../../ports/artifacts.js";
import type { PageCapturedEvent } from "../../../application/processPageCaptured.js";

const EVENTS_EXCHANGE = "castellani.events";
const PAGE_CAPTURED_ROUTING_KEY = "PageCaptured";
const PAGE_CAPTURED_QUEUE = "castellani.search.page-captured";
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

  if (!isRecord(value)) {
    return null;
  }

  if (
    typeof value.messageId !== "string" ||
    !value.messageId ||
    typeof value.correlationId !== "string" ||
    !value.correlationId ||
    value.type !== "PageCaptured" ||
    value.version !== 1 ||
    typeof value.occurredAt !== "string" ||
    !isRecord(value.payload)
  ) {
    return null;
  }

  const payload = value.payload;
  const artifacts = payload.warcArtifacts;

  if (
    typeof payload.archiveId !== "string" ||
    !payload.archiveId ||
    payload.archiveId !== value.correlationId ||
    typeof payload.snapshotId !== "string" ||
    !payload.snapshotId ||
    typeof payload.urlKey !== "string" ||
    !payload.urlKey ||
    typeof payload.url !== "string" ||
    typeof payload.capturedAt !== "string" ||
    !Array.isArray(artifacts) ||
    artifacts.length === 0
  ) {
    return null;
  }

  const validArtifacts = artifacts.every(
    (artifact: unknown) =>
      isRecord(artifact) &&
      typeof artifact.bucket === "string" &&
      artifact.bucket.length > 0 &&
      typeof artifact.key === "string" &&
      artifact.key.length > 0 &&
      typeof artifact.sha256 === "string" &&
      /^[a-f0-9]{64}$/i.test(artifact.sha256) &&
      (artifact.versionId === undefined ||
        typeof artifact.versionId === "string") &&
      typeof artifact.sizeBytes === "number" &&
      Number.isSafeInteger(artifact.sizeBytes) &&
      artifact.sizeBytes >= 0,
  );

  if (!validArtifacts) {
    return null;
  }

  return {
    messageId: value.messageId,
    correlationId: value.correlationId,
    occurredAt: value.occurredAt,
    payload: {
      archiveId: payload.archiveId,
      snapshotId: payload.snapshotId,
      urlKey: payload.urlKey,
      url: payload.url,
      ...(typeof payload.finalUrl === "string"
        ? { finalUrl: payload.finalUrl }
        : {}),
      capturedAt: payload.capturedAt,
      ...(typeof payload.contentType === "string"
        ? { contentType: payload.contentType }
        : {}),
      warcArtifacts: artifacts as ArtifactReference[],
    },
  };
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
): Promise<void> {
  await channel.assertExchange(EVENTS_EXCHANGE, "topic", { durable: true });
  await channel.assertExchange(DEAD_LETTER_EXCHANGE, "fanout", {
    durable: true,
  });
  await channel.assertQueue(DEAD_LETTER_QUEUE, { durable: true });
  await channel.bindQueue(DEAD_LETTER_QUEUE, DEAD_LETTER_EXCHANGE, "");
  await channel.assertQueue(PAGE_CAPTURED_QUEUE, {
    durable: true,
    arguments: { "x-dead-letter-exchange": DEAD_LETTER_EXCHANGE },
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
  PAGE_CAPTURED_QUEUE,
  PAGE_CAPTURED_ROUTING_KEY,
  parsePageCaptured,
  startPageCapturedConsumer,
};
