import { createHash } from "node:crypto";
import { Readable } from "node:stream";
import { gzipSync } from "node:zlib";
import { expect, it } from "vitest";
import {
  ArtifactIntegrityError,
  CapturedResponseNotFoundError,
  readCapturedPage,
} from "../../src/adapters/artifacts.js";
import type {
  ArtifactObjectReader,
  ArtifactReference,
  CapturedPageReference,
} from "../../src/adapters/artifacts.js";

const page: CapturedPageReference = {
  archiveId: "archive-1",
  snapshotId: "snapshot-1",
  url: "https://example.com/start",
  finalUrl: "https://example.com/final",
  capturedAt: "2026-11-22T10:00:00.000Z",
};

function responseRecord(targetUrl: string, html: string): string {
  const response =
    "HTTP/1.1 200 OK\r\nContent-Type: text/html; charset=utf-8\r\n\r\n" + html;

  return [
    "WARC/1.1",
    "WARC-Type: response",
    "WARC-Target-URI: " + targetUrl,
    "WARC-Date: 2026-11-22T10:00:00Z",
    "Content-Type: application/http; msgtype=response",
    "Content-Length: " + Buffer.byteLength(response),
    "",
    response,
    "",
    "",
  ].join("\r\n");
}

function artifactFor(warc: string): {
  reference: ArtifactReference;
  reader: ArtifactObjectReader;
} {
  const bytes = gzipSync(Buffer.from(warc));

  return {
    reference: {
      bucket: "capture-artifacts",
      key: "archive-1/snapshot-1.warc",
      sha256: createHash("sha256").update(bytes).digest("hex"),
      sizeBytes: bytes.byteLength,
    },
    reader: {
      getObject: async () => Readable.from([bytes]),
    },
  };
}

it("extracts the captured HTTP response from its WARC artifact", async () => {
  const artifact = artifactFor(
    responseRecord(
      page.finalUrl ?? page.url,
      "<html><body>Archived page</body></html>",
    ),
  );

  await expect(
    readCapturedPage(page, [artifact.reference], artifact.reader),
  ).resolves.toMatchObject({
    archiveId: "archive-1",
    snapshotId: "snapshot-1",
    url: "https://example.com/start",
    finalUrl: "https://example.com/final",
    contentType: "text/html; charset=utf-8",
    content: "<html><body>Archived page</body></html>",
  });
});

it("selects the final URL response when the WARC contains a redirect response", async () => {
  const artifact = artifactFor(
    responseRecord(page.url, "<html><body>Redirect response</body></html>") +
      responseRecord(
        page.finalUrl ?? page.url,
        "<html><body>Final response</body></html>",
      ),
  );

  await expect(
    readCapturedPage(page, [artifact.reference], artifact.reader),
  ).resolves.toMatchObject({
    content: "<html><body>Final response</body></html>",
  });
});

it("validates the complete artifact checksum before returning captured content", async () => {
  const artifact = artifactFor(
    responseRecord(
      page.finalUrl ?? page.url,
      "<html><body>Archived page</body></html>",
    ) +
      responseRecord(
        "https://example.org/trailing",
        "<html><body>Trailing record</body></html>",
      ),
  );

  await expect(
    readCapturedPage(
      page,
      [{ ...artifact.reference, sha256: "0".repeat(64) }],
      artifact.reader,
    ),
  ).rejects.toBeInstanceOf(ArtifactIntegrityError);
});

it("rejects artifacts whose declared size does not match the downloaded object", async () => {
  const artifact = artifactFor(
    responseRecord(
      page.finalUrl ?? page.url,
      "<html><body>Archived page</body></html>",
    ),
  );

  await expect(
    readCapturedPage(
      page,
      [{ ...artifact.reference, sizeBytes: artifact.reference.sizeBytes + 1 }],
      artifact.reader,
    ),
  ).rejects.toBeInstanceOf(ArtifactIntegrityError);
});

it("rejects an artifact without a response for the captured page URL", async () => {
  const artifact = artifactFor(
    responseRecord(
      "https://example.org/other",
      "<html><body>Other page</body></html>",
    ),
  );

  await expect(
    readCapturedPage(page, [artifact.reference], artifact.reader),
  ).rejects.toBeInstanceOf(CapturedResponseNotFoundError);
});
