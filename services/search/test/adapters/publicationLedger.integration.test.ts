import { expect, it } from "vitest";
import {
  dynamodb,
  setupIntegrationEnvironment,
} from "../support/integrationEnvironment.js";
import type { PublicationIdentity } from "../../src/domain.js";

setupIntegrationEnvironment("dynamodb");

const identity: PublicationIdentity = {
  archiveId: "publication-decision-archive",
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
  const replayFirstIdentity = {
    ...identity,
    archiveId: "publication-replay-first-archive",
  };
  await dynamodb.publicationLedger.recordReplayPublished(
    replayFirstIdentity,
  );
  await dynamodb.publicationLedger.recordPublicationDecision(
    replayFirstIdentity,
  );

  await expect(
    dynamodb.publicationLedger.get(replayFirstIdentity.archiveId),
  ).resolves.toEqual({
    publicationDecision: replayFirstIdentity,
    replayPublication: replayFirstIdentity,
    compensationDecision: null,
  });
});

it("keeps duplicate publication facts idempotent", async () => {
  const duplicateIdentity = {
    ...identity,
    archiveId: "publication-duplicate-archive",
  };
  await dynamodb.publicationLedger.recordPublicationDecision(
    duplicateIdentity,
  );
  await dynamodb.publicationLedger.recordPublicationDecision(
    duplicateIdentity,
  );
  await dynamodb.publicationLedger.recordReplayPublished(
    duplicateIdentity,
  );
  await dynamodb.publicationLedger.recordReplayPublished(
    duplicateIdentity,
  );

  await expect(
    dynamodb.publicationLedger.get(duplicateIdentity.archiveId),
  ).resolves.toEqual({
    publicationDecision: duplicateIdentity,
    replayPublication: duplicateIdentity,
    compensationDecision: null,
  });
});

it("rejects a conflicting publication identity", async () => {
  const conflictIdentity = {
    ...identity,
    archiveId: "publication-conflict-archive",
  };
  await dynamodb.publicationLedger.recordPublicationDecision(
    conflictIdentity,
  );

  await expect(
    dynamodb.publicationLedger.recordPublicationDecision({
      ...conflictIdentity,
      packageDigest: "sha256:other",
    }),
  ).rejects.toThrow("conflicting publication decision");
});

it("serializes publication and compensation as mutually exclusive decisions", async () => {
  const competingIdentity = {
    ...identity,
    archiveId: "publication-competing-archive",
  };
  const results = await Promise.allSettled([
    dynamodb.publicationLedger.recordPublicationDecision(competingIdentity),
    dynamodb.publicationLedger.recordCompensationDecision({
      archiveId: competingIdentity.archiveId,
      decisionVersion: competingIdentity.decisionVersion,
      reasonCode: "capture_failed",
    }),
  ]);

  expect(results.filter((result) => result.status === "fulfilled")).toHaveLength(
    1,
  );
  expect(results.filter((result) => result.status === "rejected")).toHaveLength(
    1,
  );
});

it("prevents publication after compensation", async () => {
  const compensatedIdentity = {
    ...identity,
    archiveId: "publication-compensated-archive",
  };
  await dynamodb.publicationLedger.recordCompensationDecision({
    archiveId: compensatedIdentity.archiveId,
    decisionVersion: compensatedIdentity.decisionVersion,
    reasonCode: "capture_failed",
  });

  await expect(
    dynamodb.publicationLedger.recordPublicationDecision(compensatedIdentity),
  ).rejects.toThrow("a compensated archive cannot be published");
});
