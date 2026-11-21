import { randomUUID } from "node:crypto";

import { ConditionalCheckFailedException } from "@aws-sdk/client-dynamodb";
import { type DynamoDBDocumentClient, QueryCommand, UpdateCommand } from "@aws-sdk/lib-dynamodb";

import type { OutboxClaim, OutboxStore, OutgoingEvent } from "./outbox.js";

/** Sparse GSI over `dispatchPending`: only records not yet confirmed by the broker. */
export const DISPATCH_INDEX = "dispatch-pending-index";
const PENDING = "PENDING";

/**
 * The outbox `Put` of a transaction that also writes the state the event
 * reports. The record is created once: a stable `messageId` already present
 * means the emission was enqueued before.
 */
export function outboxPut(table: string, event: OutgoingEvent, now: Date) {
  return {
    Put: {
      TableName: table,
      Item: {
        messageId: event.messageId,
        type: event.type,
        event: JSON.stringify(event),
        state: PENDING,
        dispatchPending: PENDING,
        attempts: 0,
        createdAt: now.toISOString(),
      },
      ConditionExpression: "attribute_not_exists(messageId)",
    },
  };
}

/**
 * Outbox item, keyed by `messageId`: `type`, `event` (the JSON envelope),
 * `state` (`PENDING` or `SENT`), `dispatchPending` (present until sent),
 * `attempts`, `claimToken`, `leaseUntil` (epoch ms), `lastError`,
 * `createdAt`, `sentAt`.
 */
export class DynamoOutbox implements OutboxStore {
  constructor(
    private readonly client: DynamoDBDocumentClient,
    private readonly table: string,
    private readonly leaseMs: number,
  ) {}

  async pending(limit: number): Promise<string[]> {
    const response = await this.client.send(
      new QueryCommand({
        TableName: this.table,
        IndexName: DISPATCH_INDEX,
        KeyConditionExpression: "dispatchPending = :pending",
        ExpressionAttributeValues: { ":pending": PENDING },
        Limit: limit,
      }),
    );

    return (response.Items ?? []).map((item) => String(item.messageId));
  }

  async claim(messageId: string, now: Date): Promise<OutboxClaim | undefined> {
    const token = randomUUID();

    try {
      const result = await this.client.send(
        new UpdateCommand({
          TableName: this.table,
          Key: { messageId },
          UpdateExpression: "SET claimToken = :token, leaseUntil = :lease ADD attempts :one",
          ConditionExpression: "dispatchPending = :pending AND (attribute_not_exists(leaseUntil) OR leaseUntil < :now)",
          ExpressionAttributeValues: {
            ":token": token,
            ":lease": now.getTime() + this.leaseMs,
            ":now": now.getTime(),
            ":pending": PENDING,
            ":one": 1,
          },
          ReturnValues: "ALL_NEW",
        }),
      );
      const item = result.Attributes ?? {};

      return {
        messageId,
        token,
        event: JSON.parse(String(item.event)) as OutgoingEvent,
        attempts: Number(item.attempts ?? 1),
      };
    } catch (error) {
      if (error instanceof ConditionalCheckFailedException) {
        return undefined;
      }

      throw error;
    }
  }

  async markSent(claim: OutboxClaim, now: Date): Promise<void> {
    await this.fenced(claim, "SET #state = :sent, sentAt = :now REMOVE dispatchPending, leaseUntil, lastError", {
      ":sent": "SENT",
      ":now": now.toISOString(),
    });
  }

  async release(claim: OutboxClaim, reason: string, retryAt: Date): Promise<void> {
    await this.fenced(claim, "SET lastError = :reason, leaseUntil = :retryAt", {
      ":reason": reason,
      ":retryAt": retryAt.getTime(),
    });
  }

  /** A lost claim is not an error: its new holder publishes the same `messageId`. */
  private async fenced(claim: OutboxClaim, update: string, values: Record<string, unknown>): Promise<void> {
    try {
      await this.client.send(
        new UpdateCommand({
          TableName: this.table,
          Key: { messageId: claim.messageId },
          UpdateExpression: update,
          ConditionExpression: "claimToken = :token",
          ...(update.includes("#state") ? { ExpressionAttributeNames: { "#state": "state" } } : {}),
          ExpressionAttributeValues: { ...values, ":token": claim.token },
        }),
      );
    } catch (error) {
      if (!(error instanceof ConditionalCheckFailedException)) {
        throw error;
      }
    }
  }
}
