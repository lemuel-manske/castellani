import { expect, it } from "vitest";
import {
  dynamodb,
  setupIntegrationEnvironment,
} from "../support/integrationEnvironment.js";
import type { PublicationIdentity } from "../../src/domain.js";

setupIntegrationEnvironment("dynamodb");

const identity: PublicationIdentity = {
  archiveId: "publication-archive-1",
  decisionVersion: 2,
  packageDigest: "sha256:package",
};

it("authorizes publication only after the matching replay acknowledgement", async () => {
  await dynamodb.publicationLedger.recordPublicationDecision(identity);

  await expect(
    dynamodb.publicationLedger.get(identity.archiveId),
  ).resolves.toEqual({
    publicationDecision: identity,
    replayPublication: null,
    compensationDecision: null,
  });

  await dynamodb.publicationLedger.recordReplayPublished(identity);

  await expect(
    dynamodb.publicationLedger.get(identity.archiveId),
  ).resolves.toEqual({
    publicationDecision: identity,
    replayPublication: identity,
    compensationDecision: null,
  });
});

it("accepts replay acknowledgement before the publication decision", async () => {
  await dynamodb.publicationLedger.recordReplayPublished(identity);
  await dynamodb.publicationLedger.recordPublicationDecision(identity);

  await expect(
    dynamodb.publicationLedger.get(identity.archiveId),
  ).resolves.toEqual({
    publicationDecision: identity,
    replayPublication: identity,
    compensationDecision: null,
  });
});

it("keeps duplicate publication facts idempotent", async () => {
  await dynamodb.publicationLedger.recordPublicationDecision(identity);
  await dynamodb.publicationLedger.recordPublicationDecision(identity);
  await dynamodb.publicationLedger.recordReplayPublished(identity);
  await dynamodb.publicationLedger.recordReplayPublished(identity);

  await expect(
    dynamodb.publicationLedger.get(identity.archiveId),
  ).resolves.toEqual({
    publicationDecision: identity,
    replayPublication: identity,
    compensationDecision: null,
  });
});

it("rejects a conflicting publication identity", async () => {
  await dynamodb.publicationLedger.recordPublicationDecision(identity);

  await expect(
    dynamodb.publicationLedger.recordPublicationDecision({
      ...identity,
      packageDigest: "sha256:other",
    }),
  ).rejects.toThrow("conflicting publication decision");
});

it("prevents publication after compensation", async () => {
  await dynamodb.publicationLedger.recordCompensationDecision({
    archiveId: identity.archiveId,
    decisionVersion: identity.decisionVersion,
    reasonCode: "capture_failed",
  });

  await expect(
    dynamodb.publicationLedger.recordPublicationDecision(identity),
  ).rejects.toThrow("a compensated archive cannot be published");
});
