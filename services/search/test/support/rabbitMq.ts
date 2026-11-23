import * as amqp from "amqplib";
import type { ConsumeMessage } from "amqplib";
import {
  DEAD_LETTER_QUEUE as PAGE_CAPTURED_DEAD_LETTER_QUEUE,
  EVENTS_EXCHANGE,
  RETRY_EXCHANGE as PAGE_CAPTURED_RETRY_EXCHANGE,
  DEAD_LETTER_EXCHANGE as PAGE_CAPTURED_DEAD_LETTER_EXCHANGE,
  PAGE_CAPTURED_QUEUE,
  PAGE_CAPTURED_ROUTING_KEY,
  RETRY_QUEUE as PAGE_CAPTURED_RETRY_QUEUE,
  startPageCapturedConsumer,
} from "../../src/adapters/messaging/rabbitmq/pageCapturedConsumer.js";
import {
  DEAD_LETTER_QUEUE as PUBLICATION_DEAD_LETTER_QUEUE,
  PUBLICATION_QUEUE,
  RETRY_EXCHANGE as PUBLICATION_RETRY_EXCHANGE,
  DEAD_LETTER_EXCHANGE as PUBLICATION_DEAD_LETTER_EXCHANGE,
  RETRY_QUEUE as PUBLICATION_RETRY_QUEUE,
  startPublicationConsumer,
} from "../../src/adapters/messaging/rabbitmq/publicationConsumer.js";
import type {
  PageCapturedEvent,
  PublicationEvent,
} from "../../src/application/types.js";

const SEARCH_RABBITMQ_URL = process.env.SEARCH_RABBITMQ_URL;

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
      handle: (event: PageCapturedEvent) => Promise<unknown>,
      handlePublication: (event: PublicationEvent) => Promise<void>,
    ): Promise<void> {
      connection = await amqp.connect(
        SEARCH_RABBITMQ_URL ?? "amqp://localhost",
      );
      consumerChannel = await connection.createConfirmChannel();
      publicationConsumerChannel = await connection.createConfirmChannel();
      publisherChannel = await connection.createConfirmChannel();
      await startPageCapturedConsumer(consumerChannel, handle);
      await startPublicationConsumer(
        publicationConsumerChannel,
        handlePublication,
      );
      await consumerChannel.consume(
        PAGE_CAPTURED_DEAD_LETTER_QUEUE,
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
        PUBLICATION_DEAD_LETTER_QUEUE,
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
        PAGE_CAPTURED_ROUTING_KEY,
        Buffer.from(JSON.stringify(event)),
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

      publisherChannel.publish(
        EVENTS_EXCHANGE,
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
              PAGE_CAPTURED_QUEUE,
              PAGE_CAPTURED_RETRY_QUEUE,
              PAGE_CAPTURED_DEAD_LETTER_QUEUE,
              PUBLICATION_QUEUE,
              PUBLICATION_RETRY_QUEUE,
              PUBLICATION_DEAD_LETTER_QUEUE,
            ].map((queue) => cleanup.deleteQueue(queue).catch(() => undefined)),
          );
          await Promise.all(
            [
              PAGE_CAPTURED_RETRY_EXCHANGE,
              PAGE_CAPTURED_DEAD_LETTER_EXCHANGE,
              PUBLICATION_RETRY_EXCHANGE,
              PUBLICATION_DEAD_LETTER_EXCHANGE,
            ].map((exchange) =>
              cleanup.deleteExchange(exchange).catch(() => undefined),
            ),
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

export { SEARCH_RABBITMQ_URL, createRabbitMqTestSupport };
