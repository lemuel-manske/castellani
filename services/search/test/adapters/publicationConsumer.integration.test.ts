import { createHash } from "node:crypto";
import { expect, it } from "vitest";
import {
  dynamodb,
  nextPublicationEvent,
  opensearch,
  s3,
  rabbitmq,
  setupIntegrationEnvironment,
} from "../support/integrationEnvironment.js";
import { isPublicationAuthorized } from "../../src/domain/publication.js";
import { createCapturedPageFixture } from "../support/fixtures.js";

setupIntegrationEnvironment(["dynamodb", "rabbitmq", "s3", "opensearch"]);

it("persists publication decisions and replay acknowledgements delivered through RabbitMQ", async () => {
  const identity = {
    archiveId: "rabbitmq-publication-archive",
    decisionVersion: 3,
    packageDigest: "sha256:rabbitmq-package",
  };
  const publicationDecision = {
    messageId: "publication-event-message",
    correlationId: identity.archiveId,
    type: "ArchivePublicationDecided",
    version: 1,
    occurredAt: "2026-11-22T12:00:00.000Z",
    payload: identity,
  };
  const replayPublished = {
    ...publicationDecision,
    messageId: "replay-published-event-message",
    type: "ArchivePublished",
  };
  const decisionDelivery = nextPublicationEvent();

  await rabbitmq.publishPublication(
    publicationDecision,
    publicationDecision.type,
  );

  await expect(decisionDelivery).resolves.toEqual({
    type: "ArchivePublicationDecided",
    payload: identity,
  });

  const replayDelivery = nextPublicationEvent();

  await rabbitmq.publishPublication(replayPublished, replayPublished.type);

  await expect(replayDelivery).resolves.toEqual({
    type: "ArchivePublished",
    payload: identity,
  });

  const facts = await dynamodb.publicationLedger.get(identity.archiveId);

  expect(isPublicationAuthorized(facts)).toBe(true);
});

it("dead-letters malformed publication event envelopes", async () => {
  const deadLetter = rabbitmq.nextPublicationDeadLetter();

  await rabbitmq.publishPublication(
    { messageId: "malformed-publication-message" },
    "ArchivePublicationDecided",
  );

  const message = await deadLetter;

  expect(message.content.toString("utf8")).toBe(
    JSON.stringify({ messageId: "malformed-publication-message" }),
  );
});

it("recovers missing PageCaptured indexing from the immutable manifest", async () => {
  const fixture = createCapturedPageFixture("recovered-manifest-snapshot", {
    bucket: s3.bucketName,
  });
  await s3.putObject(fixture.bytes, fixture.artifact.key);

  const manifest = {
    schemaVersion: 1,
    archiveId: fixture.page.archiveId,
    collectionId: "manifest-recovery-collection",
    normalizerVersion: "v1",
    seedUrl: fixture.page.url,
    createdAt: fixture.page.capturedAt,
    snapshots: [
      {
        snapshotId: fixture.page.snapshotId,
        urlKey: fixture.event.payload.urlKey,
        url: fixture.page.url,
        finalUrl: fixture.page.finalUrl,
        redirectChain: fixture.event.payload.redirectChain,
        capturedAt: fixture.page.capturedAt,
        contentType: "text/html; charset=utf-8",
        warcArtifacts: [fixture.artifact],
      },
    ],
    failedPages: [],
  };
  const manifestBytes = Buffer.from(JSON.stringify(manifest));
  const manifestDigest = createHash("sha256")
    .update(manifestBytes)
    .digest("hex");
  const manifestKey = "archives/manifest-recovery-archive/manifest.json";
  await s3.putObject(manifestBytes, manifestKey);

  const event = {
    messageId: "crawl-completed-recovery-message",
    correlationId: fixture.page.archiveId,
    type: "CrawlCompleted",
    version: 1,
    occurredAt: fixture.page.capturedAt,
    payload: {
      archiveId: fixture.page.archiveId,
      manifestDigest,
      manifest: {
        bucket: s3.bucketName,
        key: manifestKey,
        sha256: manifestDigest,
        sizeBytes: manifestBytes.byteLength,
      },
    },
  };
  const delivered = nextPublicationEvent();

  await rabbitmq.publishPublication(event, event.type);

  await expect(delivered).resolves.toMatchObject({
    type: "CrawlCompleted",
    payload: {
      archiveId: fixture.page.archiveId,
      manifestDigest,
    },
  });

  await expect(
    dynamodb.manifestLedger.contains(
      fixture.page.archiveId,
      fixture.page.snapshotId,
      "manifest-recovery-collection",
    ),
  ).resolves.toBe(true);

  await opensearch.client.indices.refresh({ index: opensearch.indexName });

  const indexed = await opensearch.client.get({
    index: opensearch.indexName,
    id: fixture.page.snapshotId,
  });

  expect(indexed.body._source).toMatchObject({
    archiveId: fixture.page.archiveId,
    snapshotId: fixture.page.snapshotId,
    text: "Integrated content",
  });
});
