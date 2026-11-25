import { randomUUID } from "node:crypto";
import { expect, it } from "vitest";

import { ARCHIVE_COMPENSATION_DECIDED_EVENT } from "../../src/domain.js";

import { createCapturedPageFixture } from "../support/fixtures.js";
import {
  application,
  compensationDecisions,
  dynamodb,
  s3,
  searchIndex,
  setupIntegrationEnvironment,
} from "../support/integrationEnvironment.js";

setupIntegrationEnvironment(["dynamodb", "opensearch", "s3"]);

it("removes indexed documents and confirms a compensation decision", async () => {
  const token = randomUUID().replaceAll("-", "");

  const archiveId = `compensated-${token}`;
  const snapshotId = `compensated-${token}`;

  const fixture = createCapturedPageFixture(snapshotId, {
    archiveId,
    bucket: s3.bucketName,
    body: `<html><head><title>${token}</title></head><body><h1>${token}</h1></body></html>`,
  });

  await s3.putObject(fixture.bytes, fixture.artifact.key);

  await application.processPageCaptured(fixture.event);

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

  const indexed = await searchIndex.search({ text: token }, 10);
  const compensationDecision = await dynamodb.getPublicationEntry(archiveId);

  expect({
    indexedCandidates: indexed.candidates.length,
    compensationDecision,
    published: compensationDecisions.find(
      (decision) => decision.archiveId === archiveId,
    ),
  }).toMatchObject({
    indexedCandidates: 0,
    compensationDecision: {
      compensationDecision: JSON.stringify({
        archiveId,
        decisionVersion: 1,
        reasonCode: "seed-capture-failed",
      }),
    },
    published: {
      archiveId,
      decisionVersion: 1,
      reasonCode: "seed-capture-failed",
    },
  });
});
