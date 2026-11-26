import { createHash, randomUUID } from "node:crypto";
import { expect, it } from "vitest";

import {
  ARCHIVE_COMPENSATION_DECIDED_EVENT,
  ARCHIVE_PUBLICATION_DECIDED_EVENT,
  ARCHIVE_PUBLISHED_EVENT,
  CRAWL_COMPLETED_EVENT,
  SEARCH_INDEXING_COMPLETED_EVENT,
  SEARCH_READY_EVENT,
} from "../../src/domain.js";

import { createCapturedPageFixture } from "../support/fixtures.js";
import {
  application,
  dynamodb,
  nextPublicationEvent,
  rabbitmq,
  s3,
  setupIntegrationEnvironment,
} from "../support/integrationEnvironment.js";

import { bufferJSON } from "../../src/utils.js";

setupIntegrationEnvironment(["dynamodb", "opensearch", "rabbitmq", "s3"]);

const NO_EVENT_WAIT_MILLISECONDS = 750;

function eventId(): string {
  return randomUUID().replaceAll("-", "");
}

async function recordManifest(
  archiveId: string,
  manifestDigest: string,
  snapshotIds: string[],
): Promise<void> {
  await dynamodb.manifestLedger.record(
    {
      archiveId,
      manifestDigest,
      collectionId: `events-collection-${archiveId}`,
      snapshotIds,
    },
    `manifest-${archiveId}`,
  );
}

async function indexSnapshot(
  archiveId: string,
  snapshotId: string,
  body: string,
): Promise<void> {
  const fixture = createCapturedPageFixture(snapshotId, {
    archiveId,
    bucket: s3.bucketName,
    body,
  });

  await s3.putObject(fixture.bytes, fixture.artifact.key);
  await application.processPageCaptured(fixture.event);
}

async function markFailed(
  archiveId: string,
  snapshotId: string,
): Promise<void> {
  const result = await dynamodb.ledger.claim(
    archiveId,
    snapshotId,
    `failed-${snapshotId}`,
    120,
    5,
  );

  if (result.status !== "CLAIMED") {
    throw new Error(`could not claim failed snapshot ${snapshotId}`);
  }

  await dynamodb.ledger.complete(
    result.claim,
    "FAILED",
    "integration-indexing-failure",
  );
}

it("emits one aggregate completion with distinct outcome counts", async () => {
  const token = eventId();
  const archiveId = `events-counts-${token}`;
  const manifestDigest = `events-digest-${token}`;
  const indexedSnapshot = `events-indexed-${token}`;
  const failedSnapshot = `events-failed-${token}`;
  const unsupportedSnapshot = `events-unsupported-${token}`;

  await indexSnapshot(
    archiveId,
    indexedSnapshot,
    `<html><body><h1>indexed ${token}</h1></body></html>`,
  );
  await markFailed(archiveId, failedSnapshot);
  await indexSnapshot(archiveId, unsupportedSnapshot, "");

  await recordManifest(archiveId, manifestDigest, [
    indexedSnapshot,
    failedSnapshot,
    unsupportedSnapshot,
  ]);

  await application.report(archiveId);
  await application.drainOutbox();

  await expect(
    rabbitmq.nextEvent(SEARCH_INDEXING_COMPLETED_EVENT, archiveId),
  ).resolves.toMatchObject({
    messageId: `${archiveId}:${manifestDigest}`,
    correlationId: archiveId,
    type: SEARCH_INDEXING_COMPLETED_EVENT,
    version: 1,
    payload: {
      archiveId,
      manifestDigest,
      expected: 3,
      indexed: 1,
      failed: 1,
      unsupported: 1,
    },
  });

  await application.report(archiveId);
  await application.drainOutbox();

  expect(
    await rabbitmq.nextEvent(
      SEARCH_INDEXING_COMPLETED_EVENT,
      NO_EVENT_WAIT_MILLISECONDS,
    ),
  ).toBeUndefined();
});

it("emits SearchReady only after matching publication and replay facts", async () => {
  const token = eventId();
  const archiveId = `events-ready-${token}`;
  const manifestDigest = `events-ready-digest-${token}`;
  const snapshotId = `events-ready-snapshot-${token}`;
  const identity = {
    archiveId,
    decisionVersion: 2,
    packageDigest: `events-package-${token}`,
  };

  await indexSnapshot(
    archiveId,
    snapshotId,
    `<html><body><h1>ready ${token}</h1></body></html>`,
  );
  await recordManifest(archiveId, manifestDigest, [snapshotId]);

  await application.report(archiveId);
  await application.drainOutbox();

  expect(
    await rabbitmq.nextEvent(SEARCH_READY_EVENT, archiveId, NO_EVENT_WAIT_MILLISECONDS),
  ).toBeUndefined();

  await application.processPublicationEvent({
    type: ARCHIVE_PUBLICATION_DECIDED_EVENT,
    version: 1,
    messageId: `decision-${token}`,
    correlationId: archiveId,
    occurredAt: new Date().toISOString(),
    payload: identity,
  });

  await application.drainOutbox();

  expect(
    await rabbitmq.nextEvent(SEARCH_READY_EVENT, archiveId, NO_EVENT_WAIT_MILLISECONDS),
  ).toBeUndefined();

  await application.processPublicationEvent({
    type: ARCHIVE_PUBLISHED_EVENT,
    version: 1,
    messageId: `replay-${token}`,
    correlationId: archiveId,
    occurredAt: new Date().toISOString(),
    payload: identity,
  });

  await application.drainOutbox();

  await expect(rabbitmq.nextEvent(SEARCH_READY_EVENT, archiveId)).resolves.toMatchObject({
    messageId: `${archiveId}:2:${manifestDigest}`,
    correlationId: archiveId,
    type: SEARCH_READY_EVENT,
    version: 1,
    payload: {
      archiveId,
      decisionVersion: 2,
      manifestDigest,
    },
  });

  await application.processPublicationEvent({
    type: ARCHIVE_PUBLISHED_EVENT,
    version: 1,
    messageId: `replay-duplicate-${token}`,
    correlationId: archiveId,
    occurredAt: new Date().toISOString(),
    payload: identity,
  });

  await application.drainOutbox();

  expect(
    await rabbitmq.nextEvent(SEARCH_READY_EVENT, archiveId, NO_EVENT_WAIT_MILLISECONDS),
  ).toBeUndefined();
});

it("reports completion when CrawlCompleted arrives before its page event", async () => {
  const token = eventId();
  const archiveId = `events-late-${token}`;
  const snapshotId = `events-late-snapshot-${token}`;
  const content = `Late page content ${token}`;

  const fixture = createCapturedPageFixture(snapshotId, {
    archiveId,
    bucket: s3.bucketName,
    body: `<html><body><h1>${content}</h1></body></html>`,
  });

  await s3.putObject(fixture.bytes, fixture.artifact.key);

  const manifest = {
    schemaVersion: 1,
    archiveId,
    collectionId: `events-late-collection-${token}`,
    normalizerVersion: "v1",
    seedUrl: fixture.event.payload.url,
    createdAt: "2026-11-22T10:00:00.000Z",
    snapshots: [
      {
        snapshotId,
        urlKey: fixture.event.payload.urlKey,
        url: fixture.event.payload.url,
        finalUrl: fixture.event.payload.finalUrl,
        redirectChain: fixture.event.payload.redirectChain,
        capturedAt: fixture.event.payload.capturedAt,
        warcArtifacts: fixture.event.payload.warcArtifacts,
      },
    ],
    failedPages: [],
  };

  const manifestBytes = bufferJSON(manifest);
  const manifestDigest = createHash("sha256")
    .update(manifestBytes)
    .digest("hex");
  const manifestKey = `${archiveId}/manifest.json`;

  await s3.putObject(manifestBytes, manifestKey);

  await rabbitmq.publishPublication(
    {
      type: CRAWL_COMPLETED_EVENT,
      version: 1,
      messageId: `crawl-${token}`,
      correlationId: archiveId,
      occurredAt: manifest.createdAt,
      payload: {
        archiveId,
        manifestDigest,
        manifest: {
          bucket: s3.bucketName,
          key: manifestKey,
          sha256: manifestDigest,
          sizeBytes: manifestBytes.byteLength,
        },
        seedSucceeded: true,
        capturedCount: 1,
        failedCount: 0,
      },
    },
    CRAWL_COMPLETED_EVENT,
  );

  await expect(nextPublicationEvent()).resolves.toMatchObject({
    type: CRAWL_COMPLETED_EVENT,
    payload: { archiveId, manifestDigest },
  });

  await application.drainOutbox();

  await expect(
    rabbitmq.nextEvent(SEARCH_INDEXING_COMPLETED_EVENT, archiveId),
  ).resolves.toMatchObject({
    correlationId: archiveId,
    payload: {
      archiveId,
      manifestDigest,
      expected: 1,
      indexed: 1,
      failed: 0,
      unsupported: 0,
    },
  });
});

it("does not report completion or readiness for a compensated archive", async () => {
  const token = eventId();
  const archiveId = `events-compensated-${token}`;
  const manifestDigest = `events-compensated-digest-${token}`;
  const snapshotId = `events-compensated-snapshot-${token}`;

  await indexSnapshot(
    archiveId,
    snapshotId,
    `<html><body><h1>compensated ${token}</h1></body></html>`,
  );
  await recordManifest(archiveId, manifestDigest, [snapshotId]);

  await application.processPublicationEvent({
    type: ARCHIVE_COMPENSATION_DECIDED_EVENT,
    version: 1,
    messageId: `compensation-${token}`,
    correlationId: archiveId,
    occurredAt: new Date().toISOString(),
    payload: {
      archiveId,
      decisionVersion: 1,
      reasonCode: "seed-capture-failed",
    },
  });

  await application.report(archiveId);
  await application.drainOutbox();

  expect(
    await rabbitmq.nextEvent(
      SEARCH_INDEXING_COMPLETED_EVENT,
      NO_EVENT_WAIT_MILLISECONDS,
    ),
  ).toBeUndefined();

  expect(
    await rabbitmq.nextEvent(SEARCH_READY_EVENT, archiveId, NO_EVENT_WAIT_MILLISECONDS),
  ).toBeUndefined();
});
