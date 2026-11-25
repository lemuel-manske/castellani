import type {
  CompensationDecision,
  PublicationFacts,
  PublicationIdentity,
} from "../domain.js";

import type { OutboxEntry } from "./outbox.js";

interface PublicationLedger {
  get(archiveId: string): Promise<PublicationFacts>;

  recordPublicationDecision(
    identity: PublicationIdentity,
    messageId: string,
  ): Promise<void>;

  recordReplayPublished(
    identity: PublicationIdentity,
    messageId: string,
  ): Promise<void>;

  recordCompensationDecision(
    decision: CompensationDecision,
    messageId: string,
    outboxEntry: OutboxEntry,
  ): Promise<void>;
}

export type { PublicationLedger };
