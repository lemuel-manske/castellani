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

class IndexingClaimLostError extends Error {
  constructor(snapshotId: string) {
    super(`indexing claim was lost for snapshot ${snapshotId}`);

    this.name = "IndexingClaimLostError";
  }
}

class IndexingIdentityConflictError extends Error {
  constructor(snapshotId: string) {
    super(
      `snapshot identity conflicts with existing ledger entry: ${snapshotId}`,
    );

    this.name = "IndexingIdentityConflictError";
  }
}

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

export { IndexingClaimLostError, IndexingIdentityConflictError };

export type { IndexingClaimResult, IndexingLedger, SnapshotClaim };
