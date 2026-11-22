import { GetCommand, ScanCommand, UpdateCommand } from "@aws-sdk/lib-dynamodb";
import type { DynamoDBDocumentClient, ScanCommandInput } from "@aws-sdk/lib-dynamodb";
import type { IndexingOutcome, SnapshotLedgerEntry } from "../../../domain.js";
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

interface ClaimIndexingEntryInput {
  archiveId: string;
  snapshotId: string;
  messageId: string;
  token: string;
  now: number;
  leaseUntil: number;
  maxAttempts: number;
}

interface ExhaustIndexingEntryInput {
  archiveId: string;
  snapshotId: string;
  now: number;
  attempts: number;
  maxAttempts: number;
}

interface CompleteIndexingEntryInput {
  claim: SnapshotClaim;
  outcome: TerminalOutcome;
  reasonCode?: string;
  now: number;
}

interface ReleaseIndexingEntryInput {
  claim: SnapshotClaim;
  reason: string;
  now: number;
}

async function claimIndexingEntry(
  client: DynamoDBDocumentClient,
  tableName: string,
  input: ClaimIndexingEntryInput,
): Promise<LedgerItem> {
  const response = await client.send(
    new UpdateCommand({
      TableName: tableName,
      Key: { snapshotId: input.snapshotId },
      UpdateExpression:
        "SET #archive = :archive, #state = :processing, #token = :token, #lease = :lease, #attempts = if_not_exists(#attempts, :zero) + :one, #message = :message, #updated = :now",
      ConditionExpression:
        "attribute_not_exists(#snapshot) OR (#archive = :archive AND #attempts < :maxAttempts AND (#state = :pending OR (#state = :processing AND #lease <= :now)))",
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
        ":maxAttempts": input.maxAttempts,
      },
      ReturnValues: "ALL_NEW",
    }),
  );

  return (response.Attributes ?? {}) as LedgerItem;
}

async function exhaustIndexingEntry(
  client: DynamoDBDocumentClient,
  tableName: string,
  input: ExhaustIndexingEntryInput,
): Promise<void> {
  await client.send(
    new UpdateCommand({
      TableName: tableName,
      Key: { snapshotId: input.snapshotId },
      UpdateExpression:
        "SET #state = :failed, #reason = :reason, #updated = :now REMOVE #token, #lease",
      ConditionExpression:
        "#archive = :archive AND #attempts = :attempts AND #attempts >= :maxAttempts AND (#state = :pending OR (#state = :processing AND #lease <= :now))",
      ExpressionAttributeNames: {
        "#archive": "archiveId",
        "#attempts": "attempts",
        "#state": "state",
        "#lease": "leaseUntil",
        "#token": "claimToken",
        "#reason": "reasonCode",
        "#updated": "updatedAt",
      },
      ExpressionAttributeValues: {
        ":archive": input.archiveId,
        ":attempts": input.attempts,
        ":maxAttempts": input.maxAttempts,
        ":pending": "PENDING",
        ":processing": "PROCESSING",
        ":failed": "FAILED",
        ":reason": "INDEXING_ATTEMPTS_EXHAUSTED",
        ":now": input.now,
      },
    }),
  );
}

async function listIndexingEntriesByArchive(
  client: DynamoDBDocumentClient,
  tableName: string,
  archiveId: string,
): Promise<SnapshotLedgerEntry[]> {
  const entries: SnapshotLedgerEntry[] = [];
  let lastEvaluatedKey: ScanCommandInput["ExclusiveStartKey"];

  do {
    const response = await client.send(
      new ScanCommand({
        TableName: tableName,
        ConsistentRead: true,
        FilterExpression: "#archive = :archive",
        ProjectionExpression: "#snapshot, #state",
        ExpressionAttributeNames: {
          "#archive": "archiveId",
          "#snapshot": "snapshotId",
          "#state": "state",
        },
        ExpressionAttributeValues: { ":archive": archiveId },
        ...(lastEvaluatedKey === undefined\n          ? {}\n          : { ExclusiveStartKey: lastEvaluatedKey }),
      }),
    );

    entries.push(...(response.Items ?? []).map((item) => ({
      snapshotId: String(item.snapshotId),
      outcome: item.state as IndexingOutcome,
    })));
    lastEvaluatedKey = response.LastEvaluatedKey;
  } while (lastEvaluatedKey !== undefined);

  return entries;
}

async function getIndexingEntry(
  client: DynamoDBDocumentClient,
  tableName: string,
  snapshotId: string,
): Promise<LedgerItem | undefined> {
  const response = await client.send(
    new GetCommand({
      TableName: tableName,
      Key: { snapshotId },
      ConsistentRead: true,
    }),
  );

  return response.Item as LedgerItem | undefined;
}

async function completeIndexingEntry(
  client: DynamoDBDocumentClient,
  tableName: string,
  input: CompleteIndexingEntryInput,
): Promise<void> {
  const hasReason = input.reasonCode !== undefined;

  await client.send(
    new UpdateCommand({
      TableName: tableName,
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

async function releaseIndexingEntry(
  client: DynamoDBDocumentClient,
  tableName: string,
  input: ReleaseIndexingEntryInput,
): Promise<void> {
  await client.send(
    new UpdateCommand({
      TableName: tableName,
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

export {
  claimIndexingEntry,
  completeIndexingEntry,
  exhaustIndexingEntry,
  getIndexingEntry,\n  listIndexingEntriesByArchive,
  releaseIndexingEntry,
};
