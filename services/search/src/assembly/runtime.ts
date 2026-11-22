import { DynamoDBClient } from "@aws-sdk/client-dynamodb";
import { S3Client } from "@aws-sdk/client-s3";
import { DynamoDBDocumentClient } from "@aws-sdk/lib-dynamodb";
import { Client as OpenSearchClient } from "@opensearch-project/opensearch";
import * as amqp from "amqplib";
import { createS3ArtifactReader } from "../adapters/artifacts/s3.js";
import { createWarcCapturedPageReader } from "../adapters/artifacts/warc.js";
import { startPageCapturedConsumer } from "../adapters/messaging/rabbitmq/pageCapturedConsumer.js";
import { DynamoDBIndexingLedger } from "../adapters/persistence/dynamodb/indexing-ledger.js";
import {
  createOpenSearchDocumentWriter,
  ensureSearchIndex,
} from "../adapters/search/opensearch.js";
import { processPageCaptured } from "../application/processPageCaptured.js";
import type { SearchSettings } from "./config.js";

class SearchRuntime {
  constructor(private readonly settings: SearchSettings) {}

  async start(): Promise<void> {
    const localCredentials = { accessKeyId: "test", secretAccessKey: "test" };
    const dynamodb = new DynamoDBClient({
      region: this.settings.awsRegion,
      ...(this.settings.dynamodbEndpointUrl === undefined
        ? {}
        : {
            endpoint: this.settings.dynamodbEndpointUrl,
            credentials: localCredentials,
          }),
    });
    const documentClient = DynamoDBDocumentClient.from(dynamodb, {
      marshallOptions: { removeUndefinedValues: true },
    });
    const s3 = new S3Client({
      region: this.settings.awsRegion,
      ...(this.settings.s3EndpointUrl === undefined
        ? {}
        : {
            endpoint: this.settings.s3EndpointUrl,
            forcePathStyle: true,
            credentials: localCredentials,
          }),
    });
    const opensearch = new OpenSearchClient({
      node: this.settings.opensearchUrl,
    });

    const ledger = new DynamoDBIndexingLedger(
      documentClient,
      this.settings.indexingLedgerTableName,
    );
    const documentWriter = createOpenSearchDocumentWriter(
      opensearch,
      this.settings.searchIndexName,
    );
    const capturedPageReader = createWarcCapturedPageReader(
      createS3ArtifactReader(s3),
    );

    try {
      await ensureSearchIndex(opensearch, this.settings.searchIndexName);
      await this.runConsumer({
        ledger,
        capturedPageReader,
        documentWriter,
      });
    } finally {
      await Promise.allSettled([dynamodb.destroy(), s3.destroy()]);
      await opensearch.close();
    }
  }

  private async runConsumer(
    dependencies: Parameters<typeof processPageCaptured>[1],
  ): Promise<void> {
    while (true) {
      let connection: amqp.ChannelModel | undefined;
      let channel: amqp.Channel | undefined;

      try {
        connection = await amqp.connect(this.settings.rabbitmqUrl);
        channel = await connection.createChannel();
        await startPageCapturedConsumer(channel, (event) =>
          processPageCaptured(event, {
            ...dependencies,
            leaseDurationSeconds: this.settings.indexingLeaseDurationSeconds,
            maxAttempts: this.settings.indexingMaxAttempts,
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

      await new Promise((resolve) =>
        setTimeout(resolve, this.settings.reconnectDelayMilliseconds),
      );
    }
  }
}

export { SearchRuntime };
