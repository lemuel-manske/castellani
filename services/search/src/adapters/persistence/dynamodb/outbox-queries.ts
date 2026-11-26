import type { OutboxEntry } from "../../../ports/outbox.js";

import { OUTBOX } from "./tables.js";

/** Builds the conditional outbox insert shared by all transactional emitters. */
function putOutboxEntry(outboxEntry: OutboxEntry) {
  return {
    Put: {
      TableName: OUTBOX,
      Item: {
        messageId: outboxEntry.messageId,
        correlationId: outboxEntry.correlationId,
        type: outboxEntry.type,
        occurredAt: outboxEntry.occurredAt,
        envelope: outboxEntry.envelope,
        cleanupRequired: outboxEntry.cleanupRequired,
        state: "PENDING",
        attempts: 0,
        createdAt: outboxEntry.occurredAt,
      },
      ConditionExpression: "attribute_not_exists(messageId)",
    },
  };
}

export { putOutboxEntry };
