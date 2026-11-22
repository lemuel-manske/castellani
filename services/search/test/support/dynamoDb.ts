import { randomUUID } from "node:crypto";
import {
  CreateTableCommand,
  DeleteTableCommand,
  DynamoDBClient,
  waitUntilTableExists,
} from "@aws-sdk/client-dynamodb";
import { DynamoDBDocumentClient } from "@aws-sdk/lib-dynamodb";
import { DynamoDBIndexingLedger } from "../../src/adapters/persistence/dynamodb/indexing-ledger.js";

const SEARCH_DYNAMODB_ENDPOINT_URL = process.env.SEARCH_DYNAMODB_ENDPOINT_URL;

function createDynamoDbTestSupport(clock: () => number) {
  const client = new DynamoDBClient({
    region: "us-east-1",
    endpoint: SEARCH_DYNAMODB_ENDPOINT_URL ?? "http://localhost:8000",
    credentials: { accessKeyId: "test", secretAccessKey: "test" },
  });
  const documentClient = DynamoDBDocumentClient.from(client, {
    marshallOptions: { removeUndefinedValues: true },
  });
  const tableName = `search-ledger-${randomUUID().replaceAll("-", "")}`;
  const ledger = new DynamoDBIndexingLedger(documentClient, tableName, clock);

  return {
    ledger,
    async setup(): Promise<void> {
      await client.send(
        new CreateTableCommand({
          TableName: tableName,
          AttributeDefinitions: [{ AttributeName: "snapshotId", AttributeType: "S" }],
          KeySchema: [{ AttributeName: "snapshotId", KeyType: "HASH" }],
          BillingMode: "PAY_PER_REQUEST",
        }),
      );
      await waitUntilTableExists({ client, maxWaitTime: 20 }, { TableName: tableName });
    },
    async teardown(): Promise<void> {
      try {
        await client.send(new DeleteTableCommand({ TableName: tableName }));
      } finally {
        client.destroy();
      }
    },
  };
}

export { SEARCH_DYNAMODB_ENDPOINT_URL, createDynamoDbTestSupport };
