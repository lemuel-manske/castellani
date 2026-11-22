import Ajv, { type AnySchema } from "ajv";
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

const PAGE_CAPTURED_SCHEMA = {
  type: "object",
  required: [
    "messageId",
    "correlationId",
    "type",
    "version",
    "occurredAt",
    "payload",
  ],
  properties: {
    messageId: { type: "string", minLength: 1 },
    correlationId: { type: "string", minLength: 1 },
    type: { const: "PageCaptured" },
    version: { const: EXPECTED_VERSION },
    occurredAt: { type: "string", minLength: 1 },
    payload: {
      type: "object",
      required: [
        "archiveId",
        "snapshotId",
        "urlKey",
        "url",
        "finalUrl",
        "redirectChain",
        "capturedAt",
        "warcArtifacts",
      ],
      properties: {
        archiveId: { type: "string", minLength: 1 },
        snapshotId: { type: "string", minLength: 1 },
        urlKey: { type: "string", minLength: 1 },
        url: { type: "string", minLength: 1 },
        finalUrl: { type: "string", minLength: 1 },
        redirectChain: {
          type: "array",
          items: { type: "string", minLength: 1 },
        },
        capturedAt: { type: "string", minLength: 1 },
        contentType: { type: "string" },
        warcArtifacts: {
          type: "array",
          minItems: 1,
          items: {
            type: "object",
            required: ["bucket", "key", "sha256", "sizeBytes"],
            properties: {
              bucket: { type: "string", minLength: 1 },
              key: { type: "string", minLength: 1 },
              sha256: { type: "string", pattern: "^[a-f0-9]{64}$" },
              sizeBytes: { type: "integer", minimum: 0, maximum: 9007199254740991 },
              versionId: { type: "string", minLength: 1 },
            },
          },
        },
      },
    },
  },
} satisfies AnySchema;

const validatePageCaptured = new Ajv({ allErrors: true }).compile<unknown>(
  PAGE_CAPTURED_SCHEMA,
);

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

  if (!validatePageCaptured(value)) {
    return null;
  }

  const event = value as PageCapturedEvent;
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
