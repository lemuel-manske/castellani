import { DynamoDBClient } from "@aws-sdk/client-dynamodb";
import { S3Client } from "@aws-sdk/client-s3";
import { DynamoDBDocumentClient } from "@aws-sdk/lib-dynamodb";
import { Client as OpenSearchClient } from "@opensearch-project/opensearch";
import * as amqp from "amqplib";
import { createS3ArtifactReader } from "./adapters/artifacts/s3.js";
import { createWarcCapturedPageReader } from "./adapters/artifacts/warc.js";
import { startPageCapturedConsumer } from "./adapters/messaging/rabbitmq/pageCapturedConsumer.js";
import { DynamoDBIndexingLedger } from "./adapters/persistence/dynamodb/indexing-ledger.js";
import {
  createOpenSearchDocumentWriter,
  ensureSearchIndex,
} from "./adapters/search/opensearch.js";
import { processPageCaptured } from "./application/processPageCaptured.js";

const awsRegion = process.env.SEARCH_AWS_REGION ?? "us-east-1";
const dynamodbEndpoint = process.env.SEARCH_DYNAMODB_ENDPOINT_URL;
const s3Endpoint = process.env.SEARCH_S3_ENDPOINT_URL;
const rabbitmqUrl =
  process.env.SEARCH_RABBITMQ_URL ??
  "amqp://castellani:local-development-only@localhost:5672/";
const opensearchUrl =
  process.env.SEARCH_OPENSEARCH_URL ?? "http://localhost:9200";
const artifactBucket =
  process.env.SEARCH_ARTIFACT_BUCKET ?? "castellani-archive-artifacts";
const ledgerTable =
  process.env.SEARCH_INDEXING_LEDGER_TABLE ?? "search_indexing_ledger";

const localCredentials = { accessKeyId: "test", secretAccessKey: "test" };
const dynamodb = new DynamoDBClient({
  region: awsRegion,
  ...(dynamodbEndpoint === undefined
    ? {}
    : { endpoint: dynamodbEndpoint, credentials: localCredentials }),
});
const documentClient = DynamoDBDocumentClient.from(dynamodb, {
  marshallOptions: { removeUndefinedValues: true },
});
const s3 = new S3Client({
  region: awsRegion,
  ...(s3Endpoint === undefined
    ? {}
    : {
        endpoint: s3Endpoint,
        forcePathStyle: true,
        credentials: localCredentials,
      }),
});
const opensearch = new OpenSearchClient({ node: opensearchUrl });

const ledger = new DynamoDBIndexingLedger(documentClient, ledgerTable);
const documentWriter = createOpenSearchDocumentWriter(
  opensearch,
  process.env.SEARCH_INDEX_NAME ?? "archive-pages-v1",
);
const capturedPageReader = createWarcCapturedPageReader(
  createS3ArtifactReader(s3),
);

async function delay(milliseconds: number): Promise<void> {
  await new Promise((resolve) => setTimeout(resolve, milliseconds));
}

async function runConsumer(): Promise<void> {
  await ensureSearchIndex(
    opensearch,
    process.env.SEARCH_INDEX_NAME ?? "archive-pages-v1",
  );

  while (true) {
    let connection: amqp.ChannelModel | undefined;
    let channel: amqp.Channel | undefined;

    try {
      connection = await amqp.connect(rabbitmqUrl);
      channel = await connection.createChannel();

      await startPageCapturedConsumer(channel, (event) =>
        processPageCaptured(event, {
          ledger,
          capturedPageReader,
          documentWriter,
        }),
      );

      await new Promise<void>((resolve) => {
        connection?.once("close", resolve);
        connection?.once("error", resolve);
      });
    } catch (error) {
      console.error("Search consumer connection failed", error);
    } finally {
      await channel?.close().catch(() => undefined);
      await connection?.close().catch(() => undefined);
    }

    await delay(1000);
  }
}

runConsumer().catch((error: unknown) => {
  console.error("Search service stopped unexpectedly", error);
  process.exitCode = 1;
});
