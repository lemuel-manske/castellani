import { randomUUID } from "node:crypto";

import { ConditionalCheckFailedException } from "@aws-sdk/client-dynamodb";
import { type DynamoDBDocumentClient, GetCommand, UpdateCommand } from "@aws-sdk/lib-dynamodb";

import {
  type Claim,
  type ClaimResult,
  type Ledger,
  type LedgerStatus,
  type Outcome,
  type PageCaptured,
  terminalStatuses,
} from "./model.js";

/**
 * Ledger item, keyed by `snapshotId`:
 * `archiveId`, `status`, `attempts`, `claimToken`, `leaseUntil` (epoch ms),
 * `firstMessageId`, `reason`, `createdAt`, `updatedAt`.
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
          Key: { snapshotId: event.snapshotId },
          UpdateExpression:
            "SET archiveId = :archiveId, #status = :processing, claimToken = :token, leaseUntil = :lease, " +
            "updatedAt = :now, createdAt = if_not_exists(createdAt, :now), " +
            "firstMessageId = if_not_exists(firstMessageId, :messageId), " +
            "attempts = if_not_exists(attempts, :zero) + :one",
          ConditionExpression:
            "(attribute_not_exists(archiveId) OR archiveId = :archiveId) AND (" +
            "attribute_not_exists(#status) OR #status = :pending OR " +
            "(#status = :processing AND leaseUntil < :nowMs))",
          ExpressionAttributeNames: { "#status": "status" },
          ExpressionAttributeValues: {
            ":archiveId": event.archiveId,
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
        claim: { snapshotId: event.snapshotId, token, attempt: Number(result.Attributes?.attempts ?? 1) },
      };
    } catch (error) {
      if (!(error instanceof ConditionalCheckFailedException)) {
        throw error;
      }
    }

    return this.explainRejectedClaim(event);
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
          Key: { snapshotId: claim.snapshotId },
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
      new GetCommand({ TableName: this.table, Key: { snapshotId: event.snapshotId }, ConsistentRead: true }),
    );

    if (item === undefined) {
      // Deleted between the conditional write and the read; try again later.
      return { kind: "busy" };
    }

    if (item.archiveId !== event.archiveId) {
      return {
        kind: "conflict",
        reason: `snapshot ${event.snapshotId} belongs to archive ${String(item.archiveId)}, not ${event.archiveId}`,
      };
    }

    const status = item.status as LedgerStatus;

    return terminalStatuses.has(status) ? { kind: "done", status } : { kind: "busy" };
  }
}
