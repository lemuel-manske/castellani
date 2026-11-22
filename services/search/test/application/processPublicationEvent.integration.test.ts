import { expect, it } from "vitest";
import { isPublicationAuthorized } from "../../src/domain/publication.js";
import { processPublicationEvent } from "../../src/application/processPublicationEvent.js";
import { dynamodb, setupIntegrationEnvironment } from "../support/integrationEnvironment.js";

setupIntegrationEnvironment("dynamodb");

it("persists publication facts regardless of event delivery order", async () => {
  const identity = {
    archiveId: "publication-event-order-archive",
    decisionVersion: 4,
    packageDigest: "sha256:published-package",
  };

  await processPublicationEvent(
    { type: "ArchivePublished", payload: identity },
    dynamodb.publicationLedger,
  );

  await expect(
    dynamodb.publicationLedger.get(identity.archiveId),
  ).resolves.toMatchObject({
    publicationDecision: null,
    replayPublication: identity,
    compensationDecision: null,
  });

  await processPublicationEvent(
    { type: "ArchivePublicationDecided", payload: identity },
    dynamodb.publicationLedger,
  );

  const facts = await dynamodb.publicationLedger.get(identity.archiveId);

  expect(facts).toEqual({
    publicationDecision: identity,
    replayPublication: identity,
    compensationDecision: null,
  });
  expect(isPublicationAuthorized(facts)).toBe(true);
});

it("persists compensation decisions as terminal non-publication facts", async () => {
  const decision = {
    archiveId: "compensated-event-archive",
    decisionVersion: 2,
    reasonCode: "seed_capture_failed",
  };

  await processPublicationEvent(
    { type: "ArchiveCompensationDecided", payload: decision },
    dynamodb.publicationLedger,
  );

  const facts = await dynamodb.publicationLedger.get(decision.archiveId);

  expect(facts).toEqual({
    publicationDecision: null,
    replayPublication: null,
    compensationDecision: decision,
  });
  expect(isPublicationAuthorized(facts)).toBe(false);
});
