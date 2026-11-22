import { expect, it } from "vitest";
import { createS3ArtifactReader } from "../../src/adapters/artifacts/s3.js";
import { createWarcCapturedPageReader } from "../../src/adapters/artifacts/warc.js";
import { createOpenSearchDocumentWriter } from "../../src/adapters/search/opensearch.js";
import { processPageCaptured } from "../../src/application/processPageCaptured.js";
import {
  dynamodb,
  opensearch,
  s3,
  setupIntegrationEnvironment,
} from "../support/integrationEnvironment.js";
import { createCapturedPageFixture } from "../support/fixtures.js";

setupIntegrationEnvironment(["dynamodb", "s3", "opensearch"]);

function dependencies() {
  return {
    ledger: dynamodb.ledger,
    capturedPageReader: createWarcCapturedPageReader(
      createS3ArtifactReader(s3.client),
    ),
    documentWriter: createOpenSearchDocumentWriter(
      opensearch.client,
      opensearch.indexName,
    ),
  };
}

it("indexes a captured page across the real infrastructure adapters", async () => {
  const fixture = createCapturedPageFixture("integrated-snapshot", {
    bucket: s3.bucketName,
  });

  await s3.putObject(fixture.bytes, fixture.artifact.key);

  await expect(
    processPageCaptured(fixture.event, dependencies()),
  ).resolves.toEqual({ status: "COMPLETED", outcome: "INDEXED" });

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

  await expect(
    processPageCaptured(fixture.event, dependencies()),
  ).resolves.toEqual({ status: "DUPLICATE", outcome: "INDEXED" });
});

it("does not process a snapshot while another worker holds its lease", async () => {
  const fixture = createCapturedPageFixture("busy-snapshot", {
    bucket: s3.bucketName,
  });

  await dynamodb.ledger.claim(
    fixture.page.archiveId,
    fixture.page.snapshotId,
    "busy-message",
    120,
  );
  await s3.putObject(fixture.bytes, fixture.artifact.key);

  await expect(
    processPageCaptured(fixture.event, dependencies()),
  ).resolves.toEqual({ status: "BUSY" });
});

it("records terminal failure when the captured artifact fails integrity validation", async () => {
  const fixture = createCapturedPageFixture("invalid-artifact-snapshot", {
    bucket: s3.bucketName,
    validChecksum: false,
  });

  await s3.putObject(fixture.bytes, fixture.artifact.key);

  await expect(
    processPageCaptured(fixture.event, {
      ...dependencies(),
      maxAttempts: 1,
    }),
  ).resolves.toEqual({ status: "COMPLETED", outcome: "FAILED" });

  await expect(
    dynamodb.ledger.claim(
      fixture.page.archiveId,
      fixture.page.snapshotId,
      "retry-message",
      120,
    ),
  ).resolves.toEqual({ status: "TERMINAL", outcome: "FAILED" });
});

it("records unsupported content without indexing a document", async () => {
  const fixture = createCapturedPageFixture("unsupported-snapshot", {
    bucket: s3.bucketName,
    contentType: "application/pdf",
    body: "%PDF-1.7 not searchable text",
  });

  await s3.putObject(fixture.bytes, fixture.artifact.key);

  await expect(
    processPageCaptured(fixture.event, dependencies()),
  ).resolves.toEqual({ status: "COMPLETED", outcome: "UNSUPPORTED" });

  await opensearch.client.indices.refresh({ index: opensearch.indexName });

  const indexed = await opensearch.client.exists({
    index: opensearch.indexName,
    id: fixture.page.snapshotId,
  });

  expect(indexed.body).toBe(false);
});
