import { createHash, randomUUID } from "node:crypto";
import { expect, it } from "vitest";

import { CRAWL_COMPLETED_EVENT } from "../../src/domain.js";
import { createCapturedPageFixture } from "../support/fixtures.js";
import {
  dynamodb,
  nextPublicationEvent,
  opensearch,
  rabbitmq,
  s3,
  searchIndex,
  setupIntegrationEnvironment,
} from "../support/integrationEnvironment.js";
import { bufferJSON } from "../../src/utils.js";

setupIntegrationEnvironment(["dynamodb", "opensearch", "rabbitmq", "s3"]);

it("indexes the snapshots described by a CrawlCompleted manifest delivered through RabbitMQ", async () => {
  const token = randomUUID().replaceAll("-", "");

  const archiveId = `crawl-completed-${token}`;
  const snapshotId = `manifest-snapshot-${token}`;
  const collectionId = `collection-${token}`;
  const content = `Manifest indexed content ${token}`;

  const fixture = createCapturedPageFixture(snapshotId, {
    archiveId,
    bucket: s3.bucketName,
    body: `<html><head><title>${content}</title></head><body><h1>${content}</h1></body></html>`,
  });

  await s3.putObject(fixture.bytes, fixture.artifact.key);

  const manifest = {
    schemaVersion: 1,
    archiveId,
    collectionId,
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
      messageId: `crawl-completed-message-${token}`,
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
        capturedCount: manifest.snapshots.length,
        failedCount: 0,
      },
    },
    CRAWL_COMPLETED_EVENT,
  );

  const event = await nextPublicationEvent();

  expect(event).toMatchObject({
    type: CRAWL_COMPLETED_EVENT,
    payload: {
      archiveId,
      manifestDigest,
    },
  });

  expect(
    await dynamodb.manifestLedger.contains(archiveId, snapshotId, collectionId),
  ).toBe(true);

  expect(await dynamodb.getManifestMetadata(archiveId)).toMatchObject({
    manifestDigest,
    collectionId,
    processedMessageIds: [event.messageId],
  });

  await expect(
    dynamodb.manifestLedger.record(
      {
        archiveId,
        manifestDigest,
        collectionId,
        snapshotIds: [snapshotId, `extra-${snapshotId}`],
      },
      event.messageId,
    ),
  ).rejects.toThrow("archive manifest changed concurrently");

  const indexingEntry = await dynamodb.getIndexingEntry(snapshotId);

  expect(indexingEntry).toMatchObject({
    archiveId,
    snapshotId,
    state: "INDEXED",
    attempts: 1,
  });

  await opensearch.client.indices.refresh();

  const indexed = await searchIndex.search({ text: token }, 10);

  expect(indexed.candidates).toMatchObject([
    {
      document: {
        archiveId,
        snapshotId,
        url: fixture.event.payload.url,
        finalUrl: fixture.event.payload.finalUrl,
        title: content,
      },
    },
  ]);

  expect(indexed.nextCursor).toBeNull();
});
