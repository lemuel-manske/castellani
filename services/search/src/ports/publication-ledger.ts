import type {
  CompensationDecision,
  PublicationFacts,
  PublicationIdentity,
} from "../domain.js";

interface PublicationLedger {
  get(archiveId: string): Promise<PublicationFacts>;
  recordPublicationDecision(identity: PublicationIdentity): Promise<void>;
  recordReplayPublished(identity: PublicationIdentity): Promise<void>;
  recordCompensationDecision(decision: CompensationDecision): Promise<void>;
}

export type { PublicationLedger };
