import { expect, it } from "vitest";
import {
  dynamodb,
  nextPublicationEvent,
  rabbitmq,
  setupIntegrationEnvironment,
} from "../support/integrationEnvironment.js";
import { isPublicationAuthorized } from "../../src/domain/publication.js";

setupIntegrationEnvironment(["dynamodb", "rabbitmq"]);

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

it("receives CrawlCompleted manifest references from the events exchange", async () => {
  const event = {
    messageId: "crawl-completed-message",
    correlationId: "crawl-completed-archive",
    type: "CrawlCompleted",
    version: 1,
    occurredAt: "2026-11-22T12:00:00.000Z",
    payload: {
      archiveId: "crawl-completed-archive",
      manifestDigest: "a".repeat(64),
      manifest: {
        bucket: "archive-manifests",
        key: "archives/crawl-completed-archive/manifest.json",
        sha256: "a".repeat(64),
        sizeBytes: 128,
      },
    },
  };
  const delivered = nextPublicationEvent();

  await rabbitmq.publishPublication(event, event.type);

  await expect(delivered).resolves.toMatchObject({
    type: "CrawlCompleted",
    payload: {
      archiveId: event.payload.archiveId,
      manifestDigest: event.payload.manifestDigest,
      manifest: event.payload.manifest,
    },
  });
});
