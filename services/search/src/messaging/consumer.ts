import { type Channel, type ChannelModel, type ConfirmChannel, type ConsumeMessage, connect } from "amqplib";

import { RejectedEventError } from "../indexing/indexer.js";
import { type Contracts, InvalidMessageError } from "./contracts.js";

export const SEARCH_QUEUE = "castellani.search";
export const RETRY_QUEUE = "castellani.search.retry";
export const DEAD_QUEUE = "castellani.search.dead";
export const ATTEMPT_HEADER = "x-search-attempt";

/** Event types this service consumes, bound by routing key. */
export const CONSUMED_TYPES = [
  "PageCaptured",
  "ArchivePublicationDecided",
  "ArchivePublished",
  "ArchiveCompensationDecided",
] as const;

export type ConsumedType = (typeof CONSUMED_TYPES)[number];

export type Handlers = Record<ConsumedType, (message: unknown) => Promise<unknown>>;

/** Envelope of an event this service emits; routed by `type`. */
export type Publication = { messageId: string; type: string } & Record<string, unknown>;

export type ConsumerOptions = {
  url: string;
  exchange: string;
  prefetch: number;
  maxDeliveryAttempts: number;
  retryDelayMs: number;
};

type Logger = {
  info(object: object, message: string): void;
  warn(object: object, message: string): void;
  error(object: object, message: string): void;
};

/**
 * Durable, manually acknowledged consumer. Retry and dead-letter queues belong
 * to Search and are addressed through the default exchange, so a retried event
 * returns only to this service's queue instead of fanning out again to every
 * consumer bound to the event type.
 */
export class Consumer {
  private connection: ChannelModel | undefined;
  private publisher: ConfirmChannel | undefined;
  private inFlight = new Set<Promise<void>>();
  private stopping = false;
  connected = false;

  constructor(
    private readonly options: ConsumerOptions,
    private readonly contracts: Contracts,
    private readonly handlers: Handlers,
    private readonly log: Logger,
  ) {}

  /** Consumes until `stop()`, reconnecting with capped backoff. */
  async run(): Promise<void> {
    let backoffMs = 500;

    while (!this.isStopping()) {
      try {
        await this.session();
        backoffMs = 500;
      } catch (error) {
        this.connected = false;

        if (this.isStopping()) {
          break;
        }

        this.log.warn({ err: error, backoffMs }, "RabbitMQ session ended; reconnecting");
        await sleep(backoffMs);
        backoffMs = Math.min(backoffMs * 2, 15_000);
      }
    }
  }

  /** Read through a method: `stop()` flips the flag concurrently with `run()`. */
  private isStopping(): boolean {
    return this.stopping;
  }

  /**
   * Publishes an event to the exchange and resolves once the broker confirms
   * it. Handlers call this before their delivery is acknowledged, so an
   * unconfirmed publication leaves the inbound message to be redelivered.
   */
  publish(message: Publication): Promise<void> {
    const publisher = this.publisher;

    if (publisher === undefined || !this.connected) {
      return Promise.reject(new Error("RabbitMQ is not connected"));
    }

    return new Promise((resolve, reject) => {
      publisher.publish(
        this.options.exchange,
        message.type,
        Buffer.from(JSON.stringify(message)),
        { persistent: true, contentType: "application/json", messageId: message.messageId, mandatory: true },
        (error: unknown) => {
          if (error) {
            reject(error instanceof Error ? error : new Error(`broker did not confirm ${message.type}`));
          } else {
            resolve();
          }
        },
      );
    });
  }

  async stop(): Promise<void> {
    this.stopping = true;
    await Promise.allSettled(this.inFlight);
    await this.connection?.close().catch(() => undefined);
    this.connected = false;
  }

  private async session(): Promise<void> {
    const connection = await connect(this.options.url);
    this.connection = connection;

    const closed = new Promise<void>((resolve, reject) => {
      connection.on("close", () => {
        if (this.isStopping()) {
          resolve();
        } else {
          reject(new Error("connection closed"));
        }
      });
      connection.on("error", (error: unknown) => {
        this.log.warn({ err: error }, "RabbitMQ connection error");
      });
    });

    const channel = await connection.createChannel();
    const publisher = await connection.createConfirmChannel();
    this.publisher = publisher;

    // `mandatory` publications that no queue accepts are returned here;
    // log them, since an unroutable acknowledgment would otherwise vanish.
    publisher.on("return", (returned: ConsumeMessage) => {
      this.log.error({ routingKey: returned.fields.routingKey }, "published event was unroutable");
    });

    await declareTopology(channel, this.options);
    await channel.prefetch(this.options.prefetch);

    await channel.consume(SEARCH_QUEUE, (delivery) => {
      if (delivery === null) {
        return;
      }

      const work = this.process(channel, publisher, delivery).catch((error: unknown) => {
        this.log.error({ err: error }, "failed to settle delivery");
      });

      this.inFlight.add(work);
      void work.finally(() => {
        this.inFlight.delete(work);
      });
    });

    this.connected = true;
    this.log.info({ queue: SEARCH_QUEUE }, "consuming");

    await closed;
  }

  private async process(channel: Channel, publisher: ConfirmChannel, delivery: ConsumeMessage): Promise<void> {
    const attempt = attemptOf(delivery);
    const messageId = String(delivery.properties.messageId ?? "");

    try {
      const message: unknown = JSON.parse(delivery.content.toString("utf8"));
      const { type } = this.contracts.envelopeOf(message);

      if (!isConsumedType(type)) {
        throw new InvalidMessageError(`unexpected message type ${type}`);
      }

      const result = await this.handlers[type](message);
      this.log.info({ messageId, type, attempt, result }, "handled event");
      channel.ack(delivery);

      return;
    } catch (error) {
      if (error instanceof SyntaxError || error instanceof InvalidMessageError || error instanceof RejectedEventError) {
        this.log.warn({ err: error, messageId }, "rejecting message to DLQ");
        channel.nack(delivery, false, false);

        return;
      }

      if (attempt >= this.options.maxDeliveryAttempts) {
        // Exhausted transport retries. The ledger keeps the snapshot
        // recoverable; manifest reconciliation owns the remaining work.
        this.log.error({ err: error, attempt }, "delivery attempts exhausted; dead-lettering");
        channel.nack(delivery, false, false);

        return;
      }

      this.log.warn({ err: error, attempt }, "scheduling retry");

      await publishConfirmed(publisher, RETRY_QUEUE, delivery, attempt + 1);
      channel.ack(delivery);
    }
  }
}

export async function declareTopology(channel: Channel, options: ConsumerOptions): Promise<void> {
  await channel.assertExchange(options.exchange, "topic", { durable: true });

  await channel.assertQueue(DEAD_QUEUE, { durable: true });

  await channel.assertQueue(RETRY_QUEUE, {
    durable: true,
    arguments: {
      "x-message-ttl": options.retryDelayMs,
      "x-dead-letter-exchange": "",
      "x-dead-letter-routing-key": SEARCH_QUEUE,
    },
  });

  await channel.assertQueue(SEARCH_QUEUE, {
    durable: true,
    arguments: {
      "x-dead-letter-exchange": "",
      "x-dead-letter-routing-key": DEAD_QUEUE,
    },
  });

  for (const type of CONSUMED_TYPES) {
    await channel.bindQueue(SEARCH_QUEUE, options.exchange, type);
  }
}

function publishConfirmed(
  channel: ConfirmChannel,
  queue: string,
  delivery: ConsumeMessage,
  attempt: number,
): Promise<void> {
  const properties = delivery.properties as {
    contentType?: string;
    messageId?: string;
    headers?: Record<string, unknown>;
  };

  return new Promise((resolve, reject) => {
    channel.sendToQueue(
      queue,
      delivery.content,
      {
        persistent: true,
        contentType: properties.contentType ?? "application/json",
        ...(properties.messageId ? { messageId: properties.messageId } : {}),
        headers: { ...properties.headers, [ATTEMPT_HEADER]: attempt },
      },
      (error: unknown) => {
        if (error) {
          reject(error instanceof Error ? error : new Error("broker did not confirm the retry publication"));
        } else {
          resolve();
        }
      },
    );
  });
}

function isConsumedType(type: string): type is ConsumedType {
  return (CONSUMED_TYPES as readonly string[]).includes(type);
}

function attemptOf(delivery: ConsumeMessage): number {
  const headers = delivery.properties.headers as Record<string, unknown> | undefined;
  const value = Number(headers?.[ATTEMPT_HEADER] ?? 1);

  return Number.isSafeInteger(value) && value > 0 ? value : 1;
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
