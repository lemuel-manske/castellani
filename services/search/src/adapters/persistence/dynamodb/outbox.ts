import { randomUUID } from "node:crypto";

import { GetCommand, ScanCommand, UpdateCommand } from "@aws-sdk/lib-dynamodb";
import type { DynamoDBDocumentClient } from "@aws-sdk/lib-dynamodb";

import { OUTBOX_STATE } from "../../../ports/outbox.js";
import type {
  ClaimedOutboxMessage,
  Outbox,
  OutboxEntry,
} from "../../../ports/outbox.js";

import { OUTBOX } from "../../../topology/tables.js";

import { stringValue } from "../../../utils/index.js";

import { isConditionalCheckFailure } from "./error-handling.js";

const SCAN_LIMIT = 50;

function entryFromItem(
  item: Record<string, unknown> | undefined,
): OutboxEntry | undefined {
  if (item === undefined) {
    return undefined;
  }

  const messageId = stringValue(item["messageId"]);

  if (!messageId) {
    return undefined;
  }

  return {
    messageId,
    correlationId: stringValue(item["correlationId"]),
    type: stringValue(item["type"]),
    occurredAt: stringValue(item["occurredAt"]),
    envelope: stringValue(item["envelope"]),
    cleanupRequired: item["cleanupRequired"] === true,
  };
}

class DynamoDBOutbox implements Outbox {
  constructor(private readonly client: DynamoDBDocumentClient) {}

  async get(messageId: string): Promise<OutboxEntry | undefined> {
    const response = await this.client.send(
      new GetCommand({
        TableName: OUTBOX,
        Key: { messageId },
        ConsistentRead: true,
      }),
    );

    return entryFromItem(response.Item);
  }

  async claim(
    leaseDurationSeconds: number,
  ): Promise<ClaimedOutboxMessage | undefined> {
    if (!Number.isFinite(leaseDurationSeconds) || leaseDurationSeconds <= 0) {
      throw new Error("lease duration must be positive");
    }

    const now = Date.now() / 1000;
    let cursor: Record<string, unknown> | undefined;

    for (;;) {
      const page = await this.client.send(
        new ScanCommand({
          TableName: OUTBOX,
          Limit: SCAN_LIMIT,
          ExclusiveStartKey: cursor,
          FilterExpression:
            "#state = :pending OR (#state = :claimed AND #leaseUntil < :now)",
          ExpressionAttributeNames: {
            "#state": "state",
          },
          ExpressionAttributeValues: {
            ":pending": OUTBOX_STATE.PENDING,
            ":claimed": OUTBOX_STATE.CLAIMED,
            ":now": now,
          },
        }),
      );

      for (const item of page.Items ?? []) {
        const id = stringValue(item["messageId"]);

        if (!id) {
          continue;
        }

        const leaseToken = randomUUID();

        try {
          const response = await this.client.send(
            new UpdateCommand({
              TableName: OUTBOX,
              Key: { messageId: id },
              ConditionExpression:
                "#state = :pending OR (#state = :claimed AND #leaseUntil < :now)",
              UpdateExpression:
                "SET #state = :claimed, leaseToken = :token, leaseUntil = :until ADD attempts :increment",
              ExpressionAttributeNames: {
                "#state": "state",
              },
              ExpressionAttributeValues: {
                ":pending": OUTBOX_STATE.PENDING,
                ":claimed": OUTBOX_STATE.CLAIMED,
                ":now": now,
                ":until": now + leaseDurationSeconds,
                ":token": leaseToken,
                ":increment": 1,
              },
              ReturnValues: "ALL_NEW",
            }),
          );

          const entry = entryFromItem(response.Attributes);

          if (entry === undefined) {
            throw new Error("claimed outbox entry is missing messageId");
          }

          return { ...entry, leaseToken };
        } catch (error) {
          if (isConditionalCheckFailure(error)) {
            continue;
          }

          throw error;
        }
      }

      if (page.LastEvaluatedKey === undefined) {
        return undefined;
      }

      cursor = page.LastEvaluatedKey;
    }
  }

  async completeCleanup(message: ClaimedOutboxMessage): Promise<boolean> {
    try {
      await this.client.send(
        new UpdateCommand({
          TableName: OUTBOX,
          Key: { messageId: message.messageId },
          ConditionExpression:
            "#state = :claimed AND leaseToken = :token AND #cleanup = :pendingCleanup",
          UpdateExpression: "SET #cleanup = :done",
          ExpressionAttributeNames: {
            "#state": "state",
            "#cleanup": "cleanupRequired",
          },
          ExpressionAttributeValues: {
            ":claimed": OUTBOX_STATE.CLAIMED,
            ":token": message.leaseToken,
            ":pendingCleanup": true,
            ":done": false,
          },
        }),
      );

      return true;
    } catch (error) {
      if (isConditionalCheckFailure(error)) {
        return false;
      }

      throw error;
    }
  }

  async confirm(message: ClaimedOutboxMessage): Promise<void> {
    await this.client.send(
      new UpdateCommand({
        TableName: OUTBOX,
        Key: { messageId: message.messageId },
        ConditionExpression: "#state = :claimed AND leaseToken = :token",
        UpdateExpression:
          "SET #state = :published, publishedAt = :now REMOVE leaseToken, leaseUntil",
        ExpressionAttributeNames: {
          "#state": "state",
        },
        ExpressionAttributeValues: {
          ":claimed": OUTBOX_STATE.CLAIMED,
          ":token": message.leaseToken,
          ":published": OUTBOX_STATE.PUBLISHED,
          ":now": new Date().toISOString(),
        },
      }),
    );
  }
}

export { DynamoDBOutbox };
