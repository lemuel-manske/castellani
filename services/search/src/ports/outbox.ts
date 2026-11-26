const OUTBOX_STATE = {
  PENDING: "PENDING",
  CLAIMED: "CLAIMED",
  PUBLISHED: "PUBLISHED",
} as const;

interface OutboxEntry {
  messageId: string;
  correlationId: string;
  type: string;
  occurredAt: string;
  envelope: string;
  cleanupRequired: boolean;
}

interface ClaimedOutboxMessage extends OutboxEntry {
  leaseToken: string;
}

interface Outbox {
  get(messageId: string): Promise<OutboxEntry | undefined>;

  claim(
    leaseDurationSeconds: number,
  ): Promise<ClaimedOutboxMessage | undefined>;

  completeCleanup(message: ClaimedOutboxMessage): Promise<boolean>;

  confirm(message: ClaimedOutboxMessage): Promise<void>;
}

export { OUTBOX_STATE };

export type { ClaimedOutboxMessage, Outbox, OutboxEntry };
