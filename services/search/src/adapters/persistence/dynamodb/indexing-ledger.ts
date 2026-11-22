import { randomUUID } from "node:crypto";
import { GetCommand, UpdateCommand } from "@aws-sdk/lib-dynamodb";
import type { DynamoDBDocumentClient } from "@aws-sdk/lib-dynamodb";
import type { IndexingOutcome } from "../../../domain.js";
import type {
  IndexingClaimResult,
  IndexingLedger,
  SnapshotClaim,
} from "../../../ports/indexing-ledger.js";

type TerminalOutcome = Extract<
  IndexingOutcome,
  "INDEXED" | "UNSUPPORTED" | "FAILED"
>;

interface LedgerItem {
  archiveId?: string;
  snapshotId?: string;
  state?: IndexingOutcome;
  claimToken?: string;
  leaseUntil?: number;
  attempts?: number;
}

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
  ): Promise<IndexingClaimResult> {
    if (!archiveId || !snapshotId || !messageId) {
      throw new Error("archiveId, snapshotId, and messageId must not be empty");
    }
    if (leaseDurationSeconds <= 0) {
      throw new Error("lease duration must be positive");
    }

    const now = this.clock() / 1000;
    const token = randomUUID();

    try {
      const response = await this.client.send(
        new UpdateCommand({
          TableName: this.tableName,
          Key: { snapshotId },
          UpdateExpression:
            "SET #archive = :archive, #state = :processing, #token = :token, #lease = :lease, #attempts = if_not_exists(#attempts, :zero) + :one, #message = :message, #updated = :now",
          ConditionExpression:
            "attribute_not_exists(#snapshot) OR #state = :pending OR (#state = :processing AND #lease <= :now)",
          ExpressionAttributeNames: {
            "#snapshot": "snapshotId",
            "#archive": "archiveId",
            "#state": "state",
            "#token": "claimToken",
            "#lease": "leaseUntil",
            "#attempts": "attempts",
            "#message": "lastMessageId",
            "#updated": "updatedAt",
          },
          ExpressionAttributeValues: {
            ":archive": archiveId,
            ":processing": "PROCESSING",
            ":pending": "PENDING",
            ":token": token,
            ":lease": now + leaseDurationSeconds,
            ":zero": 0,
            ":one": 1,
            ":message": messageId,
            ":now": now,
          },
          ReturnValues: "ALL_NEW",
        }),
      );

      const attributes = response.Attributes as LedgerItem | undefined;
      const attempts = attributes?.attempts;

      if (attempts === undefined) {
        throw new Error("DynamoDB did not return the claimed indexing entry");
      }

      return {
        status: "CLAIMED",
        claim: { archiveId, snapshotId, token, attempts },
      };
    } catch (error) {
      if (
        !(error instanceof Error) ||
        error.name !== "ConditionalCheckFailedException"
      ) {
        throw error;
      }

      const response = await this.client.send(
        new GetCommand({
          TableName: this.tableName,
          Key: { snapshotId },
          ConsistentRead: true,
        }),
      );
      const item = response.Item as LedgerItem | undefined;

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

      return {
        status: "BUSY",
        leaseUntil: item.leaseUntil ?? now,
      };
    }
  }

  async complete(
    claim: SnapshotClaim,
    outcome: TerminalOutcome,
    reasonCode?: string,
  ): Promise<void> {
    const now = this.clock() / 1000;
    await this.client
      .send(
        new UpdateCommand({
          TableName: this.tableName,
          Key: { snapshotId: claim.snapshotId },
          UpdateExpression:
            reasonCode === undefined
              ? "SET #state = :outcome, #updated = :now REMOVE #token, #lease"
              : "SET #state = :outcome, #reason = :reason, #updated = :now REMOVE #token, #lease",
          ConditionExpression:
            "#archive = :archive AND #state = :processing AND #token = :token",
          ExpressionAttributeNames: {
            "#archive": "archiveId",
            "#state": "state",
            "#token": "claimToken",
            "#lease": "leaseUntil",
            "#updated": "updatedAt",
            ...(reasonCode === undefined ? {} : { "#reason": "reasonCode" }),
          },
          ExpressionAttributeValues: {
            ":archive": claim.archiveId,
            ":processing": "PROCESSING",
            ":token": claim.token,
            ":outcome": outcome,
            ":now": now,
            ...(reasonCode === undefined ? {} : { ":reason": reasonCode }),
          },
        }),
      )
      .catch((error: unknown) => {
        if (
          error instanceof Error &&
          error.name === "ConditionalCheckFailedException"
        ) {
          throw new IndexingClaimLostError(claim.snapshotId);
        }
        throw error;
      });
  }

  async release(claim: SnapshotClaim, reason: string): Promise<void> {
    const now = this.clock() / 1000;
    await this.client
      .send(
        new UpdateCommand({
          TableName: this.tableName,
          Key: { snapshotId: claim.snapshotId },
          UpdateExpression:
            "SET #state = :pending, #reason = :reason, #updated = :now REMOVE #token, #lease",
          ConditionExpression:
            "#archive = :archive AND #state = :processing AND #token = :token",
          ExpressionAttributeNames: {
            "#archive": "archiveId",
            "#state": "state",
            "#token": "claimToken",
            "#lease": "leaseUntil",
            "#reason": "lastError",
            "#updated": "updatedAt",
          },
          ExpressionAttributeValues: {
            ":archive": claim.archiveId,
            ":processing": "PROCESSING",
            ":pending": "PENDING",
            ":token": claim.token,
            ":reason": reason.slice(0, 1000),
            ":now": now,
          },
        }),
      )
      .catch((error: unknown) => {
        if (
          error instanceof Error &&
          error.name === "ConditionalCheckFailedException"
        ) {
          throw new IndexingClaimLostError(claim.snapshotId);
        }
        throw error;
      });
  }
}

export {
  DynamoDBIndexingLedger,
  IndexingClaimLostError,
  IndexingIdentityConflictError,
};
