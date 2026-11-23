import type {
  TerminalIndexingOutcome,
  SnapshotLedgerEntry,
} from "../domain.js";

interface SnapshotClaim {
  archiveId: string;
  snapshotId: string;
  token: string;
  attempts: number;
}

type IndexingClaimResult =
  | { status: "CLAIMED"; claim: SnapshotClaim }
  | { status: "BUSY"; leaseUntil: number }
  | {
      status: "TERMINAL";
      outcome: TerminalIndexingOutcome;
    };

interface IndexingLedger {
  claim(
    archiveId: string,
    snapshotId: string,
    messageId: string,
    leaseDurationSeconds?: number,
    maxAttempts?: number,
  ): Promise<IndexingClaimResult>;

  complete(
    claim: SnapshotClaim,
    outcome: TerminalIndexingOutcome,
    reasonCode?: string,
  ): Promise<void>;

  release(claim: SnapshotClaim, reason: string): Promise<void>;

  listByArchive(archiveId: string): Promise<SnapshotLedgerEntry[]>;
}

export type { IndexingClaimResult, IndexingLedger, SnapshotClaim };
