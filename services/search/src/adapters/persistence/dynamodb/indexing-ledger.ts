import { randomUUID } from "node:crypto";
import type { DynamoDBDocumentClient } from "@aws-sdk/lib-dynamodb";
import {
  INDEXING_CLAIM_STATUS,
  INDEXING_OUTCOME,
  type SnapshotLedgerEntry,
  type TerminalIndexingOutcome,
} from "../../../domain/index.js";
import {
  IndexingClaimLostError,
  IndexingIdentityConflictError,
} from "../../../ports/indexing-ledger.js";
import type {
  IndexingClaimResult,
  IndexingLedger,
  SnapshotClaim,
} from "../../../ports/indexing-ledger.js";
import {
  claimIndexingEntry,
  completeIndexingEntry,
  exhaustIndexingEntry,
  getIndexingEntry,
  listIndexingEntriesByArchive,
  releaseIndexingEntry,
} from "./indexing-ledger-queries.js";
import { isConditionalCheckFailure } from "./error-handling.js";

const DEFAULT_MAX_ATTEMPTS = 5;

class DynamoDBIndexingLedger implements IndexingLedger {
  constructor(private readonly client: DynamoDBDocumentClient) {}

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

    const now = Date.now() / 1000;
    const token = randomUUID();

    try {
      const item = await claimIndexingEntry(this.client, {
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
        status: INDEXING_CLAIM_STATUS.CLAIMED,
        claim: {
          archiveId,
          snapshotId,
          messageId,
          token,
          attempts: item.attempts,
        },
      };
    } catch (error) {
      if (
        !(error instanceof Error) ||
        error.name !== "ConditionalCheckFailedException"
      ) {
        throw error;
      }

      const item = await getIndexingEntry(this.client, snapshotId);

      if (item === undefined) {
        throw error;
      }

      if (item.archiveId !== archiveId) {
        throw new IndexingIdentityConflictError(snapshotId);
      }

      if (
        item.state === INDEXING_OUTCOME.INDEXED ||
        item.state === INDEXING_OUTCOME.UNSUPPORTED ||
        item.state === INDEXING_OUTCOME.FAILED
      ) {
        return { status: INDEXING_CLAIM_STATUS.TERMINAL, outcome: item.state };
      }

      const leaseExpired =
        item.state === INDEXING_OUTCOME.PENDING ||
        (item.state === INDEXING_OUTCOME.PROCESSING &&
          item.leaseUntil !== undefined &&
          item.leaseUntil <= now);

      const attempts = item.attempts;

      if (leaseExpired && attempts !== undefined && attempts >= maxAttempts) {
        try {
          await exhaustIndexingEntry(this.client, {
            archiveId,
            snapshotId,
            messageId,
            now,
            attempts,
            maxAttempts,
          });

          return {
            status: INDEXING_CLAIM_STATUS.TERMINAL,
            outcome: INDEXING_OUTCOME.FAILED,
          };
        } catch (exhaustionError) {
          if (isConditionalCheckFailure(exhaustionError)) {
            throw exhaustionError;
          }

          const current = await getIndexingEntry(this.client, snapshotId);

          if (current === undefined) {
            throw exhaustionError;
          }

          if (current.archiveId !== archiveId) {
            throw new IndexingIdentityConflictError(snapshotId);
          }

          if (
            current.state === INDEXING_OUTCOME.INDEXED ||
            current.state === INDEXING_OUTCOME.UNSUPPORTED ||
            current.state === INDEXING_OUTCOME.FAILED
          ) {
            return {
              status: INDEXING_CLAIM_STATUS.TERMINAL,
              outcome: current.state,
            };
          }

          return {
            status: INDEXING_CLAIM_STATUS.BUSY,
            leaseUntil: current.leaseUntil ?? now,
          };
        }
      }

      return {
        status: INDEXING_CLAIM_STATUS.BUSY,
        leaseUntil: item.leaseUntil ?? now,
      };
    }
  }

  async listByArchive(archiveId: string): Promise<SnapshotLedgerEntry[]> {
    if (!archiveId) {
      throw new Error("archiveId must not be empty");
    }

    return listIndexingEntriesByArchive(this.client, archiveId);
  }

  async complete(
    claim: SnapshotClaim,
    outcome: TerminalIndexingOutcome,
    reasonCode?: string,
  ): Promise<void> {
    try {
      await completeIndexingEntry(this.client, {
        claim,
        outcome,
        ...(reasonCode === undefined ? {} : { reasonCode }),
        now: Date.now() / 1000,
      });
    } catch (error) {
      if (isConditionalCheckFailure(error)) {
        throw new IndexingClaimLostError(claim.snapshotId);
      }

      throw error;
    }
  }

  async release(claim: SnapshotClaim, reason: string): Promise<void> {
    try {
      await releaseIndexingEntry(this.client, {
        claim,
        reason: reason.slice(0, 1000),
        now: Date.now() / 1000,
      });
    } catch (error) {
      if (isConditionalCheckFailure(error)) {
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
