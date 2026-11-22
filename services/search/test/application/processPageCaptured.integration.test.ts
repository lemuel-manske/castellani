import { createHash } from "node:crypto";
import { Readable } from "node:stream";
import { gzipSync } from "node:zlib";
import { afterAll, beforeAll, expect, it } from "vitest";
import { createWarcCapturedPageReader } from "../../src/adapters/artifacts/warc.js";
import { createOpenSearchDocumentWriter } from "../../src/adapters/search/opensearch.js";
import { processPageCaptured } from "../../src/application/processPageCaptured.js";
import type { PageCapturedEvent } from "../../src/application/processPageCaptured.js";
import type { ArtifactObjectReader } from "../../src/ports/artifacts.js";
import {
  SEARCH_DYNAMODB_ENDPOINT_URL,
  createDynamoDbTestSupport,
} from "../support/dynamoDb.js";
import {
  SEARCH_OPENSEARCH_URL,
  createOpenSearchTestSupport,
} from "../support/openSearch.js";

let now = 1_000_000;
const dynamodb = createDynamoDbTestSupport(() => now);
const opensearch = createOpenSearchTestSupport();

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
      warcArtifacts: [{
        bucket: "capture-artifacts",
        key: `integration-archive/${snapshotId}.warc`,
        sha256: validChecksum ? checksum : "0".repeat(64),
        sizeBytes: bytes.byteLength,
      }],
    },
  };
  const artifactReader: ArtifactObjectReader = {
    getObject: () => Promise.resolve(Readable.from([bytes])),
  };

  return {
    event,
    capturedPageReader: createWarcCapturedPageReader(artifactReader),
  };
}

beforeAll(async () => {
  if (!SEARCH_DYNAMODB_ENDPOINT_URL?.trim()) {
    throw new Error("SEARCH_DYNAMODB_ENDPOINT_URL is required for Search integration tests");
  }
  if (!SEARCH_OPENSEARCH_URL?.trim()) {
    throw new Error("SEARCH_OPENSEARCH_URL is required for Search integration tests");
  }
  await dynamodb.setup();
  await opensearch.setup();
});

afterAll(async () => {
  if (SEARCH_OPENSEARCH_URL?.trim()) {
    await opensearch.teardown();
  }
  if (SEARCH_DYNAMODB_ENDPOINT_URL?.trim()) {
    await dynamodb.teardown();
  }
});

it("processes a captured page through DynamoDB, WARC extraction, and OpenSearch", async () => {
  const fixture = capturedFixture("integrated-snapshot");
  const result = await processPageCaptured(fixture.event, {
    ledger: dynamodb.ledger,
    capturedPageReader: fixture.capturedPageReader,
    documentWriter: createOpenSearchDocumentWriter(
      opensearch.client,
      opensearch.indexName,
    ),
  });

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
    processPageCaptured(fixture.event, {
      ledger: dynamodb.ledger,
      capturedPageReader: fixture.capturedPageReader,
      documentWriter: createOpenSearchDocumentWriter(
        opensearch.client,
        opensearch.indexName,
      ),
    }),
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

  await expect(
    processPageCaptured(fixture.event, {
      ledger: dynamodb.ledger,
      capturedPageReader: fixture.capturedPageReader,
      documentWriter: createOpenSearchDocumentWriter(
        opensearch.client,
        opensearch.indexName,
      ),
    }),
  ).resolves.toEqual({ status: "BUSY" });
});

it("records terminal failure when the captured artifact fails integrity validation", async () => {
  const fixture = capturedFixture("invalid-artifact-snapshot", false);

  await expect(
    processPageCaptured(fixture.event, {
      ledger: dynamodb.ledger,
      capturedPageReader: fixture.capturedPageReader,
      documentWriter: createOpenSearchDocumentWriter(
        opensearch.client,
        opensearch.indexName,
      ),
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
