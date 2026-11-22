import {
  GetCommand,
  UpdateCommand,
} from "@aws-sdk/lib-dynamodb";
import type { DynamoDBDocumentClient } from "@aws-sdk/lib-dynamodb";
import type { IndexingOutcome } from "../../../domain.js";
import type { SnapshotClaim } from "../../../ports/indexing-ledger.js";

type TerminalOutcome = Extract<
  IndexingOutcome,
  "INDEXED" | "UNSUPPORTED" | "FAILED"
>;

interface LedgerItem {
  archiveId?: string;
  snapshotId?: string;
  state?: IndexingOutcome;
  leaseUntil?: number;
  attempts?: number;
}

interface ClaimQuery {
  archiveId: string;
  snapshotId: string;
  messageId: string;
  token: string;
  now: number;
  leaseUntil: number;
}

interface CompletionQuery {
  claim: SnapshotClaim;
  outcome: TerminalOutcome;
  reasonCode?: string;
  now: number;
}

interface ReleaseQuery {
  claim: SnapshotClaim;
  reason: string;
  now: number;
}

/**
 * Contains the DynamoDB access expressions used by the indexing ledger.
 * State transitions and interpretation of query results stay in the ledger.
 */
class DynamoDBIndexingLedgerQueries {
  constructor(
    private readonly client: DynamoDBDocumentClient,
    private readonly tableName: string,
  ) {
    if (!tableName.trim()) {
      throw new Error("indexing ledger table name must not be empty");
    }
  }

  async claim(input: ClaimQuery): Promise<LedgerItem> {
    const response = await this.client.send(
      new UpdateCommand({
        TableName: this.tableName,
        Key: { snapshotId: input.snapshotId },
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
          ":archive": input.archiveId,
          ":processing": "PROCESSING",
          ":pending": "PENDING",
          ":token": input.token,
          ":lease": input.leaseUntil,
          ":zero": 0,
          ":one": 1,
          ":message": input.messageId,
          ":now": input.now,
        },
        ReturnValues: "ALL_NEW",
      }),
    );

    return (response.Attributes ?? {}) as LedgerItem;
  }

  async get(snapshotId: string): Promise<LedgerItem | undefined> {
    const response = await this.client.send(
      new GetCommand({
        TableName: this.tableName,
        Key: { snapshotId },
        ConsistentRead: true,
      }),
    );
    return response.Item as LedgerItem | undefined;
  }

  async complete(input: CompletionQuery): Promise<void> {
    const hasReason = input.reasonCode !== undefined;
    await this.client.send(
      new UpdateCommand({
        TableName: this.tableName,
        Key: { snapshotId: input.claim.snapshotId },
        UpdateExpression: hasReason
          ? "SET #state = :outcome, #reason = :reason, #updated = :now REMOVE #token, #lease"
          : "SET #state = :outcome, #updated = :now REMOVE #token, #lease",
        ConditionExpression:
          "#archive = :archive AND #state = :processing AND #token = :token",
        ExpressionAttributeNames: {
          "#archive": "archiveId",
          "#state": "state",
          "#token": "claimToken",
          "#lease": "leaseUntil",
          "#updated": "updatedAt",
          ...(hasReason ? { "#reason": "reasonCode" } : {}),
        },
        ExpressionAttributeValues: {
          ":archive": input.claim.archiveId,
          ":processing": "PROCESSING",
          ":token": input.claim.token,
          ":outcome": input.outcome,
          ":now": input.now,
          ...(hasReason ? { ":reason": input.reasonCode } : {}),
        },
      }),
    );
  }

  async release(input: ReleaseQuery): Promise<void> {
    await this.client.send(
      new UpdateCommand({
        TableName: this.tableName,
        Key: { snapshotId: input.claim.snapshotId },
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
          ":archive": input.claim.archiveId,
          ":processing": "PROCESSING",
          ":pending": "PENDING",
          ":token": input.claim.token,
          ":reason": input.reason,
          ":now": input.now,
        },
      }),
    );
  }
}

export { DynamoDBIndexingLedgerQueries };
