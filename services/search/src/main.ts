import { DynamoDBClient } from "@aws-sdk/client-dynamodb";
import { S3Client } from "@aws-sdk/client-s3";
import { DynamoDBDocumentClient } from "@aws-sdk/lib-dynamodb";

import { loadConfig } from "./config.js";
import { buildServer } from "./http/server.js";
import { DynamoLedger } from "./indexing/dynamodb-ledger.js";
import { Indexer } from "./indexing/indexer.js";
import { S3ArtifactStore } from "./indexing/s3-artifacts.js";
import { Consumer } from "./messaging/consumer.js";
import { Contracts, type MessageType } from "./messaging/contracts.js";
import { DynamoInbox } from "./messaging/inbox.js";
import { DynamoOutbox } from "./outbox/dynamodb-outbox.js";
import { type EventPublisher, OutboxDispatcher } from "./outbox/outbox.js";
import { DynamoPublications } from "./publication/dynamodb-publications.js";
import { PublicationHandler } from "./publication/handler.js";
import { ReconcileScheduler, Reconciler, RepairSweep } from "./reconciliation/reconciler.js";
import { OpenSearchIndex } from "./search/opensearch.js";

/** How long a dispatcher holds an outbox record while awaiting the broker's confirm. */
const OUTBOX_LEASE_MS = 30_000;

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
  // Enqueued reports wake the dispatcher, declared further down.
  const visibility = new DynamoPublications(dynamo, config.publicationsTable, config.outboxTable, () => {
    dispatcher.wake();
  });
  const ledger = new DynamoLedger(dynamo, config.ledgerTable, config.claimLeaseMs);
  const artifacts = new S3ArtifactStore(s3, config.maxArtifactBytes);

  let indexReady = false;

  // Closures here reference `consumer` and `dispatcher`, declared further
  // down: they only run after startup, once both are initialized.
  const app = buildServer({
    searcher: index,
    ready: () => indexReady && consumer.connected,
    logger: { level: process.env.SEARCH_LOG_LEVEL ?? "info" },
  });
  const log = app.log;

  // Outbox records are validated against their contract, then published with
  // confirms through the consumer's broker connection.
  const publisher: EventPublisher = {
    publish: (event) => {
      contracts.assertOutgoing(event.type as MessageType, event);

      return consumer.publish(event);
    },
  };

  const indexer = new Indexer(ledger, artifacts, index, visibility, {
    maxDocumentAttempts: config.maxDocumentAttempts,
  });
  const reconciler = new Reconciler(visibility, ledger, indexer, artifacts, contracts, index, log);
  const scheduler = new ReconcileScheduler(reconciler, visibility, config.reconcileIntervalMs, log);
  const dispatcher: OutboxDispatcher = new OutboxDispatcher(
    new DynamoOutbox(dynamo, config.outboxTable, OUTBOX_LEASE_MS),
    publisher,
    { intervalMs: config.outboxIntervalMs },
    log,
  );

  // Durable first, so the periodic pass finds the request after a crash.
  const requestReconcile = async (archiveId: string): Promise<void> => {
    await visibility.requestReconcile(archiveId);
    scheduler.schedule(archiveId);
  };
  const repair = new RepairSweep(visibility, requestReconcile, config.repairIntervalMs, log);

  const publication = new PublicationHandler(visibility, index, { request: requestReconcile }, reconciler);

  const consumer: Consumer = new Consumer(
    {
      url: config.rabbitUrl,
      exchange: config.rabbitExchange,
      prefetch: config.rabbitPrefetch,
      maxDeliveryAttempts: config.maxDeliveryAttempts,
      retryDelayMs: config.retryDelayMs,
    },
    contracts,
    new DynamoInbox(dynamo, config.inboxTable, config.inboxRetentionMs),
    {
      PageCaptured: (message) => indexer.handle(contracts.parsePageCaptured(message)),
      CrawlCompleted: (message) => {
        const event = contracts.parseCrawlCompleted(message);

        return publication.crawlCompleted(event.archiveId, event.manifest, event.manifestDigest);
      },
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
  const running = (async () => {
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

    await Promise.all([consumer.run(), scheduler.run(), dispatcher.run(), repair.run()]);
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
    scheduler.stop();
    dispatcher.stop();
    repair.stop();
    await consumer.stop();
    await running.catch(() => undefined);
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
