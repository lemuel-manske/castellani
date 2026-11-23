import * as amqp from "amqplib";
import { startPageCapturedConsumer } from "../adapters/messaging/rabbitmq/pageCapturedConsumer.js";
import { startPublicationConsumer } from "../adapters/messaging/rabbitmq/publicationConsumer.js";
import type {
  PageCapturedEvent,
  PageCapturedResult,
  PublicationEvent,
} from "../application/types.js";

interface SearchWorkerHandlers {
  pageCaptured(event: PageCapturedEvent): Promise<PageCapturedResult>;
  publicationEvent(event: PublicationEvent): Promise<void>;
}

interface SearchWorkerSettings {
  rabbitmqUrl: string;
  reconnectDelayMilliseconds: number;
}

/** Owns the RabbitMQ connection and consumer lifecycle for Search. */
class SearchWorker {
  constructor(
    private readonly settings: SearchWorkerSettings,
    private readonly handlers: SearchWorkerHandlers,
  ) {}

  async start(signal: AbortSignal): Promise<void> {
    while (!signal.aborted) {
      let connection: amqp.ChannelModel | undefined;
      let pageCapturedChannel: amqp.ConfirmChannel | undefined;
      let publicationChannel: amqp.ConfirmChannel | undefined;

      try {
        connection = await amqp.connect(this.settings.rabbitmqUrl);

        if (signal.aborted) {
          await connection.close();
          break;
        }

        pageCapturedChannel = await connection.createConfirmChannel();
        publicationChannel = await connection.createConfirmChannel();

        if (signal.aborted) {
          await Promise.all([
            pageCapturedChannel.close(),
            publicationChannel.close(),
          ]);
          await connection.close();
          break;
        }

        await startPageCapturedConsumer(
          pageCapturedChannel,
          this.handlers.pageCaptured,
        );
        await startPublicationConsumer(
          publicationChannel,
          this.handlers.publicationEvent,
        );

        await this.waitForConnectionOrShutdown(connection, signal);
      } catch (error) {
        if (!signal.aborted) {
          console.error("Search consumer connection failed", error);
        }
      } finally {
        await pageCapturedChannel?.close().catch(() => undefined);
        await publicationChannel?.close().catch(() => undefined);
        await connection?.close().catch(() => undefined);
      }

      await this.waitForReconnectDelay(signal);
    }
  }

  private waitForConnectionOrShutdown(
    connection: amqp.ChannelModel,
    signal: AbortSignal,
  ): Promise<void> {
    return new Promise((resolve) => {
      const finish = () => {
        signal.removeEventListener("abort", finish);
        connection.removeListener("close", finish);
        connection.removeListener("error", finish);
        resolve();
      };

      connection.once("close", finish);
      connection.once("error", finish);
      signal.addEventListener("abort", finish, { once: true });

      if (signal.aborted) {
        finish();
      }
    });
  }

  private waitForReconnectDelay(signal: AbortSignal): Promise<void> {
    if (signal.aborted) {
      return Promise.resolve();
    }

    return new Promise((resolve) => {
      const finish = () => {
        clearTimeout(timeout);
        signal.removeEventListener("abort", finish);
        resolve();
      };

      const timeout = setTimeout(
        finish,
        this.settings.reconnectDelayMilliseconds,
      );

      signal.addEventListener("abort", finish, { once: true });

      if (signal.aborted) {
        finish();
      }
    });
  }
}

export { SearchWorker };
