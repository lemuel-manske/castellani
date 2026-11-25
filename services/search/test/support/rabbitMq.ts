import * as amqp from "amqplib";
import type { ConsumeMessage } from "amqplib";

import {
  EVENTS_EXCHANGE,
  PAGE_CAPTURED_TOPOLOGY,
  PUBLICATION_TOPOLOGY,
} from "../../src/adapters/messaging/rabbitmq/topology.js";
import { startPageCapturedConsumer } from "../../src/adapters/messaging/rabbitmq/pageCapturedConsumer.js";
import { startPublicationConsumer } from "../../src/adapters/messaging/rabbitmq/publicationConsumer.js";

import type {
  PageCapturedEvent,
  PageCapturedResult,
  PublicationEvent,
} from "../../src/application/types.js";

import { SEARCH_RABBITMQ_URL } from "./env.js";
import { bufferJSON } from "../../src/utils.js";

function createRabbitMqTestSupport() {
  let connection: amqp.ChannelModel | undefined;
  let consumerChannel: amqp.ConfirmChannel | undefined;
  let publicationConsumerChannel: amqp.ConfirmChannel | undefined;
  let publisherChannel: amqp.ConfirmChannel | undefined;

  const deadLetters: ConsumeMessage[] = [];
  const deadLetterWaiters: ((message: ConsumeMessage) => void)[] = [];
  const publicationDeadLetters: ConsumeMessage[] = [];
  const publicationDeadLetterWaiters: ((message: ConsumeMessage) => void)[] =
    [];

  function receiveDeadLetter(
    message: ConsumeMessage,
    messages: ConsumeMessage[],
    waiters: ((message: ConsumeMessage) => void)[],
    channel: amqp.ConfirmChannel | undefined,
  ): void {
    channel?.ack(message);

    const waiter = waiters.shift();

    if (waiter === undefined) {
      messages.push(message);
      return;
    }

    waiter(message);
  }

  return {
    async setup(
      handleCapture: (event: PageCapturedEvent) => Promise<PageCapturedResult>,
      handlePublication: (event: PublicationEvent) => Promise<void>,
    ): Promise<void> {
      connection = await amqp.connect(
        SEARCH_RABBITMQ_URL ?? "amqp://localhost",
      );
      consumerChannel = await connection.createConfirmChannel();
      publicationConsumerChannel = await connection.createConfirmChannel();
      publisherChannel = await connection.createConfirmChannel();

      await startPageCapturedConsumer(consumerChannel, handleCapture);

      await startPublicationConsumer(
        publicationConsumerChannel,
        handlePublication,
      );

      await consumerChannel.consume(
        PAGE_CAPTURED_TOPOLOGY.deadLetterQueue,
        (message) => {
          if (message === null) {
            return;
          }

          receiveDeadLetter(
            message,
            deadLetters,
            deadLetterWaiters,
            consumerChannel,
          );
        },
      );

      await publicationConsumerChannel.consume(
        PUBLICATION_TOPOLOGY.deadLetterQueue,
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
        EVENTS_EXCHANGE,
        PAGE_CAPTURED_TOPOLOGY.routingKey,
        bufferJSON(event),
        { contentType: "application/json", persistent: true },
      );

      await publisherChannel.waitForConfirms();
    },

    async publishPublication(
      event: unknown,
      routingKey: string,
    ): Promise<void> {
      if (publisherChannel === undefined) {
        throw new Error("RabbitMQ integration environment is not initialized");
      }

      publisherChannel.publish(EVENTS_EXCHANGE, routingKey, bufferJSON(event), {
        contentType: "application/json",
        persistent: true,
      });

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
        ? new Promise((resolve) => publicationDeadLetterWaiters.push(resolve))
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
          await Promise.all(
            [
              PAGE_CAPTURED_TOPOLOGY.queue,
              PAGE_CAPTURED_TOPOLOGY.retryQueue,
              PAGE_CAPTURED_TOPOLOGY.deadLetterQueue,
              PUBLICATION_TOPOLOGY.queue,
              PUBLICATION_TOPOLOGY.retryQueue,
              PUBLICATION_TOPOLOGY.deadLetterQueue,
            ].map((queue) => cleanup.purgeQueue(queue).catch(() => undefined)),
          );
        } finally {
          await cleanup.close().catch(() => undefined);
        }
      } finally {
        await connection.close().catch(() => undefined);
      }
    },
  };
}

export { createRabbitMqTestSupport };
