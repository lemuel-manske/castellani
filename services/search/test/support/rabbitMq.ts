import { randomUUID } from "node:crypto";
import * as amqp from "amqplib";
import {
  startPageCapturedConsumer,
  type PageCapturedConsumerTopology,
} from "../../src/adapters/messaging/rabbitmq/pageCapturedConsumer.js";
import type { PageCapturedEvent } from "../../src/application/processPageCaptured.js";

const SEARCH_RABBITMQ_URL = process.env.SEARCH_RABBITMQ_URL;

function createRabbitMqTestSupport() {
  const suffix = randomUUID().replaceAll("-", "");
  const topology: PageCapturedConsumerTopology = {
    eventsExchange: `search-integration-events-${suffix}`,
    routingKey: "PageCaptured",
    queue: `search-integration-queue-${suffix}`,
    retryExchange: `search-integration-retry-${suffix}`,
    retryQueue: `search-integration-retry-queue-${suffix}`,
    deadLetterExchange: `search-integration-dead-${suffix}`,
    deadLetterQueue: `search-integration-dead-queue-${suffix}`,
  };

  let connection: amqp.ChannelModel | undefined;
  let consumerChannel: amqp.ConfirmChannel | undefined;
  let publisherChannel: amqp.ConfirmChannel | undefined;

  return {
    async setup(
      handle: (event: PageCapturedEvent) => Promise<unknown>,
    ): Promise<void> {
      connection = await amqp.connect(
        SEARCH_RABBITMQ_URL ?? "amqp://localhost",
      );
      consumerChannel = await connection.createConfirmChannel();
      publisherChannel = await connection.createConfirmChannel();
      await startPageCapturedConsumer(consumerChannel, handle, topology);
    },

    async publish(event: unknown): Promise<void> {
      if (publisherChannel === undefined) {
        throw new Error("RabbitMQ integration environment is not initialized");
      }

      publisherChannel.publish(
        topology.eventsExchange,
        topology.routingKey,
        Buffer.from(JSON.stringify(event)),
        { contentType: "application/json", persistent: true },
      );
      await publisherChannel.waitForConfirms();
    },

    async teardown(): Promise<void> {
      if (connection === undefined) {
        return;
      }

      await publisherChannel?.close().catch(() => undefined);
      await consumerChannel?.close().catch(() => undefined);

      try {
        const cleanup = await connection.createChannel();

        try {
          await cleanup.deleteQueue(topology.queue).catch(() => undefined);
          await cleanup.deleteQueue(topology.retryQueue).catch(() => undefined);
          await cleanup
            .deleteQueue(topology.deadLetterQueue)
            .catch(() => undefined);
          await cleanup
            .deleteExchange(topology.eventsExchange)
            .catch(() => undefined);
          await cleanup
            .deleteExchange(topology.retryExchange)
            .catch(() => undefined);
          await cleanup
            .deleteExchange(topology.retryExchange)
            .catch(() => undefined);
          await cleanup
            .deleteExchange(topology.deadLetterExchange)
            .catch(() => undefined);
        } finally {
          await cleanup.close().catch(() => undefined);
        }
      } finally {
        await connection.close().catch(() => undefined);
      }
    },
  };
}

export { SEARCH_RABBITMQ_URL, createRabbitMqTestSupport };
