import { randomUUID } from "node:crypto";
import type { IndexingOutcome } from "../../../domain.js";
import type {
  IndexingClaimResult,
  IndexingLedger,
  SnapshotClaim,
} from "../../../ports/indexing-ledger.js";
import { DynamoDBIndexingLedgerQueries } from "./indexing-ledger-queries.js";

type TerminalOutcome = Extract<
  IndexingOutcome,
  "INDEXED" | "UNSUPPORTED" | "FAILED"
>;

class IndexingClaimLostError extends Error {
  constructor(snapshotId: string) {
    super(`indexing claim was lost for snapshot ${snapshotId}`);
    this.name = "IndexingClaimLostError";
  }
}

class IndexingIdentityConflictError extends Error {
  constructor(snapshotId: string) {
    super(`snapshot identity conflicts with existing ledger entry: ${snapshotId}`);
    this.name = "IndexingIdentityConflictError";
  }
}

class DynamoDBIndexingLedger implements IndexingLedger {
  private readonly queries: DynamoDBIndexingLedgerQueries;

  constructor(
    client: ConstructorParameters<typeof DynamoDBIndexingLedgerQueries>[0],
    tableName: string,
    private readonly clock: () => number = Date.now,
  ) {
    this.queries = new DynamoDBIndexingLedgerQueries(client, tableName);
  }

  async claim(
    archiveId: string,
    snapshotId: string,
    messageId: string,
    leaseDurationSeconds: number,
  ): Promise<IndexingClaimResult> {
    if (!archiveId || !snapshotId || !messageId) {
      throw new Error("archiveId, snapshotId, and messageId must not be empty");
    }
    if (!Number.isFinite(leaseDurationSeconds) || leaseDurationSeconds <= 0) {
      throw new Error("lease duration must be positive");
    }

    const now = this.clock() / 1000;
    const token = randomUUID();

    try {
      const item = await this.queries.claim({
        archiveId,
        snapshotId,
        messageId,
        token,
        now,
        leaseUntil: now + leaseDurationSeconds,
      });

      if (item.attempts === undefined) {
        throw new Error("DynamoDB did not return the claimed indexing entry");
      }

      return {
        status: "CLAIMED",
        claim: { archiveId, snapshotId, token, attempts: item.attempts },
      };
    } catch (error) {
      if (
        !(error instanceof Error) ||
        error.name !== "ConditionalCheckFailedException"
      ) {
        throw error;
      }

      const item = await this.queries.get(snapshotId);
      if (item === undefined) {
        throw error;
      }
      if (item.archiveId !== archiveId) {
        throw new IndexingIdentityConflictError(snapshotId);
      }

      if (
        item.state === "INDEXED" ||
        item.state === "UNSUPPORTED" ||
        item.state === "FAILED"
      ) {
        return { status: "TERMINAL", outcome: item.state };
      }

      return { status: "BUSY", leaseUntil: item.leaseUntil ?? now };
    }
  }

  async complete(
    claim: SnapshotClaim,
    outcome: TerminalOutcome,
    reasonCode?: string,
  ): Promise<void> {
    try {
      await this.queries.complete({
        claim,
        outcome,
        reasonCode,
        now: this.clock() / 1000,
      });
    } catch (error) {
      if (
        error instanceof Error &&
        error.name === "ConditionalCheckFailedException"
      ) {
        throw new IndexingClaimLostError(claim.snapshotId);
      }
      throw error;
    }
  }

  async release(claim: SnapshotClaim, reason: string): Promise<void> {
    try {
      await this.queries.release({
        claim,
        reason: reason.slice(0, 1000),
        now: this.clock() / 1000,
      });
    } catch (error) {
      if (
        error instanceof Error &&
        error.name === "ConditionalCheckFailedException"
      ) {
        throw new IndexingClaimLostError(claim.snapshotId);
      }
      throw error;
    }
  }
}

export {
  DynamoDBIndexingLedger,
  IndexingClaimLostError,
  IndexingIdentityConflictError,
};
