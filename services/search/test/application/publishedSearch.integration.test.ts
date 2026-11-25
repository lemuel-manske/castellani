import { randomUUID } from "node:crypto";
import { expect, it } from "vitest";

import {
  ARCHIVE_PUBLICATION_DECIDED_EVENT,
  ARCHIVE_PUBLISHED_EVENT,
} from "../../src/domain.js";
import { createCapturedPageFixture } from "../support/fixtures.js";
import {
  application,
  dynamodb,
  nextPublicationEvent,
  opensearch,
  rabbitmq,
  s3,
  setupIntegrationEnvironment,
} from "../support/integrationEnvironment.js";

setupIntegrationEnvironment(["dynamodb", "opensearch", "rabbitmq", "s3"]);

it("keeps indexed snapshots hidden until the matching replay-publication acknowledgement", async () => {
  const token = randomUUID().replaceAll("-", "");

  const snapshotId = `publication-visibility-${token}`;
  const archiveId = `publication-archive-${token}`;
  const collectionId = `publication-collection-${token}`;
  const content = `Publication visibility content ${token}`;

  const fixture = createCapturedPageFixture(snapshotId, {
    archiveId,
    bucket: s3.bucketName,
    body: `<html><head><title>${content}</title></head><body><h1>${content}</h1></body></html>`,
  });

  await s3.putObject(fixture.bytes, fixture.artifact.key);

  const indexed = await application.processPageCaptured(fixture.event);

  expect(indexed).toEqual({ status: "COMPLETED", outcome: "INDEXED" });

  await dynamodb.manifestLedger.record({
    archiveId,
    manifestDigest: `manifest-${token}`,
    collectionId,
    snapshotIds: [snapshotId],
  });

  const identity = {
    archiveId,
    decisionVersion: 1,
    packageDigest: `package-${token}`,
  };

  const decisionEvent = {
    type: ARCHIVE_PUBLICATION_DECIDED_EVENT,
    version: 1,
    messageId: `publication-decision-${token}`,
    correlationId: archiveId,
    occurredAt: fixture.event.occurredAt,
    payload: identity,
  } as const;

  await rabbitmq.publishPublication(decisionEvent, decisionEvent.type);

  await expect(nextPublicationEvent()).resolves.toMatchObject({
    type: decisionEvent.type,
    payload: identity,
  });

  await opensearch.client.indices.refresh();

  const query = {
    text: token,
    collectionId,
    limit: 10,
  };

  const unpublished = await application.searchPublishedDocuments(query);

  expect(unpublished.results).toEqual([]);
  expect(unpublished.nextCursor).toBeNull();

  const acknowledgementEvent = {
    type: ARCHIVE_PUBLISHED_EVENT,
    version: 1,
    messageId: `replay-published-${token}`,
    correlationId: archiveId,
    occurredAt: fixture.event.occurredAt,
    payload: identity,
  } as const;

  await rabbitmq.publishPublication(
    acknowledgementEvent,
    acknowledgementEvent.type,
  );

  await expect(nextPublicationEvent()).resolves.toMatchObject({
    type: acknowledgementEvent.type,
    payload: identity,
  });

  const published = await application.searchPublishedDocuments(query);

  expect(published.results).toMatchObject([
    {
      archiveId,
      snapshotId,
      url: fixture.event.payload.url,
      capturedAt: fixture.event.payload.capturedAt,
      title: content,
    },
  ]);

  expect(published.results).toHaveLength(1);

  expect(published.nextCursor).toBeNull();
});
