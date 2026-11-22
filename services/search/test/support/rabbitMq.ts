import { randomUUID } from "node:crypto";
import * as amqp from "amqplib";
import type { ConsumeMessage } from "amqplib";
import {
  startPageCapturedConsumer,
  type PageCapturedConsumerTopology,
} from "../../src/adapters/messaging/rabbitmq/pageCapturedConsumer.js";
import {
  startPublicationConsumer,
  type PublicationConsumerTopology,
} from "../../src/adapters/messaging/rabbitmq/publicationConsumer.js";
import type { PageCapturedEvent } from "../../src/application/processPageCaptured.js";
import type { PublicationEvent } from "../../src/application/processPublicationEvent.js";

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
  const publicationTopology: PublicationConsumerTopology = {
    eventsExchange: `search-publication-integration-events-${suffix}`,
    routingKeys: [
      "ArchivePublicationDecided",
      "ArchivePublished",
      "ArchiveCompensationDecided",
      "CrawlCompleted",
    ],
    queue: `search-publication-integration-queue-${suffix}`,
    retryExchange: `search-publication-integration-retry-${suffix}`,
    retryQueue: `search-publication-integration-retry-queue-${suffix}`,
    deadLetterExchange: `search-publication-integration-dead-${suffix}`,
    deadLetterQueue: `search-publication-integration-dead-queue-${suffix}`,
  };

  let connection: amqp.ChannelModel | undefined;
  let consumerChannel: amqp.ConfirmChannel | undefined;
  let publicationConsumerChannel: amqp.ConfirmChannel | undefined;
  let publisherChannel: amqp.ConfirmChannel | undefined;
  const deadLetters: ConsumeMessage[] = [];
  const deadLetterWaiters: ((message: ConsumeMessage) => void)[] = [];
  const publicationDeadLetters: ConsumeMessage[] = [];
  const publicationDeadLetterWaiters: ((message: ConsumeMessage) => void)[] = [];

  function receiveDeadLetter(
    message: ConsumeMessage,
    messages: ConsumeMessage[],
    waiters: ((message: ConsumeMessage) => void)[],
    channel: amqp.ConfirmChannel | undefined,
  ): void {
    channel?.ack(message);
    const waiter = waiters.shift();
    waiter ? waiter(message) : messages.push(message);
  }

  return {
    async setup(
      handle: (event: PageCapturedEvent) => Promise<unknown>,
      handlePublication: (event: PublicationEvent) => Promise<void>,
    ): Promise<void> {
      connection = await amqp.connect(
        SEARCH_RABBITMQ_URL ?? "amqp://localhost",
      );
      consumerChannel = await connection.createConfirmChannel();
      publicationConsumerChannel = await connection.createConfirmChannel();
      publisherChannel = await connection.createConfirmChannel();
      await startPageCapturedConsumer(consumerChannel, handle, topology);
      await startPublicationConsumer(
        publicationConsumerChannel,
        handlePublication,
        publicationTopology,
      );
      await consumerChannel.consume(topology.deadLetterQueue, (message) => {
        if (message === null) {
          return;
        }

        receiveDeadLetter(message, deadLetters, deadLetterWaiters, consumerChannel);
      });
      await publicationConsumerChannel.consume(
        publicationTopology.deadLetterQueue,
        (message) => {
          if (message === null) {
            return;
          }

          receiveDeadLetter(
            message,
            publicationDeadLetters,
            publicationDeadLetterWaiters,
            publicationConsumerChannel,
          );
        },
      );
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

    async publishPublication(event: unknown, routingKey: string): Promise<void> {
      if (publisherChannel === undefined) {
        throw new Error("RabbitMQ integration environment is not initialized");
      }

      publisherChannel.publish(
        publicationTopology.eventsExchange,
        routingKey,
        Buffer.from(JSON.stringify(event)),
        { contentType: "application/json", persistent: true },
      );
      await publisherChannel.waitForConfirms();
    },

    nextDeadLetter(): Promise<ConsumeMessage> {
      const message = deadLetters.shift();

      return message === undefined
        ? new Promise((resolve) => deadLetterWaiters.push(resolve))
        : Promise.resolve(message);
    },

    nextPublicationDeadLetter(): Promise<ConsumeMessage> {
      const message = publicationDeadLetters.shift();

      return message === undefined
        ? new Promise((resolve) =>
            publicationDeadLetterWaiters.push(resolve),
          )
        : Promise.resolve(message);
    },

    async teardown(): Promise<void> {
      if (connection === undefined) {
        return;
      }

      await publisherChannel?.close().catch(() => undefined);
      await consumerChannel?.close().catch(() => undefined);
      await publicationConsumerChannel?.close().catch(() => undefined);

      try {
        const cleanup = await connection.createChannel();

        try {
          await Promise.all([
            topology.queue,
            topology.retryQueue,
            topology.deadLetterQueue,
            publicationTopology.queue,
            publicationTopology.retryQueue,
            publicationTopology.deadLetterQueue,
          ].map((queue) => cleanup.deleteQueue(queue).catch(() => undefined)));
          await Promise.all([
            topology.eventsExchange,
            topology.retryExchange,
            topology.deadLetterExchange,
            publicationTopology.eventsExchange,
            publicationTopology.retryExchange,
            publicationTopology.deadLetterExchange,
          ].map((exchange) =>
            cleanup.deleteExchange(exchange).catch(() => undefined),
          ));
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
