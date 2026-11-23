import { randomUUID } from "node:crypto";
import { expect, it } from "vitest";

import { createCapturedPageFixture } from "../support/fixtures.js";
import {
  application,
  dynamodb,
  opensearch,
  s3,
  searchIndex,
  setupIntegrationEnvironment,
} from "../support/integrationEnvironment.js";

setupIntegrationEnvironment(["dynamodb", "opensearch", "s3"]);

it("does not repeat indexing work when a PageCaptured event is delivered again", async () => {
  const token = randomUUID().replaceAll("-", "");
  const snapshotId = `duplicate-${token}`;
  const content = `Duplicate delivery ${token}`;
  const fixture = createCapturedPageFixture(snapshotId, {
    bucket: s3.bucketName,
    body: `<html><head><title>${content}</title></head><body><h1>${content}</h1></body></html>`,
  });

  await s3.putObject(fixture.bytes, fixture.artifact.key);

  const first = await application.processPageCaptured(fixture.event);
  const duplicate = await application.processPageCaptured(fixture.event);

  expect(first).toEqual({ status: "COMPLETED", outcome: "INDEXED" });
  expect(duplicate).toEqual({ status: "COMPLETED", outcome: "INDEXED" });

  const entries = await dynamodb.ledger.listByArchive(
    fixture.event.payload.archiveId,
  );

  expect(entries.filter((entry) => entry.snapshotId === snapshotId)).toEqual([
    { snapshotId, outcome: "INDEXED" },
  ]);

  await opensearch.client.indices.refresh();

  const indexed = await searchIndex.search({ text: token }, 10);

  expect(indexed.candidates).toHaveLength(1);
  expect(indexed.candidates[0]?.document.snapshotId).toBe(snapshotId);
});

it("releases a failed indexing claim so the same event can be retried", async () => {
  const token = randomUUID().replaceAll("-", "");
  const snapshotId = `recovery-${token}`;
  const content = `Recovered artifact ${token}`;
  const fixture = createCapturedPageFixture(snapshotId, {
    bucket: s3.bucketName,
    body: `<html><head><title>${content}</title></head><body><h1>${content}</h1></body></html>`,
  });

  await expect(
    application.processPageCaptured(fixture.event),
  ).rejects.toThrow();

  const released = await dynamodb.ledger.listByArchive(
    fixture.event.payload.archiveId,
  );

  expect(
    released.find((entry) => entry.snapshotId === snapshotId)?.outcome,
  ).toBe("PENDING");

  await s3.putObject(fixture.bytes, fixture.artifact.key);

  const retried = await application.processPageCaptured(fixture.event);

  expect(retried).toEqual({ status: "COMPLETED", outcome: "INDEXED" });

  const recovered = await dynamodb.ledger.listByArchive(
    fixture.event.payload.archiveId,
  );

  expect(
    recovered.find((entry) => entry.snapshotId === snapshotId)?.outcome,
  ).toBe("INDEXED");

  await opensearch.client.indices.refresh();

  const indexed = await searchIndex.search({ text: token }, 10);

  expect(indexed.candidates).toHaveLength(1);
  expect(indexed.candidates[0]?.document.snapshotId).toBe(snapshotId);
});
