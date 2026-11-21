import { type DynamoDBDocumentClient, GetCommand, PutCommand } from "@aws-sdk/lib-dynamodb";

/**
 * Message-level deduplication (`search_inbox`). A message is recorded only
 * after its handler finished, so a recorded `messageId` always means its
 * durable effect is accounted for; a crash before recording just reprocesses
 * the message through the idempotent handlers.
 */
export interface Inbox {
  processed(messageId: string): Promise<boolean>;
  record(messageId: string, type: string, now: Date): Promise<void>;
}

/**
 * Inbox item, keyed by `messageId`: `type`, `processedAt`, `expiresAt` (epoch
 * seconds, the table's TTL attribute). TTL is cleanup only: a record is
 * honored while it exists, even past `expiresAt`, and a message redelivered
 * after its record is gone is reprocessed by the idempotent handlers.
 */
export class DynamoInbox implements Inbox {
  constructor(
    private readonly client: DynamoDBDocumentClient,
    private readonly table: string,
    private readonly retentionMs: number,
  ) {}

  async processed(messageId: string): Promise<boolean> {
    const { Item: item } = await this.client.send(
      new GetCommand({ TableName: this.table, Key: { messageId }, ConsistentRead: true }),
    );

    return item !== undefined;
  }

  async record(messageId: string, type: string, now: Date): Promise<void> {
    await this.client.send(
      new PutCommand({
        TableName: this.table,
        Item: {
          messageId,
          type,
          processedAt: now.toISOString(),
          expiresAt: Math.ceil((now.getTime() + this.retentionMs) / 1_000),
        },
      }),
    );
  }
}
