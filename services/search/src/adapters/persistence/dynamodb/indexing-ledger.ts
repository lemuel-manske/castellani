import { randomUUID } from "node:crypto";
import type { DynamoDBDocumentClient } from "@aws-sdk/lib-dynamodb";
import type { IndexingOutcome, SnapshotLedgerEntry } from "../../../domain.js";
import type {
  IndexingClaimResult,
  IndexingLedger,
  SnapshotClaim,
} from "../../../ports/indexing-ledger.js";
import {
  claimIndexingEntry,
  completeIndexingEntry,
  exhaustIndexingEntry,
  getIndexingEntry,\n  listIndexingEntriesByArchive,
  releaseIndexingEntry,
} from "./indexing-ledger-queries.js";

type TerminalOutcome = Extract<
  IndexingOutcome,
  "INDEXED" | "UNSUPPORTED" | "FAILED"
>;

const DEFAULT_MAX_ATTEMPTS = 5;

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

class DynamoDBIndexingLedger implements IndexingLedger {
  constructor(
    private readonly client: DynamoDBDocumentClient,
    private readonly tableName: string,
    private readonly clock: () => number = Date.now,
  ) {
    if (!tableName.trim()) {
      throw new Error("indexing ledger table name must not be empty");
    }
  }

  async claim(
    archiveId: string,
    snapshotId: string,
    messageId: string,
    leaseDurationSeconds: number,
    maxAttempts = DEFAULT_MAX_ATTEMPTS,
  ): Promise<IndexingClaimResult> {
    if (!archiveId || !snapshotId || !messageId) {
      throw new Error("archiveId, snapshotId, and messageId must not be empty");
    }

    if (!Number.isFinite(leaseDurationSeconds) || leaseDurationSeconds <= 0) {
      throw new Error("lease duration must be positive");
    }

    if (!Number.isSafeInteger(maxAttempts) || maxAttempts <= 0) {
      throw new Error("maximum indexing attempts must be a positive integer");
    }

    const now = this.clock() / 1000;
    const token = randomUUID();

    try {
      const item = await claimIndexingEntry(this.client, this.tableName, {
        archiveId,
        snapshotId,
        messageId,
        token,
        now,
        leaseUntil: now + leaseDurationSeconds,
        maxAttempts,
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

      const item = await getIndexingEntry(
        this.client,
        this.tableName,
        snapshotId,
      );

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

      const leaseExpired =
        item.state === "PENDING" ||
        (item.state === "PROCESSING" &&
          item.leaseUntil !== undefined &&
          item.leaseUntil <= now);
      const attempts = item.attempts;

      if (leaseExpired && attempts !== undefined && attempts >= maxAttempts) {
        try {
          await exhaustIndexingEntry(this.client, this.tableName, {
            archiveId,
            snapshotId,
            now,
            attempts,
            maxAttempts,
          });
          return { status: "TERMINAL", outcome: "FAILED" };
        } catch (exhaustionError) {
          if (
            !(exhaustionError instanceof Error) ||
            exhaustionError.name !== "ConditionalCheckFailedException"
          ) {
            throw exhaustionError;
          }

          const current = await getIndexingEntry(
            this.client,
            this.tableName,
            snapshotId,
          );

          if (current?.archiveId !== archiveId) {
            throw new IndexingIdentityConflictError(snapshotId);
          }

          if (
            current?.state === "INDEXED" ||
            current?.state === "UNSUPPORTED" ||
            current?.state === "FAILED"
          ) {
            return { status: "TERMINAL", outcome: current.state };
          }

          return {
            status: "BUSY",
            leaseUntil: current?.leaseUntil ?? now,
          };
        }
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
      await completeIndexingEntry(this.client, this.tableName, {
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
      await releaseIndexingEntry(this.client, this.tableName, {
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
