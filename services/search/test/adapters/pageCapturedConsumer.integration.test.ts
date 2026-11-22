import { randomUUID } from "node:crypto";
import * as amqp from "amqplib";
import { afterAll, beforeAll, describe, expect, it } from "vitest";
import {
  startPageCapturedConsumer,
  type PageCapturedConsumerTopology,
} from "../../src/adapters/messaging/rabbitmq/pageCapturedConsumer.js";
import type { PageCapturedEvent } from "../../src/application/processPageCaptured.js";

const url = process.env.SEARCH_TEST_RABBITMQ_URL;

describe.skipIf(url === undefined)("RabbitMQ PageCaptured integration", () => {
  const suffix = randomUUID().replaceAll("-", "");
  const topology: PageCapturedConsumerTopology = {
    eventsExchange: `search-integration-events-${suffix}`,
    routingKey: "PageCaptured",
    queue: `search-integration-queue-${suffix}`,
    deadLetterExchange: `search-integration-dead-${suffix}`,
    deadLetterQueue: `search-integration-dead-queue-${suffix}`,
  };

  let connection: amqp.ChannelModel | undefined;
  let consumerChannel: amqp.Channel | undefined;
  let resolveReceived: (event: PageCapturedEvent) => void = () => {
    throw new Error("consumer was not initialized");
  };
  let received: Promise<PageCapturedEvent> = new Promise<PageCapturedEvent>(() => undefined);

  beforeAll(async () => {
    connection = await amqp.connect(url ?? "amqp://localhost");
    consumerChannel = await connection.createChannel();
    received = new Promise((resolve) => {
      resolveReceived = resolve;
    });

    await startPageCapturedConsumer(
      consumerChannel,
      async (event) => {
        resolveReceived(event);
        return { status: "COMPLETED" };
      },
      topology,
    );
  });

  afterAll(async () => {
    await consumerChannel?.close().catch(() => undefined);

    if (connection !== undefined) {
      const cleanup = await connection.createChannel();
      await cleanup.deleteQueue(topology.queue);
      await cleanup.deleteQueue(topology.deadLetterQueue);
      await cleanup.deleteExchange(topology.eventsExchange);
      await cleanup.deleteExchange(topology.deadLetterExchange);
      await cleanup.close();
      await connection.close();
    }
  });

  it("delivers the Capture-produced event envelope to the consumer", async () => {
    const event = {
      messageId: `page-captured-${suffix}`,
      correlationId: "integration-archive",
      type: "PageCaptured",
      version: 1,
      occurredAt: "2026-11-22T10:00:00.000Z",
      payload: {
        archiveId: "integration-archive",
        snapshotId: "integration-snapshot",
        urlKey: "integration-url-key",
        url: "https://example.com/",
        finalUrl: "https://example.com/final",
        redirectChain: ["https://example.com/", "https://example.com/final"],
        capturedAt: "2026-11-22T10:00:00.000Z",
        contentType: "text/html",
        warcArtifacts: [
          {
            bucket: "capture-artifacts",
            key: `capture-staging/integration-archive/integration-url-key/attempt-${suffix}/integration-snapshot/page.warc.gz`,
            sha256: "a".repeat(64),
            sizeBytes: 128,
            versionId: "integration-version",
          },
        ],
      },
    };

    const publisher = await connection!.createChannel();
    await publisher.assertExchange(topology.eventsExchange, "topic", {
      durable: true,
    });
    publisher.publish(
      topology.eventsExchange,
      topology.routingKey,
      Buffer.from(JSON.stringify(event)),
      {
        contentType: "application/json",
        messageId: event.messageId,
        persistent: true,
      },
    );

    await expect(received).resolves.toMatchObject({
      messageId: event.messageId,
      correlationId: "integration-archive",
      payload: {
        archiveId: "integration-archive",
        snapshotId: "integration-snapshot",
        finalUrl: "https://example.com/final",
      },
    });

    await publisher.close();
  });
});
