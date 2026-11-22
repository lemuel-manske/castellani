import { createHash } from "node:crypto";
import { gzipSync } from "node:zlib";
import { afterAll, beforeAll, expect, it } from "vitest";
import { createS3ArtifactReader } from "../../src/adapters/artifacts/s3.js";
import { createWarcCapturedPageReader } from "../../src/adapters/artifacts/warc.js";
import { createOpenSearchDocumentWriter } from "../../src/adapters/search/opensearch.js";
import { processPageCaptured } from "../../src/application/processPageCaptured.js";
import type { PageCapturedEvent } from "../../src/application/processPageCaptured.js";
import {
  SEARCH_DYNAMODB_ENDPOINT_URL,
  createDynamoDbTestSupport,
} from "../support/dynamoDb.js";
import {
  SEARCH_OPENSEARCH_URL,
  createOpenSearchTestSupport,
} from "../support/openSearch.js";
import {
  SEARCH_S3_ENDPOINT_URL,
  createS3TestSupport,
} from "../support/s3.js";

const now = 1_000_000;
const dynamodb = createDynamoDbTestSupport(() => now);
const opensearch = createOpenSearchTestSupport();
const s3 = createS3TestSupport();

function capturedFixture(snapshotId: string, validChecksum = true) {
  const response =
    "HTTP/1.1 200 OK\\r\\nContent-Type: text/html; charset=utf-8\\r\\n\\r\\n<html><body><h1>Integrated content</h1></body></html>";
  const warc = [
    "WARC/1.1",
    "WARC-Type: response",
    "WARC-Target-URI: https://example.com/final",
    "WARC-Date: 2026-11-22T10:00:00Z",
    "Content-Type: application/http; msgtype=response",
    `Content-Length: ${Buffer.byteLength(response)}`,
    "",
    response,
    "",
    "",
  ].join("\\r\\n");
  const bytes = gzipSync(Buffer.from(warc));
  const checksum = createHash("sha256").update(bytes).digest("hex");
  const event: PageCapturedEvent = {
    messageId: `message-${snapshotId}`,
    correlationId: "integration-archive",
    occurredAt: "2026-11-22T10:00:00.000Z",
    payload: {
      archiveId: "integration-archive",
      snapshotId,
      urlKey: snapshotId,
      url: "https://example.com/",
      finalUrl: "https://example.com/final",
      redirectChain: ["https://example.com/", "https://example.com/final"],
      capturedAt: "2026-11-22T10:00:00.000Z",
      contentType: "text/html",
      warcArtifacts: [
        {
          bucket: s3.bucketName,
          key: s3.artifactKey,
          sha256: validChecksum ? checksum : "0".repeat(64),
          sizeBytes: bytes.byteLength,
        },
      ],
    },
  };

  return { event, bytes };
}

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

beforeAll(async () => {
  if (!SEARCH_DYNAMODB_ENDPOINT_URL?.trim()) {
    throw new Error(
      "SEARCH_DYNAMODB_ENDPOINT_URL is required for Search integration tests",
    );
  }
  if (!SEARCH_OPENSEARCH_URL?.trim()) {
    throw new Error(
      "SEARCH_OPENSEARCH_URL is required for Search integration tests",
    );
  }
  if (!SEARCH_S3_ENDPOINT_URL?.trim()) {
    throw new Error(
      "SEARCH_S3_ENDPOINT_URL is required for Search integration tests",
    );
  }

  await dynamodb.setup();
  await opensearch.setup();
  await s3.setup();
});

afterAll(async () => {
  if (SEARCH_S3_ENDPOINT_URL?.trim()) {
    await s3.teardown();
  }
  if (SEARCH_OPENSEARCH_URL?.trim()) {
    await opensearch.teardown();
  }
  if (SEARCH_DYNAMODB_ENDPOINT_URL?.trim()) {
    await dynamodb.teardown();
  }
});

it("processes a captured page through DynamoDB, S3, WARC extraction, and OpenSearch", async () => {
  const fixture = capturedFixture("integrated-snapshot");
  await s3.putObject(fixture.bytes);

  const result = await processPageCaptured(fixture.event, dependencies());

  expect(result).toEqual({ status: "COMPLETED", outcome: "INDEXED" });
  await opensearch.client.indices.refresh({ index: opensearch.indexName });

  const indexed = await opensearch.client.get({
    index: opensearch.indexName,
    id: "integrated-snapshot",
  });
  expect(indexed.body._source).toMatchObject({
    archiveId: "integration-archive",
    snapshotId: "integrated-snapshot",
    text: "Integrated content",
  });

  await expect(
    processPageCaptured(fixture.event, dependencies()),
  ).resolves.toEqual({ status: "DUPLICATE", outcome: "INDEXED" });
});

it("does not process a snapshot while another worker holds its DynamoDB lease", async () => {
  await dynamodb.ledger.claim(
    "integration-archive",
    "busy-snapshot",
    "busy-message",
    120,
  );
  const fixture = capturedFixture("busy-snapshot");
  await s3.putObject(fixture.bytes);

  await expect(
    processPageCaptured(fixture.event, dependencies()),
  ).resolves.toEqual({ status: "BUSY" });
});

it("records terminal failure when the captured artifact fails integrity validation", async () => {
  const fixture = capturedFixture("invalid-artifact-snapshot", false);
  await s3.putObject(fixture.bytes);

  await expect(
    processPageCaptured(fixture.event, {
      ...dependencies(),
      maxAttempts: 1,
    }),
  ).resolves.toEqual({ status: "COMPLETED", outcome: "FAILED" });

  await expect(
    dynamodb.ledger.claim(
      "integration-archive",
      "invalid-artifact-snapshot",
      "retry-message",
      120,
    ),
  ).resolves.toEqual({ status: "TERMINAL", outcome: "FAILED" });
});
