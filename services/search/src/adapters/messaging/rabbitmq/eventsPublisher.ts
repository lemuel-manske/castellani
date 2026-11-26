import * as amqp from "amqplib";

import type { ClaimedOutboxMessage } from "../../../ports/outbox.js";
import type { EventsPublisher } from "../../../ports/events-publisher.js";

import { EVENTS_EXCHANGE } from "./topology.js";

const PUBLISH_TIMEOUT_MILLISECONDS = 15000;

function messageError(error: unknown, fallback: string): Error {
  return error instanceof Error ? error : new Error(fallback);
}

function createRabbitMQEventsPublisher(rabbitmqUrl: string): EventsPublisher {
  return {
    async publish(message: ClaimedOutboxMessage): Promise<void> {
      const connection = await amqp.connect(rabbitmqUrl);

      try {
        const channel = await connection.createConfirmChannel();

        try {
          let returned = false;

          channel.on("return", () => {
            returned = true;
          });

          await new Promise<void>((resolve, reject) => {
            const timeout = setTimeout(() => {
              reject(new Error("event publish confirmation timed out"));
            }, PUBLISH_TIMEOUT_MILLISECONDS);

            const published = channel.publish(
              EVENTS_EXCHANGE,
              message.type,
              Buffer.from(message.envelope, "utf8"),
              {
                contentType: "application/json",
                persistent: true,
                mandatory: true,
                messageId: message.messageId,
                correlationId: message.correlationId,
              },
              (error: unknown) => {
                clearTimeout(timeout);

                if (error) {
                  reject(messageError(error, "event publish failed"));
                  return;
                }

                if (returned) {
                  reject(new Error("event message was unroutable"));
                  return;
                }

                resolve();
              },
            );

            if (!published) {
              clearTimeout(timeout);
              reject(new Error("event message was not accepted"));
            }
          });
        } finally {
          await channel.close().catch(() => undefined);
        }
      } finally {
        await connection.close().catch(() => undefined);
      }
    },
  };
}

export { createRabbitMQEventsPublisher };
