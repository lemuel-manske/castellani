import { Wakeable } from "../support/wakeable.js";

/** Envelope of an event Search emits; routed by `type`. */
export type OutgoingEvent = {
  messageId: string;
  correlationId: string;
  type: string;
  version: 1;
  occurredAt: string;
  payload: Record<string, unknown>;
};

export type OutboxClaim = { messageId: string; token: string; event: OutgoingEvent; attempts: number };

/**
 * Durable outbox (`search_outbox`). Records are written in the same
 * transaction as the state they report (see `ArchiveVisibility`); this port
 * only dispatches them.
 */
export interface OutboxStore {
  /** Message IDs not yet confirmed by the broker. */
  pending(limit: number): Promise<string[]>;
  /** Claims a pending record with a lease; undefined if sent, leased or backing off. */
  claim(messageId: string, now: Date): Promise<OutboxClaim | undefined>;
  /** Marks the record sent, if the claim is still held. */
  markSent(claim: OutboxClaim, now: Date): Promise<void>;
  /** Leaves the record pending and claimable again at `retryAt`. */
  release(claim: OutboxClaim, reason: string, retryAt: Date, now: Date): Promise<void>;
}

export interface EventPublisher {
  /** Publishes an event and resolves once the broker confirms a queue accepted it. */
  publish(event: OutgoingEvent): Promise<void>;
}

export type DispatcherOptions = { intervalMs: number; maxBackoffMs?: number };

type Logger = { warn(object: object, message: string): void };

/**
 * Publishes outbox records with confirms and their stable `messageId`. A
 * record is marked sent only after the broker confirms it was routed; a
 * failed or unroutable publication stays pending and is retried with backoff.
 * Claims make concurrent dispatchers (replicas) publish each record once in
 * the normal case; a duplicate after a lost lease keeps the same `messageId`,
 * which consumers deduplicate.
 */
export class OutboxDispatcher {
  private readonly sleeper = new Wakeable();
  private readonly maxBackoffMs: number;
  private stopping = false;

  constructor(
    private readonly store: OutboxStore,
    private readonly publisher: EventPublisher,
    private readonly options: DispatcherOptions,
    private readonly log: Logger,
    private readonly clock: () => Date = () => new Date(),
  ) {
    this.maxBackoffMs = options.maxBackoffMs ?? 60_000;
  }

  /** Dispatches promptly, e.g. right after a record was enqueued. */
  wake(): void {
    this.sleeper.wake();
  }

  async run(): Promise<void> {
    while (!this.isStopping()) {
      try {
        await this.dispatchPending();
      } catch (error) {
        this.log.warn({ err: error }, "outbox dispatch pass failed");
      }

      await this.sleeper.sleep(this.options.intervalMs);
    }
  }

  stop(): void {
    this.stopping = true;
    this.sleeper.wake();
  }

  /** One pass over pending records. Returns how many were sent. */
  async dispatchPending(): Promise<number> {
    let sent = 0;

    for (const messageId of await this.store.pending(100)) {
      const claim = await this.store.claim(messageId, this.clock());

      if (claim === undefined) {
        continue;
      }

      try {
        await this.publisher.publish(claim.event);
      } catch (error) {
        const reason = error instanceof Error ? error.message : String(error);
        const backoffMs = Math.min(1_000 * 2 ** claim.attempts, this.maxBackoffMs);
        const now = this.clock();

        this.log.warn({ err: error, messageId, attempts: claim.attempts }, "outbox publication failed; retrying");
        await this.store.release(claim, reason, new Date(now.getTime() + backoffMs), now);
        continue;
      }

      await this.store.markSent(claim, this.clock());
      sent += 1;
    }

    return sent;
  }

  /** Read through a method: `stop()` flips the flag concurrently with `run()`. */
  private isStopping(): boolean {
    return this.stopping;
  }
}
