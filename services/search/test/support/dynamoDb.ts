import {
  CreateTableCommand,
  DeleteTableCommand,
  DynamoDBClient,
  waitUntilTableExists,
} from "@aws-sdk/client-dynamodb";
import { DynamoDBDocumentClient, GetCommand } from "@aws-sdk/lib-dynamodb";

import {
  MANIFEST_LEDGER,
  OUTBOX,
  PUBLICATION_LEDGER,
  INDEXING_LEDGER,
} from "../../src/topology/tables.js";

import { DynamoDBIndexingLedger } from "../../src/adapters/persistence/dynamodb/indexing-ledger.js";
import { DynamoDBManifestLedger } from "../../src/adapters/persistence/dynamodb/manifest-ledger.js";
import { DynamoDBOutbox } from "../../src/adapters/persistence/dynamodb/outbox.js";
import { DynamoDBPublicationLedger } from "../../src/adapters/persistence/dynamodb/publication-ledger.js";

import type { SearchSettings } from "../../src/config.js";

function createDynamoDbTestSupport(settings: SearchSettings) {
  const client = new DynamoDBClient({
    region: settings.awsRegion,
    endpoint: settings.dynamodbEndpointUrl,
    credentials: {
      accessKeyId: settings.awsAccessKeyId,
      secretAccessKey: settings.awsSecretAccessKey,
    },
  });

  const documentClient = DynamoDBDocumentClient.from(client, {
    marshallOptions: { removeUndefinedValues: true },
  });

  const ledger = new DynamoDBIndexingLedger(documentClient);
  const outbox = new DynamoDBOutbox(documentClient);
  const publicationLedger = new DynamoDBPublicationLedger(
    documentClient,
    outbox,
  );
  const manifestLedger = new DynamoDBManifestLedger(documentClient);

  return {
    ledger,
    publicationLedger,
    manifestLedger,

    async getIndexingEntry(
      snapshotId: string,
    ): Promise<Record<string, unknown> | undefined> {
      const response = await documentClient.send(
        new GetCommand({
          TableName: INDEXING_LEDGER,
          Key: { snapshotId },
          ConsistentRead: true,
        }),
      );

      return response.Item;
    },

    async getPublicationEntry(
      archiveId: string,
    ): Promise<Record<string, unknown> | undefined> {
      const response = await documentClient.send(
        new GetCommand({
          TableName: PUBLICATION_LEDGER,
          Key: { archiveId },
          ConsistentRead: true,
        }),
      );

      return response.Item;
    },

    async getManifestMetadata(
      archiveId: string,
    ): Promise<Record<string, unknown> | undefined> {
      const response = await documentClient.send(
        new GetCommand({
          TableName: MANIFEST_LEDGER,
          Key: { archiveId, snapshotId: "!manifest" },
          ConsistentRead: true,
        }),
      );

      return response.Item;
    },

    async setup(): Promise<void> {
      await client.send(
        new CreateTableCommand({
          TableName: INDEXING_LEDGER,
          AttributeDefinitions: [
            { AttributeName: "snapshotId", AttributeType: "S" },
            { AttributeName: "archiveId", AttributeType: "S" },
          ],
          KeySchema: [{ AttributeName: "snapshotId", KeyType: "HASH" }],
          GlobalSecondaryIndexes: [
            {
              IndexName: "archiveId-snapshotId-index",
              KeySchema: [
                { AttributeName: "archiveId", KeyType: "HASH" },
                { AttributeName: "snapshotId", KeyType: "RANGE" },
              ],
              Projection: { ProjectionType: "ALL" },
            },
          ],
          BillingMode: "PAY_PER_REQUEST",
        }),
      );

      await waitUntilTableExists(
        { client, maxWaitTime: 20, minDelay: 1, maxDelay: 2 },
        { TableName: INDEXING_LEDGER },
      );

      await client.send(
        new CreateTableCommand({
          TableName: PUBLICATION_LEDGER,
          AttributeDefinitions: [
            { AttributeName: "archiveId", AttributeType: "S" },
          ],
          KeySchema: [{ AttributeName: "archiveId", KeyType: "HASH" }],
          BillingMode: "PAY_PER_REQUEST",
        }),
      );

      await waitUntilTableExists(
        { client, maxWaitTime: 20, minDelay: 1, maxDelay: 2 },
        { TableName: PUBLICATION_LEDGER },
      );

      await client.send(
        new CreateTableCommand({
          TableName: MANIFEST_LEDGER,
          AttributeDefinitions: [
            { AttributeName: "archiveId", AttributeType: "S" },
            { AttributeName: "snapshotId", AttributeType: "S" },
          ],
          KeySchema: [
            { AttributeName: "archiveId", KeyType: "HASH" },
            { AttributeName: "snapshotId", KeyType: "RANGE" },
          ],
          BillingMode: "PAY_PER_REQUEST",
        }),
      );

      await waitUntilTableExists(
        { client, maxWaitTime: 20, minDelay: 1, maxDelay: 2 },
        { TableName: MANIFEST_LEDGER },
      );

      await client.send(
        new CreateTableCommand({
          TableName: OUTBOX,
          AttributeDefinitions: [
            { AttributeName: "messageId", AttributeType: "S" },
          ],
          KeySchema: [{ AttributeName: "messageId", KeyType: "HASH" }],
          BillingMode: "PAY_PER_REQUEST",
        }),
      );

      await waitUntilTableExists(
        { client, maxWaitTime: 20, minDelay: 1, maxDelay: 2 },
        { TableName: OUTBOX },
      );
    },

    async teardown(): Promise<void> {
      try {
        await Promise.all([
          client.send(new DeleteTableCommand({ TableName: INDEXING_LEDGER })),

          client.send(
            new DeleteTableCommand({ TableName: PUBLICATION_LEDGER }),
          ),

          client.send(new DeleteTableCommand({ TableName: MANIFEST_LEDGER })),

          client.send(new DeleteTableCommand({ TableName: OUTBOX })),
        ]);
      } finally {
        client.destroy();
      }
    },
  };
}

export { createDynamoDbTestSupport };
