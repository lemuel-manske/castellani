import type { IndexingOutcome } from "../domain.js";

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
      outcome: Extract<IndexingOutcome, "INDEXED" | "UNSUPPORTED" | "FAILED">;
    };

interface IndexingLedger {
  claim(
    archiveId: string,
    snapshotId: string,
    messageId: string,
    leaseDurationSeconds: number,
  ): Promise<IndexingClaimResult>;
  complete(
    claim: SnapshotClaim,
    outcome: Extract<IndexingOutcome, "INDEXED" | "UNSUPPORTED" | "FAILED">,
    reasonCode?: string,
  ): Promise<void>;
  release(claim: SnapshotClaim, reason: string): Promise<void>;
}

export type { IndexingClaimResult, IndexingLedger, SnapshotClaim };
