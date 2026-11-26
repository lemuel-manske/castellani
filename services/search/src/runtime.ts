import { DynamoDBClient } from "@aws-sdk/client-dynamodb";
import { DynamoDBDocumentClient } from "@aws-sdk/lib-dynamodb";
import { S3Client } from "@aws-sdk/client-s3";
import { Client as OpenSearchClient } from "@opensearch-project/opensearch";

import { DynamoDBIndexingLedger } from "./adapters/persistence/dynamodb/indexing-ledger.js";
import { DynamoDBManifestLedger } from "./adapters/persistence/dynamodb/manifest-ledger.js";
import { DynamoDBOutbox } from "./adapters/persistence/dynamodb/outbox.js";
import { DynamoDBPublicationLedger } from "./adapters/persistence/dynamodb/publication-ledger.js";
import { createOpenSearchDocumentReader } from "./adapters/search/opensearch-reader.js";
import {
  createOpenSearchDocumentWriter,
  ensureSearchIndex,
} from "./adapters/search/opensearch.js";
import { createRabbitMQCompensationPublisher } from "./adapters/messaging/rabbitmq/compensationPublisher.js";
import { createS3ArtifactReader } from "./adapters/artifacts/s3.js";
import { createWarcCapturedPageReader } from "./adapters/artifacts/warc.js";

import { createSearchServer } from "./api/server.js";

import { CRAWL_COMPLETED_EVENT } from "./domain/index.js";

import type { PublicationEvent } from "./application/types.js";
import { processCrawlCompleted } from "./application/processCrawlCompleted.js";
import { processPageCaptured } from "./application/processPageCaptured.js";
import { processPublicationEvent } from "./application/processPublicationEvent.js";

import { isAborted } from "./utils/delay.js";

import type { SearchSettings } from "./config.js";
import { SearchWorker } from "./searchWorker.js";
import { startOutboxWorker } from "./outboxWorker.js";

const HOST = "0.0.0.0";

/** Composes Search infrastructure and coordinates its HTTP and worker lifecycles. */
class SearchRuntime {
  constructor(private readonly settings: SearchSettings) {}

  async start(
    signal: AbortSignal = new AbortController().signal,
  ): Promise<void> {
    if (isAborted(signal)) {
      return;
    }

    const localCredentials = {
      accessKeyId: this.settings.awsAccessKeyId,
      secretAccessKey: this.settings.awsSecretAccessKey,
    };

    const dynamodb = new DynamoDBClient({
      region: this.settings.awsRegion,
      endpoint: this.settings.dynamodbEndpointUrl,
      credentials: localCredentials,
    });

    const documentClient = DynamoDBDocumentClient.from(dynamodb, {
      marshallOptions: { removeUndefinedValues: true },
    });

    const s3 = new S3Client({
      region: this.settings.awsRegion,
      endpoint: this.settings.s3EndpointUrl,
      forcePathStyle: true,
      credentials: localCredentials,
    });

    const opensearch = new OpenSearchClient({
      node: this.settings.opensearchUrl,
    });

    const outbox = new DynamoDBOutbox(documentClient);

    const indexingLedger = new DynamoDBIndexingLedger(documentClient);

    const publicationLedger = new DynamoDBPublicationLedger(
      documentClient,
      outbox,
    );
    const manifestLedger = new DynamoDBManifestLedger(documentClient);

    const artifactReader = createS3ArtifactReader(s3);

    const capturedPageReader = createWarcCapturedPageReader(artifactReader);

    const documentWriter = createOpenSearchDocumentWriter(opensearch);

    const compensationPublisher = createRabbitMQCompensationPublisher(
      this.settings.rabbitmqUrl,
    );

    const searchServer = createSearchServer(
      createOpenSearchDocumentReader(opensearch),
      publicationLedger,
      manifestLedger,
    );

    const worker = new SearchWorker(
      {
        rabbitmqUrl: this.settings.rabbitmqUrl,
        reconnectDelayMilliseconds: this.settings.reconnectDelayMilliseconds,
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
            publicationLedger,
          ),

        publicationEvent: (event: PublicationEvent) =>
          event.type === CRAWL_COMPLETED_EVENT
            ? processCrawlCompleted(
                event,
                artifactReader,
                manifestLedger,
                indexingLedger,
                capturedPageReader,
                documentWriter,
                this.settings.indexingLeaseDurationSeconds,
                this.settings.indexingMaxAttempts,
                publicationLedger,
              )
            : processPublicationEvent(event, publicationLedger, documentWriter),
      },
    );

    try {
      await ensureSearchIndex(opensearch);

      const port = parseInt(this.settings.httpPort, 10);

      await searchServer.listen({
        host: HOST,
        port: port,
      });

      void startOutboxWorker(
        signal,
        outbox,
        documentWriter,
        compensationPublisher,
      ).catch((error: unknown) => {
        console.error("Search outbox worker stopped", error);
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
