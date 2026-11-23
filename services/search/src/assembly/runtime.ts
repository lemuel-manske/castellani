import { DynamoDBClient } from "@aws-sdk/client-dynamodb";
import { S3Client } from "@aws-sdk/client-s3";
import { DynamoDBDocumentClient } from "@aws-sdk/lib-dynamodb";
import { Client as OpenSearchClient } from "@opensearch-project/opensearch";
import { createS3ArtifactReader } from "../adapters/artifacts/s3.js";
import { createWarcCapturedPageReader } from "../adapters/artifacts/warc.js";
import { createOpenSearchDocumentReader } from "../adapters/search/opensearch-reader.js";
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
import type { PublicationEvent } from "../application/types.js";
import type { SearchSettings } from "./config.js";
import { SearchWorker } from "./worker.js";

/** Composes Search infrastructure and coordinates its HTTP and worker lifecycles. */
class SearchRuntime {
  constructor(private readonly settings: SearchSettings) {}

  async start(
    signal: AbortSignal = new AbortController().signal,
  ): Promise<void> {
    if (signal.aborted) {
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

    const indexingLedger = new DynamoDBIndexingLedger(
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
    const capturedPageReader = createWarcCapturedPageReader(artifactReader);
    const documentWriter = createOpenSearchDocumentWriter(
      opensearch,
      this.settings.searchIndexName,
    );

    const searchServer = createSearchServer(
      createOpenSearchDocumentReader(opensearch, this.settings.searchIndexName),
      publicationLedger,
      manifestLedger,
    );

    const worker = new SearchWorker(
      {
        rabbitmqUrl: this.settings.rabbitmqUrl,
        reconnectDelayMilliseconds:
          this.settings.reconnectDelayMilliseconds,
      },
      {
        pageCaptured: (event) =>
          processPageCaptured(
            event,
            indexingLedger,
            capturedPageReader,
            documentWriter,
            this.settings.indexingLeaseDurationSeconds,
            this.settings.indexingMaxAttempts,
          ),
        publicationEvent: (event: PublicationEvent) =>
          event.type === "CrawlCompleted"
            ? processCrawlCompleted(
                event.payload,
                artifactReader,
                manifestLedger,
                indexingLedger,
                capturedPageReader,
                documentWriter,
                this.settings.indexingLeaseDurationSeconds,
                this.settings.indexingMaxAttempts,
              )
            : processPublicationEvent(event, publicationLedger),
      },
    );

    try {
      await ensureSearchIndex(opensearch, this.settings.searchIndexName);
      await searchServer.listen({
        host: this.settings.httpHost,
        port: this.settings.httpPort,
      });
      await worker.start(signal);
    } finally {
      await searchServer.close().catch(() => undefined);
      dynamodb.destroy();
      s3.destroy();
      await opensearch.close();
    }
  }
}

export { SearchRuntime };
