import { DynamoDBClient } from "@aws-sdk/client-dynamodb";
import { S3Client } from "@aws-sdk/client-s3";
import { DynamoDBDocumentClient } from "@aws-sdk/lib-dynamodb";

import { loadConfig } from "./config.js";
import { buildServer } from "./http/server.js";
import { DynamoLedger } from "./indexing/dynamodb-ledger.js";
import { Indexer } from "./indexing/indexer.js";
import { S3ArtifactStore } from "./indexing/s3-artifacts.js";
import { Consumer } from "./messaging/consumer.js";
import { Contracts } from "./messaging/contracts.js";
import { DynamoVisibility } from "./publication/dynamodb-visibility.js";
import { PublicationHandler } from "./publication/handler.js";
import { OpenSearchIndex } from "./search/opensearch.js";

async function main(): Promise<void> {
  const config = loadConfig(process.env);

  const aws = {
    region: config.awsRegion,
    ...(config.awsEndpoint ? { endpoint: config.awsEndpoint } : {}),
  };

  const dynamo = DynamoDBDocumentClient.from(new DynamoDBClient(aws), {
    marshallOptions: { removeUndefinedValues: true },
  });
  const s3 = new S3Client({ ...aws, forcePathStyle: config.awsEndpoint !== undefined });
  const index = OpenSearchIndex.connect(config.openSearchUrl, config.openSearchIndex);
  const contracts = new Contracts();
  const visibility = new DynamoVisibility(dynamo, config.visibilityTable);

  const indexer = new Indexer(
    new DynamoLedger(dynamo, config.ledgerTable, config.claimLeaseMs),
    new S3ArtifactStore(s3, config.maxArtifactBytes),
    index,
    visibility,
    { maxDocumentAttempts: config.maxDocumentAttempts },
  );

  // `publication` and `consumer` reference each other: the consumer dispatches
  // to the handler, and the handler publishes acknowledgments through the
  // consumer's broker connection. Explicit types break the inference cycle.
  const publication: PublicationHandler = new PublicationHandler(visibility, index, {
    publish: (event): Promise<void> => {
      contracts.assertOutgoing("SearchCompensated", event);

      return consumer.publish(event);
    },
  });

  let indexReady = false;

  const app = buildServer({
    searcher: index,
    // Only called by requests after listen(), when `consumer` is initialized.
    ready: () => indexReady && consumer.connected,
    logger: { level: process.env.SEARCH_LOG_LEVEL ?? "info" },
  });
  const log = app.log;

  const consumer: Consumer = new Consumer(
    {
      url: config.rabbitUrl,
      exchange: config.rabbitExchange,
      prefetch: config.rabbitPrefetch,
      maxDeliveryAttempts: config.maxDeliveryAttempts,
      retryDelayMs: config.retryDelayMs,
    },
    contracts,
    {
      PageCaptured: (message) => indexer.handle(contracts.parsePageCaptured(message)),
      ArchivePublicationDecided: (message) => {
        const event = contracts.parseArchiveFact("ArchivePublicationDecided", message);

        return publication.publicationDecided(event.archiveId, event);
      },
      ArchivePublished: (message) => {
        const event = contracts.parseArchiveFact("ArchivePublished", message);

        return publication.archivePublished(event.archiveId, event);
      },
      ArchiveCompensationDecided: (message) => {
        const event = contracts.parseCompensation(message);

        return publication.compensationDecided(event.archiveId, event.decisionVersion);
      },
    },
    log,
  );

  await app.listen({ host: config.host, port: config.port });

  const stopping = new AbortController();

  // The index must exist with its strict mapping before consuming: indexing
  // into a missing index would auto-create it with a dynamic mapping.
  const consuming = (async () => {
    await retry(
      () => index.ensureIndex(),
      stopping.signal,
      (err) => {
        log.warn({ err }, "OpenSearch not ready; retrying index setup");
      },
    );

    if (stopping.signal.aborted) {
      return;
    }

    indexReady = true;
    log.info({ index: config.openSearchIndex }, "search index ready");

    await consumer.run();
  })();

  const shutdown = async (signal: string): Promise<void> => {
    log.info({ signal }, "shutting down");
    stopping.abort();

    const timer = setTimeout(() => {
      log.error("shutdown timed out");
      process.exit(1);
    }, config.shutdownTimeoutMs);
    timer.unref();

    await app.close();
    await consumer.stop();
    await consuming.catch(() => undefined);
    s3.destroy();
    dynamo.destroy();
  };

  process.once("SIGTERM", (signal) => void shutdown(signal));
  process.once("SIGINT", (signal) => void shutdown(signal));
}

async function retry(
  operation: () => Promise<void>,
  signal: AbortSignal,
  onError: (error: unknown) => void,
): Promise<void> {
  let delayMs = 1_000;

  while (!signal.aborted) {
    try {
      await operation();

      return;
    } catch (error) {
      onError(error);
      await new Promise((resolve) => setTimeout(resolve, delayMs));
      delayMs = Math.min(delayMs * 2, 15_000);
    }
  }
}

main().catch((error: unknown) => {
  console.error(error);
  process.exit(1);
});
