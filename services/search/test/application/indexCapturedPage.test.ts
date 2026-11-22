import { createHash } from "node:crypto";
import { Readable } from "node:stream";
import { gzipSync } from "node:zlib";
import { expect, it, vi } from "vitest";
import { indexCapturedPage } from "../../src/application/indexCapturedPage.js";
import type {
  ArtifactObjectReader,
  ArtifactReference,
  CapturedPageReference,
} from "../../src/adapters/artifacts.js";
import type { SearchDocumentWriter } from "../../src/application/indexCapturedPage.js";

const page: CapturedPageReference = {
  archiveId: "archive-1",
  snapshotId: "snapshot-1",
  url: "https://example.com/",
  finalUrl: "https://example.com/",
  capturedAt: "2026-11-22T10:00:00.000Z",
};

function artifactFor(
  contentType: string,
  content: string,
): {
  reference: ArtifactReference;
  reader: ArtifactObjectReader;
} {
  const response =
    "HTTP/1.1 200 OK\r\nContent-Type: " + contentType + "\r\n\r\n" + content;
  const warc = [
    "WARC/1.1",
    "WARC-Type: response",
    "WARC-Target-URI: https://example.com/",
    "WARC-Date: 2026-11-22T10:00:00Z",
    "Content-Type: application/http; msgtype=response",
    "Content-Length: " + String(Buffer.byteLength(response)),
    "",
    response,
    "",
    "",
  ].join("\r\n");
  const bytes = gzipSync(Buffer.from(warc));

  return {
    reference: {
      bucket: "capture-artifacts",
      key: "archive-1/snapshot-1.warc",
      sha256: createHash("sha256").update(bytes).digest("hex"),
      sizeBytes: bytes.byteLength,
    },
    reader: {
      getObject: () => Promise.resolve(Readable.from([bytes])),
    },
  };
}

it("extracts and indexes a captured page using its snapshot identity", async () => {
  const artifact = artifactFor(
    "text/html; charset=utf-8",
    "<html><body><h1>Indexed page</h1></body></html>",
  );
  const index = vi.fn().mockResolvedValue(undefined);
  const documentWriter: SearchDocumentWriter = { index };

  await expect(
    indexCapturedPage(
      page,
      [artifact.reference],
      artifact.reader,
      documentWriter,
    ),
  ).resolves.toEqual({ outcome: "INDEXED", snapshotId: "snapshot-1" });

  expect(index).toHaveBeenCalledWith(
    expect.objectContaining({
      archiveId: "archive-1",
      snapshotId: "snapshot-1",
      text: "Indexed page",
    }),
  );
});

it("accounts for unsupported captured content without writing a document", async () => {
  const artifact = artifactFor("application/pdf", "not searchable text");
  const documentWriter: SearchDocumentWriter = {
    index: vi.fn().mockResolvedValue(undefined),
  };

  await expect(
    indexCapturedPage(
      page,
      [artifact.reference],
      artifact.reader,
      documentWriter,
    ),
  ).resolves.toEqual({
    outcome: "UNSUPPORTED",
    snapshotId: "snapshot-1",
    reasonCode: "UNSUPPORTED_CONTENT_TYPE",
  });

  expect(index).not.toHaveBeenCalled();
});
