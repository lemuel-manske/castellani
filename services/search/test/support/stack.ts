import { DynamoDBClient } from "@aws-sdk/client-dynamodb";
import { PutObjectCommand, S3Client } from "@aws-sdk/client-s3";
import { DynamoDBDocumentClient, GetCommand } from "@aws-sdk/lib-dynamodb";
import { type ChannelModel, connect } from "amqplib";
import { afterAll } from "vitest";

import type { ArtifactRef } from "../../src/indexing/model.js";
import { DEAD_QUEUE } from "../../src/messaging/consumer.js";
import { artifactRefFor, buildWarc } from "./warc.js";

/**
 * Fixtures for the running Compose stack. Configure with:
 * SEARCH_TEST_URL, SEARCH_TEST_AWS_ENDPOINT, SEARCH_TEST_RABBITMQ_URL.
 */
const env = {
  searchUrl: process.env.SEARCH_TEST_URL ?? "http://search:8082",
  awsEndpoint: process.env.SEARCH_TEST_AWS_ENDPOINT ?? "http://ministack:4566",
  rabbitUrl: process.env.SEARCH_TEST_RABBITMQ_URL ?? "amqp://castellani:local-development-only@rabbitmq:5672/",
  exchange: "castellani.events",
  bucket: "castellani-archive-artifacts",
  openSearchUrl:
    process.env.SEARCH_TEST_OPENSEARCH_URL ?? "http://ministack-opensearch-281afe4a44d7-castellani-search:9200",
  index: "snapshots-v1",
};

/**
 * Deletes a snapshot's document straight from OpenSearch, bypassing Search,
 * as a lost or rebuilt index would. The ledger still records it `INDEXED`.
 */
export async function loseDocument(archiveId: string, snapshotId: string): Promise<void> {
  const id = encodeURIComponent(`${archiveId}/${snapshotId}`);
  const response = await fetch(`${env.openSearchUrl}/${env.index}/_doc/${id}?refresh=true`, { method: "DELETE" });

  if (!response.ok) {
    throw new Error(`could not delete document ${id}: HTTP ${String(response.status)}`);
  }
}

const s3 = new S3Client({
  region: "us-east-1",
  endpoint: env.awsEndpoint,
  forcePathStyle: true,
  credentials: { accessKeyId: "test", secretAccessKey: "test" },
});

const dynamo = DynamoDBDocumentClient.from(
  new DynamoDBClient({
    region: "us-east-1",
    endpoint: env.awsEndpoint,
    credentials: { accessKeyId: "test", secretAccessKey: "test" },
  }),
);

let broker: ChannelModel | undefined;

afterAll(async () => {
  await broker?.close();
  s3.destroy();
  dynamo.destroy();
});

/** Waits until Search's own ledger records `status` for a snapshot of the archive. */
export async function ledgerReaches(
  snapshot: { archiveId: string; snapshotId: string },
  status: string,
  timeoutMs = 20_000,
): Promise<void> {
  const { archiveId, snapshotId } = snapshot;
  const deadline = Date.now() + timeoutMs;
  let current: unknown;

  while (Date.now() < deadline) {
    const { Item: item } = await dynamo.send(
      new GetCommand({ TableName: "search_indexing_ledger", Key: { archiveId, snapshotId }, ConsistentRead: true }),
    );
    current = item?.status;

    if (current === status) {
      return;
    }

    await sleep(250);
  }

  throw new Error(`snapshot ${snapshotId} did not reach ${status} within ${timeoutMs}ms (last: ${String(current)})`);
}

/** Waits until Search's inbox records a consumed message, returning the record. */
export async function inboxRecord(messageId: string, timeoutMs = 20_000): Promise<Record<string, unknown> | undefined> {
  const deadline = Date.now() + timeoutMs;

  while (Date.now() < deadline) {
    const { Item: item } = await dynamo.send(
      new GetCommand({ TableName: "search_inbox", Key: { messageId }, ConsistentRead: true }),
    );

    if (item !== undefined) {
      return item;
    }

    await sleep(250);
  }

  return undefined;
}

/** Reads Search's outbox record for an emitted event. */
export async function outboxRecord(messageId: string): Promise<Record<string, unknown> | undefined> {
  const { Item: item } = await dynamo.send(
    new GetCommand({ TableName: "search_outbox", Key: { messageId }, ConsistentRead: true }),
  );

  return item;
}

/** Stores a single-page WARC in the artifacts bucket, as Capture would. */
export async function storeCapturedPage(url: string, html: string): Promise<ArtifactRef> {
  const warc = await buildWarc([{ url, body: html }]);
  const key = `test/${crypto.randomUUID()}.warc.gz`;

  await s3.send(new PutObjectCommand({ Bucket: env.bucket, Key: key, Body: warc }));

  return { ...artifactRefFor(warc, key), bucket: env.bucket };
}

/** A manifest entry, as Capture lists each authorized snapshot. */
export type SnapshotEntry = {
  snapshotId: string;
  urlKey: string;
  url: string;
  finalUrl?: string;
  capturedAt: string;
  warcArtifacts: ArtifactRef[];
};

/**
 * Stores the final manifest for `entries` and publishes `CrawlCompleted`,
 * as Capture does when the frontier closes. Returns the manifest digest.
 */
export async function completeCrawl(
  archiveId: string,
  entries: SnapshotEntry[],
  options: { collectionId?: string } = {},
): Promise<string> {
  const manifest = {
    schemaVersion: 1,
    archiveId,
    ...(options.collectionId !== undefined ? { collectionId: options.collectionId } : {}),
    normalizerVersion: "1",
    seedUrl: "https://example.org/",
    createdAt: new Date().toISOString(),
    // Only the fields of the manifest schema: it rejects additional properties.
    snapshots: entries.map((entry) => ({
      snapshotId: entry.snapshotId,
      urlKey: entry.urlKey,
      url: entry.url,
      finalUrl: entry.finalUrl ?? entry.url,
      capturedAt: entry.capturedAt,
      warcArtifacts: entry.warcArtifacts,
    })),
    failedPages: [],
  };
  const bytes = Buffer.from(JSON.stringify(manifest));
  const key = `test/${archiveId}/manifest.json`;
  await s3.send(new PutObjectCommand({ Bucket: env.bucket, Key: key, Body: bytes }));
  const ref = { ...artifactRefFor(bytes, key), bucket: env.bucket };
  const digest = `sha256:${ref.sha256}`;

  await publish(
    archiveEvent("CrawlCompleted", archiveId, {
      manifest: ref,
      manifestDigest: digest,
      seedSucceeded: true,
      capturedCount: entries.length,
      failedCount: 0,
    }),
  );

  return digest;
}

/** Publishes an event to the shared exchange with confirms, routed by type. */
export async function publish(message: Record<string, unknown>): Promise<void> {
  broker ??= await connect(env.rabbitUrl);
  const channel = await broker.createConfirmChannel();

  channel.publish(env.exchange, String(message.type), Buffer.from(JSON.stringify(message)), {
    persistent: true,
    contentType: "application/json",
    messageId: String(message.messageId),
  });
  await channel.waitForConfirms();
  await channel.close();
}

/** An archive-scoped event, as the Coordinator or Capture would publish it. */
export function archiveEvent(type: string, archiveId: string, payload: Record<string, unknown>) {
  return {
    messageId: crypto.randomUUID(),
    correlationId: archiveId,
    type,
    version: 1,
    occurredAt: new Date().toISOString(),
    payload: { archiveId, ...payload },
  };
}

export const PACKAGE = { decisionVersion: 1, packageDigest: "sha256:integration-package" };

/**
 * Publishes the Coordinator's decision and Capture's replay acknowledgment,
 * returning their message IDs.
 */
export async function publishArchive(archiveId: string): Promise<string[]> {
  const decided = archiveEvent("ArchivePublicationDecided", archiveId, PACKAGE);
  const published = archiveEvent("ArchivePublished", archiveId, PACKAGE);

  await publish(decided);
  await publish(published);

  return [decided.messageId, published.messageId];
}

/**
 * Binds a temporary queue to `type` on the shared exchange, so a test can
 * observe events Search emits. Call before triggering the emission.
 */
export async function observe(type: string): Promise<{ next(timeoutMs?: number): Promise<Record<string, unknown>> }> {
  broker ??= await connect(env.rabbitUrl);
  const channel = await broker.createChannel();
  const { queue } = await channel.assertQueue("", { exclusive: true, autoDelete: true });
  await channel.bindQueue(queue, env.exchange, type);

  return {
    async next(timeoutMs = 15_000) {
      const deadline = Date.now() + timeoutMs;

      try {
        while (Date.now() < deadline) {
          const message = await channel.get(queue, { noAck: true });

          if (message !== false) {
            return JSON.parse(message.content.toString("utf8")) as Record<string, unknown>;
          }

          await sleep(250);
        }

        throw new Error(`no ${type} event within ${timeoutMs}ms`);
      } finally {
        await channel.close();
      }
    },
  };
}

/** Raw bytes publication, for messages that are not valid JSON. */
export async function publishRaw(type: string, body: string, messageId: string): Promise<void> {
  broker ??= await connect(env.rabbitUrl);
  const channel = await broker.createConfirmChannel();

  channel.publish(env.exchange, type, Buffer.from(body), { persistent: true, messageId });
  await channel.waitForConfirms();
  await channel.close();
}

/** Waits until a message with `messageId` reaches Search's dead-letter queue. */
export async function deadLettered(messageId: string, timeoutMs = 15_000): Promise<boolean> {
  broker ??= await connect(env.rabbitUrl);
  const channel = await broker.createChannel();
  const deadline = Date.now() + timeoutMs;

  try {
    while (Date.now() < deadline) {
      const message = await channel.get(DEAD_QUEUE, { noAck: false });

      if (message === false) {
        await sleep(250);
        continue;
      }

      // Unrelated dead letters stay unacknowledged so the next `get` moves
      // past them (a requeue would return the same message again); closing
      // the channel puts them back for whoever owns them.
      if (message.properties.messageId === messageId) {
        channel.ack(message);

        return true;
      }
    }

    return false;
  } finally {
    await channel.close();
  }
}

export type SearchResponse = {
  status: number;
  body: { results: Record<string, unknown>[]; nextCursor: string | null };
};

export async function search(params: Record<string, string>): Promise<SearchResponse> {
  const response = await fetch(`${env.searchUrl}/search?${new URLSearchParams(params).toString()}`);

  return { status: response.status, body: (await response.json()) as SearchResponse["body"] };
}

/** Polls `search` until `predicate` holds, failing after `timeoutMs`. */
export async function searchUntil(
  params: Record<string, string>,
  predicate: (response: SearchResponse) => boolean,
  timeoutMs = 20_000,
): Promise<SearchResponse> {
  const deadline = Date.now() + timeoutMs;
  let last = await search(params);

  while (!predicate(last)) {
    if (Date.now() > deadline) {
      throw new Error(`search condition not met within ${timeoutMs}ms; last response ${JSON.stringify(last)}`);
    }

    await sleep(250);
    last = await search(params);
  }

  return last;
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
