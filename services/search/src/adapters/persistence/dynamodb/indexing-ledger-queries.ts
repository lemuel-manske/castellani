import { GetCommand, QueryCommand, UpdateCommand } from "@aws-sdk/lib-dynamodb";
import type {
  DynamoDBDocumentClient,
  QueryCommandInput,
} from "@aws-sdk/lib-dynamodb";

import {
  INDEXING_OUTCOME,
  INDEXING_REASON_CODE,
  type IndexingOutcome,
  type SnapshotLedgerEntry,
  type TerminalIndexingOutcome,
} from "../../../domain/index.js";

import type { SnapshotClaim } from "../../../ports/indexing-ledger.js";

import { INDEXING_LEDGER } from "../../../topology/tables.js";

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
  messageId: string;
  now: number;
  attempts: number;
  maxAttempts: number;
}

interface CompleteIndexingEntryInput {
  claim: SnapshotClaim;
  outcome: TerminalIndexingOutcome;
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
  input: ClaimIndexingEntryInput,
): Promise<LedgerItem> {
  const response = await client.send(
    new UpdateCommand({
      TableName: INDEXING_LEDGER,
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
        ":processing": INDEXING_OUTCOME.PROCESSING,
        ":pending": INDEXING_OUTCOME.PENDING,
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
  input: ExhaustIndexingEntryInput,
): Promise<void> {
  await client.send(
    new UpdateCommand({
      TableName: INDEXING_LEDGER,
      Key: { snapshotId: input.snapshotId },
      UpdateExpression:
        "SET #state = :failed, #reason = :reason, #updated = :now, #processed = list_append(if_not_exists(#processed, :empty), :messages) REMOVE #token, #lease",
      ConditionExpression:
        "#archive = :archive AND #attempts = :attempts AND #attempts >= :maxAttempts AND (#state = :pending OR (#state = :processing AND #lease <= :now)) AND (attribute_not_exists(#processed) OR NOT contains(#processed, :message))",
      ExpressionAttributeNames: {
        "#archive": "archiveId",
        "#attempts": "attempts",
        "#state": "state",
        "#lease": "leaseUntil",
        "#token": "claimToken",
        "#reason": "reasonCode",
        "#updated": "updatedAt",
        "#processed": "processedMessageIds",
      },
      ExpressionAttributeValues: {
        ":archive": input.archiveId,
        ":attempts": input.attempts,
        ":maxAttempts": input.maxAttempts,
        ":pending": INDEXING_OUTCOME.PENDING,
        ":processing": INDEXING_OUTCOME.PROCESSING,
        ":failed": INDEXING_OUTCOME.FAILED,
        ":reason": INDEXING_REASON_CODE.ATTEMPTS_EXHAUSTED,
        ":now": input.now,
        ":empty": [],
        ":messages": [input.messageId],
        ":message": input.messageId,
      },
    }),
  );
}

async function listIndexingEntriesByArchive(
  client: DynamoDBDocumentClient,
  archiveId: string,
): Promise<SnapshotLedgerEntry[]> {
  const entries: SnapshotLedgerEntry[] = [];
  let lastEvaluatedKey: QueryCommandInput["ExclusiveStartKey"];

  do {
    const response = await client.send(
      new QueryCommand({
        TableName: INDEXING_LEDGER,
        IndexName: "archiveId-snapshotId-index",
        KeyConditionExpression: "#archive = :archive",
        ProjectionExpression: "#snapshot, #state",
        ExpressionAttributeNames: {
          "#archive": "archiveId",
          "#snapshot": "snapshotId",
          "#state": "state",
        },
        ExpressionAttributeValues: { ":archive": archiveId },
        ...(lastEvaluatedKey === undefined
          ? {}
          : { ExclusiveStartKey: lastEvaluatedKey }),
      }),
    );

    entries.push(
      ...(response.Items ?? []).map((item) => ({
        snapshotId: String(item.snapshotId),
        outcome: item.state as IndexingOutcome,
      })),
    );
    lastEvaluatedKey = response.LastEvaluatedKey;
  } while (lastEvaluatedKey !== undefined);

  return entries;
}

async function getIndexingEntry(
  client: DynamoDBDocumentClient,
  snapshotId: string,
): Promise<LedgerItem | undefined> {
  const response = await client.send(
    new GetCommand({
      TableName: INDEXING_LEDGER,
      Key: { snapshotId },
      ConsistentRead: true,
    }),
  );

  return response.Item as LedgerItem | undefined;
}

async function completeIndexingEntry(
  client: DynamoDBDocumentClient,
  input: CompleteIndexingEntryInput,
): Promise<void> {
  const hasReason = input.reasonCode !== undefined;

  await client.send(
    new UpdateCommand({
      TableName: INDEXING_LEDGER,
      Key: { snapshotId: input.claim.snapshotId },
      UpdateExpression: hasReason
        ? "SET #state = :outcome, #reason = :reason, #updated = :now, #processed = list_append(if_not_exists(#processed, :empty), :messages) REMOVE #token, #lease"
        : "SET #state = :outcome, #updated = :now, #processed = list_append(if_not_exists(#processed, :empty), :messages) REMOVE #token, #lease",
      ConditionExpression:
        "#archive = :archive AND #state = :processing AND #token = :token AND (attribute_not_exists(#processed) OR NOT contains(#processed, :message))",
      ExpressionAttributeNames: {
        "#archive": "archiveId",
        "#state": "state",
        "#token": "claimToken",
        "#lease": "leaseUntil",
        "#updated": "updatedAt",
        "#processed": "processedMessageIds",
        ...(hasReason ? { "#reason": "reasonCode" } : {}),
      },
      ExpressionAttributeValues: {
        ":archive": input.claim.archiveId,
        ":processing": INDEXING_OUTCOME.PROCESSING,
        ":token": input.claim.token,
        ":outcome": input.outcome,
        ":now": input.now,
        ":empty": [],
        ":messages": [input.claim.messageId],
        ":message": input.claim.messageId,
        ...(hasReason ? { ":reason": input.reasonCode } : {}),
      },
    }),
  );
}

async function releaseIndexingEntry(
  client: DynamoDBDocumentClient,
  input: ReleaseIndexingEntryInput,
): Promise<void> {
  await client.send(
    new UpdateCommand({
      TableName: INDEXING_LEDGER,
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
        ":processing": INDEXING_OUTCOME.PROCESSING,
        ":pending": INDEXING_OUTCOME.PENDING,
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
  getIndexingEntry,
  listIndexingEntriesByArchive,
  releaseIndexingEntry,
};
