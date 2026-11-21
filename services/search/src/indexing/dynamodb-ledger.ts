import { randomUUID } from "node:crypto";

import { ConditionalCheckFailedException } from "@aws-sdk/client-dynamodb";
import {
  BatchGetCommand,
  type BatchGetCommandOutput,
  type DynamoDBDocumentClient,
  GetCommand,
  UpdateCommand,
} from "@aws-sdk/lib-dynamodb";

import {
  type Claim,
  type ClaimResult,
  type Ledger,
  type LedgerStatus,
  type Outcome,
  type PageCaptured,
  documentId,
  terminalStatuses,
} from "./model.js";

/**
 * `search_indexing_ledger` item, keyed by `archiveId` (partition) and
 * `snapshotId` (sort): `documentId` (the stable OpenSearch ID),
 * `warcArtifacts` (the artifact references it was indexed from), `status`,
 * `attempts`, `claimToken`, `leaseUntil` (epoch ms), `firstMessageId`,
 * `reason`, `createdAt`, `updatedAt`.
 */
export class DynamoLedger implements Ledger {
  constructor(
    private readonly client: DynamoDBDocumentClient,
    private readonly table: string,
    private readonly leaseMs: number,
  ) {}

  async claim(event: PageCaptured, now: Date): Promise<ClaimResult> {
    const token = randomUUID();

    try {
      const result = await this.client.send(
        new UpdateCommand({
          TableName: this.table,
          Key: { archiveId: event.archiveId, snapshotId: event.snapshotId },
          UpdateExpression:
            "SET #status = :processing, claimToken = :token, leaseUntil = :lease, documentId = :documentId, " +
            "updatedAt = :now, createdAt = if_not_exists(createdAt, :now), " +
            "firstMessageId = if_not_exists(firstMessageId, :messageId), " +
            "warcArtifacts = if_not_exists(warcArtifacts, :artifacts), " +
            "attempts = if_not_exists(attempts, :zero) + :one",
          ConditionExpression:
            "attribute_not_exists(#status) OR #status = :pending OR (#status = :processing AND leaseUntil < :nowMs)",
          ExpressionAttributeNames: { "#status": "status" },
          ExpressionAttributeValues: {
            ":documentId": documentId(event.archiveId, event.snapshotId),
            ":artifacts": event.warcArtifacts,
            ":processing": "PROCESSING",
            ":pending": "PENDING",
            ":token": token,
            ":lease": now.getTime() + this.leaseMs,
            ":nowMs": now.getTime(),
            ":now": now.toISOString(),
            ":messageId": event.messageId,
            ":zero": 0,
            ":one": 1,
          },
          ReturnValues: "ALL_NEW",
        }),
      );

      return {
        kind: "claimed",
        claim: {
          archiveId: event.archiveId,
          snapshotId: event.snapshotId,
          token,
          attempt: Number(result.Attributes?.attempts ?? 1),
        },
      };
    } catch (error) {
      if (!(error instanceof ConditionalCheckFailedException)) {
        throw error;
      }
    }

    return this.explainRejectedClaim(event);
  }

  async statuses(archiveId: string, snapshotIds: string[]): Promise<Map<string, LedgerStatus>> {
    const result = new Map<string, LedgerStatus>();
    const unique = [...new Set(snapshotIds)];

    // BatchGetItem accepts at most 100 keys; unprocessed keys are retried.
    for (let start = 0; start < unique.length; start += 100) {
      let keys: Record<string, unknown>[] | undefined = unique
        .slice(start, start + 100)
        .map((snapshotId) => ({ archiveId, snapshotId }));

      for (let attempt = 0; keys !== undefined && keys.length > 0; attempt += 1) {
        if (attempt > 0) {
          await new Promise((resolve) => setTimeout(resolve, Math.min(50 * 2 ** attempt, 1_000)));
        }

        const response: BatchGetCommandOutput = await this.client.send(
          new BatchGetCommand({
            RequestItems: {
              [this.table]: {
                Keys: keys,
                ConsistentRead: true,
                ProjectionExpression: "snapshotId, #status",
                ExpressionAttributeNames: { "#status": "status" },
              },
            },
          }),
        );

        for (const item of response.Responses?.[this.table] ?? []) {
          result.set(String(item.snapshotId), item.status as LedgerStatus);
        }

        keys = response.UnprocessedKeys?.[this.table]?.Keys;
      }
    }

    return result;
  }

  async reopen(archiveId: string, snapshotIds: string[], reason: string, now: Date): Promise<void> {
    for (const snapshotId of new Set(snapshotIds)) {
      try {
        await this.client.send(
          new UpdateCommand({
            TableName: this.table,
            Key: { archiveId, snapshotId },
            UpdateExpression: "SET #status = :pending, attempts = :zero, reason = :reason, updatedAt = :now",
            ConditionExpression: "#status = :indexed",
            ExpressionAttributeNames: { "#status": "status" },
            ExpressionAttributeValues: {
              ":pending": "PENDING",
              ":indexed": "INDEXED",
              ":zero": 0,
              ":reason": reason,
              ":now": now.toISOString(),
            },
          }),
        );
      } catch (error) {
        // No longer INDEXED: another worker already reopened or re-indexed it.
        if (!(error instanceof ConditionalCheckFailedException)) {
          throw error;
        }
      }
    }
  }

  async release(claim: Claim, reason: string, now: Date): Promise<void> {
    await this.fenced(claim, "SET #status = :pending, reason = :reason, updatedAt = :now REMOVE leaseUntil", {
      ":pending": "PENDING",
      ":reason": reason,
      ":now": now.toISOString(),
    });
  }

  async complete(claim: Claim, outcome: Outcome, now: Date): Promise<void> {
    const values: Record<string, unknown> = { ":status": outcome.status, ":now": now.toISOString() };
    let update = "SET #status = :status, updatedAt = :now";

    if (outcome.status === "INDEXED") {
      update += " REMOVE leaseUntil, reason";
    } else {
      update += ", reason = :reason REMOVE leaseUntil";
      values[":reason"] = outcome.reason;
    }

    await this.fenced(claim, update, values);
  }

  /**
   * Applies an update only while this worker still holds the claim. Losing the
   * claim (lease expiry and takeover) is not an error: the new holder writes
   * the same deterministic document and records its own outcome.
   */
  private async fenced(claim: Claim, update: string, values: Record<string, unknown>): Promise<void> {
    try {
      await this.client.send(
        new UpdateCommand({
          TableName: this.table,
          Key: { archiveId: claim.archiveId, snapshotId: claim.snapshotId },
          UpdateExpression: update,
          ConditionExpression: "#status = :processing AND claimToken = :token",
          ExpressionAttributeNames: { "#status": "status" },
          ExpressionAttributeValues: { ...values, ":processing": "PROCESSING", ":token": claim.token },
        }),
      );
    } catch (error) {
      if (!(error instanceof ConditionalCheckFailedException)) {
        throw error;
      }
    }
  }

  private async explainRejectedClaim(event: PageCaptured): Promise<ClaimResult> {
    const { Item: item } = await this.client.send(
      new GetCommand({
        TableName: this.table,
        Key: { archiveId: event.archiveId, snapshotId: event.snapshotId },
        ConsistentRead: true,
      }),
    );

    if (item === undefined) {
      // Deleted between the conditional write and the read; try again later.
      return { kind: "busy" };
    }

    const status = item.status as LedgerStatus;

    return terminalStatuses.has(status) ? { kind: "done", status } : { kind: "busy" };
  }
}
