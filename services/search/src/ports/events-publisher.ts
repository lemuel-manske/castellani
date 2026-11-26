import type { ClaimedOutboxMessage } from "./outbox.js";

/** Publishes claimed outbox events to the broker. */
interface EventsPublisher {
  publish(message: ClaimedOutboxMessage): Promise<void>;
}

export type { EventsPublisher };
