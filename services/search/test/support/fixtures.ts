import { createHash } from "node:crypto";
import { Readable } from "node:stream";
import { gzipSync } from "node:zlib";
import type { PageCapturedEvent } from "../../src/application/processPageCaptured.js";
import type { SearchDocument } from "../../src/domain/content.js";
import type {
  ArtifactObjectReader,
  ArtifactReference,
  CapturedPageReference,
} from "../../src/ports/artifacts.js";

interface CapturedPageFixtureOptions {
  bucket?: string;
  contentType?: string;
  body?: string;
  validChecksum?: boolean;
}

function createCapturedPageFixture(
  snapshotId: string,
  options: CapturedPageFixtureOptions = {},
) {
  const contentType = options.contentType ?? "text/html; charset=utf-8";
  const body =
    options.body ??
    "<html><head><title>Integrated content</title></head><body><h1>Integrated content</h1></body></html>";
  const response = `HTTP/1.1 200 OK\r\nContent-Type: ${contentType}\r\n\r\n${body}`;
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
  ].join("\r\n");
  const bytes = gzipSync(Buffer.from(warc));
  const checksum = createHash("sha256").update(bytes).digest("hex");
  const page: CapturedPageReference = {
    archiveId: "integration-archive",
    snapshotId,
    url: "https://example.com/",
    finalUrl: "https://example.com/final",
    capturedAt: "2026-11-22T10:00:00.000Z",
  };
  const artifact: ArtifactReference = {
    bucket: options.bucket ?? "capture-artifacts",
    key: `integration-archive/${snapshotId}.warc.gz`,
    sha256: options.validChecksum === false ? "0".repeat(64) : checksum,
    sizeBytes: bytes.byteLength,
  };
  const event: PageCapturedEvent = {
    messageId: `message-${snapshotId}`,
    correlationId: page.archiveId,
    occurredAt: page.capturedAt,
    payload: {
      archiveId: page.archiveId,
      snapshotId,
      urlKey: snapshotId,
      url: page.url,
      finalUrl: page.finalUrl,
      redirectChain: [page.url, page.finalUrl],
      capturedAt: page.capturedAt,
      contentType,
      warcArtifacts: [artifact],
    },
  };
  const artifactReader: ArtifactObjectReader = {
    getObject: () => Promise.resolve(Readable.from([bytes])),
  };

  return { artifact, artifactReader, bytes, event, page };
}

function createSearchDocumentFixture(
  snapshotId = "integration-snapshot",
): SearchDocument {
  return {
    archiveId: "integration-archive",
    snapshotId,
    url: "https://example.com/",
    finalUrl: "https://example.com/final",
    capturedAt: "2026-11-22T10:00:00.000Z",
    contentType: "text/html",
    title: "Integration document",
    description: "Indexed against a real OpenSearch node",
    language: "en",
    text: "Search integration test content",
  };
}

export { createCapturedPageFixture, createSearchDocumentFixture };
