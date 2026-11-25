import type { ClaimedOutboxMessage } from "./outbox.js";

/** Publishes claimed SearchCompensated outbox messages to the broker. */
interface CompensationPublisher {
  publish(message: ClaimedOutboxMessage): Promise<void>;
}

export type { CompensationPublisher };
