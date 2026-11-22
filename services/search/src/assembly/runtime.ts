import { DynamoDBClient } from "@aws-sdk/client-dynamodb";
import { S3Client } from "@aws-sdk/client-s3";
import { DynamoDBDocumentClient } from "@aws-sdk/lib-dynamodb";
import { Client as OpenSearchClient } from "@opensearch-project/opensearch";
import * as amqp from "amqplib";
import { createS3ArtifactReader } from "../adapters/artifacts/s3.js";
import { createWarcCapturedPageReader } from "../adapters/artifacts/warc.js";
import { startPageCapturedConsumer } from "../adapters/messaging/rabbitmq/pageCapturedConsumer.js";
import { createOpenSearchDocumentReader } from "../adapters/search/opensearch-reader.js";
import { startPublicationConsumer } from "../adapters/messaging/rabbitmq/publicationConsumer.js";
import { DynamoDBIndexingLedger } from "../adapters/persistence/dynamodb/indexing-ledger.js";
import { DynamoDBManifestLedger } from "../adapters/persistence/dynamodb/manifest-ledger.js";
import { DynamoDBPublicationLedger } from "../adapters/persistence/dynamodb/publication-ledger.js";
import {
  createOpenSearchDocumentWriter,
  ensureSearchIndex,
} from "../adapters/search/opensearch.js";
import { createSearchServer } from "../api/server.js";
import { processCrawlCompleted } from "../application/processCrawlCompleted.js";
import { processPageCaptured } from "../application/processPageCaptured.js";
import { processPublicationEvent } from "../application/processPublicationEvent.js";
import type { PublicationEvent } from "../application/processPublicationEvent.js";
import type { PublicationLedger } from "../ports/publication-ledger.js";
import type { SearchSettings } from "./config.js";

function isSignalAborted(signal: AbortSignal): boolean {
  return signal.aborted;
}

function waitForConnectionOrShutdown(
  connection: amqp.ChannelModel,
  signal: AbortSignal,
): Promise<void> {
  return new Promise((resolve) => {
    const finish = () => {
      signal.removeEventListener("abort", finish);
      connection.removeListener("close", finish);
      connection.removeListener("error", finish);
      resolve();
    };

    connection.once("close", finish);
    connection.once("error", finish);
    signal.addEventListener("abort", finish, { once: true });

    if (isSignalAborted(signal)) {
      finish();
    }
  });
}

function waitForReconnectDelay(
  milliseconds: number,
  signal: AbortSignal,
): Promise<void> {
  if (isSignalAborted(signal)) {
    return Promise.resolve();
  }

  return new Promise((resolve) => {
    const finish = () => {
      clearTimeout(timeout);
      signal.removeEventListener("abort", finish);
      resolve();
    };

    const timeout = setTimeout(finish, milliseconds);

    signal.addEventListener("abort", finish, { once: true });

    if (isSignalAborted(signal)) {
      finish();
    }
  });
}

/** Owns Search service infrastructure clients and the RabbitMQ consumer lifecycle. */
class SearchRuntime {
  constructor(private readonly settings: SearchSettings) {}

  async start(
    signal: AbortSignal = new AbortController().signal,
  ): Promise<void> {
    if (isSignalAborted(signal)) {
      return;
    }

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
    const publicationLedger = new DynamoDBPublicationLedger(
      documentClient,
      this.settings.publicationLedgerTableName,
    );
    const manifestLedger = new DynamoDBManifestLedger(
      documentClient,
      this.settings.manifestLedgerTableName,
    );
    const artifactReader = createS3ArtifactReader(s3);
    const documentWriter = createOpenSearchDocumentWriter(
      opensearch,
      this.settings.searchIndexName,
    );
    const capturedPageReader = createWarcCapturedPageReader(artifactReader);
    const searchServer = createSearchServer(
      createOpenSearchDocumentReader(opensearch, this.settings.searchIndexName),
      publicationLedger,
      manifestLedger,
    );

    try {
      await ensureSearchIndex(opensearch, this.settings.searchIndexName);
      await searchServer.listen({
        host: this.settings.httpHost,
        port: this.settings.httpPort,
      });
      await this.runConsumer(
        {
          ledger,
          capturedPageReader,
          documentWriter,
          publicationLedger,
          manifestLedger,
          artifactReader,
        },
        signal,
      );
    } finally {
      await searchServer.close().catch(() => undefined);
      dynamodb.destroy();
      s3.destroy();
      await opensearch.close();
    }
  }

  private async runConsumer(
    dependencies: Parameters<typeof processPageCaptured>[1] & {
      publicationLedger: PublicationLedger;
      manifestLedger: DynamoDBManifestLedger;
      artifactReader: ReturnType<typeof createS3ArtifactReader>;
    },
    signal: AbortSignal,
  ): Promise<void> {
    while (!isSignalAborted(signal)) {
      let connection: amqp.ChannelModel | undefined;
      let pageCapturedChannel: amqp.ConfirmChannel | undefined;
      let publicationChannel: amqp.ConfirmChannel | undefined;

      try {
        connection = await amqp.connect(this.settings.rabbitmqUrl);

        if (isSignalAborted(signal)) {
          await connection.close();
          break;
        }

        pageCapturedChannel = await connection.createConfirmChannel();
        publicationChannel = await connection.createConfirmChannel();

        if (isSignalAborted(signal)) {
          await Promise.all([
            pageCapturedChannel.close(),
            publicationChannel.close(),
          ]);
          await connection.close();
          break;
        }

        await startPageCapturedConsumer(pageCapturedChannel, (event) =>
          processPageCaptured(event, {
            ...dependencies,
            leaseDurationSeconds: this.settings.indexingLeaseDurationSeconds,
            maxAttempts: this.settings.indexingMaxAttempts,
          }),
        );
        await startPublicationConsumer(
          publicationChannel,
          (event: PublicationEvent) =>
            event.type === "CrawlCompleted"
              ? processCrawlCompleted(
                  event.payload,
                  dependencies.artifactReader,
                  dependencies.manifestLedger,
                )
              : processPublicationEvent(event, dependencies.publicationLedger),
        );

        await waitForConnectionOrShutdown(connection, signal);
      } catch (error) {
        if (!isSignalAborted(signal)) {
          console.error("Search consumer connection failed", error);
        }
      } finally {
        await pageCapturedChannel?.close().catch(() => undefined);
        await publicationChannel?.close().catch(() => undefined);
        await connection?.close().catch(() => undefined);
      }

      await waitForReconnectDelay(
        this.settings.reconnectDelayMilliseconds,
        signal,
      );
    }
  }
}

export { SearchRuntime };
