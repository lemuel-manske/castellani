import { expect, it, vi } from "vitest";
import { processPageCaptured } from "../../src/application/processPageCaptured.js";
import type { IndexingLedger } from "../../src/ports/indexing-ledger.js";
import type { CapturedPageReader } from "../../src/ports/artifacts.js";
import type { SearchDocumentWriter } from "../../src/ports/search-index.js";

const event = {
  messageId: "message-1",
  correlationId: "archive-1",
  occurredAt: "2026-11-22T10:00:00.000Z",
  payload: {
    archiveId: "archive-1",
    snapshotId: "snapshot-1",
    urlKey: "url-key",
    url: "https://example.com/",
    finalUrl: "https://example.com/final",
    redirectChain: ["https://example.com/", "https://example.com/final"],
    capturedAt: "2026-11-22T10:00:00.000Z",
    contentType: "text/html",
    warcArtifacts: [
      {
        bucket: "capture-artifacts",
        key: "capture-staging/archive-1/url-key/attempt-1/snapshot-1/page.warc.gz",
        sha256: "a".repeat(64),
        sizeBytes: 128,
        versionId: "version-1",
      },
    ],
  },
};

it("claims, indexes, and records a captured snapshot outcome", async () => {
  const claim = {
    archiveId: "archive-1",
    snapshotId: "snapshot-1",
    token: "claim-1",
    attempts: 1,
  };
  const claimMock = vi.fn().mockResolvedValue({ status: "CLAIMED", claim });
  const completeMock = vi.fn().mockResolvedValue(undefined);
  const releaseMock = vi.fn().mockResolvedValue(undefined);
  const readMock = vi.fn().mockResolvedValue({
    archiveId: "archive-1",
    snapshotId: "snapshot-1",
    url: "https://example.com/",
    capturedAt: "2026-11-22T10:00:00.000Z",
    contentType: "text/html",
    content: "<html><body>Indexed content</body></html>",
  });
  const indexMock = vi.fn().mockResolvedValue(undefined);
  const ledger: IndexingLedger = {
    claim: claimMock,
    complete: completeMock,
    release: releaseMock,
  };
  const capturedPageReader: CapturedPageReader = { read: readMock };
  const documentWriter: SearchDocumentWriter = { index: indexMock };

  await expect(
    processPageCaptured(event, { ledger, capturedPageReader, documentWriter }),
  ).resolves.toEqual({ status: "COMPLETED", outcome: "INDEXED" });

  expect(claimMock).toHaveBeenCalledWith(
    "archive-1",
    "snapshot-1",
    "message-1",
    120,
  );
  expect(readMock).toHaveBeenCalledWith(event.payload, event.payload.warcArtifacts);
  expect(indexMock).toHaveBeenCalledOnce();
  expect(completeMock).toHaveBeenCalledWith(claim, "INDEXED", undefined);
});

it("does not repeat work when the snapshot already has a terminal result", async () => {
  const claimMock = vi
    .fn()
    .mockResolvedValue({ status: "TERMINAL", outcome: "INDEXED" });
  const readMock = vi.fn();
  const indexMock = vi.fn();
  const ledger: IndexingLedger = {
    claim: claimMock,
    complete: vi.fn(),
    release: vi.fn(),
  };
  const capturedPageReader: CapturedPageReader = { read: readMock };
  const documentWriter: SearchDocumentWriter = { index: indexMock };

  await expect(
    processPageCaptured(event, { ledger, capturedPageReader, documentWriter }),
  ).resolves.toEqual({ status: "DUPLICATE", outcome: "INDEXED" });

  expect(readMock).not.toHaveBeenCalled();
  expect(indexMock).not.toHaveBeenCalled();
});

it("leaves a snapshot with a live claim untouched", async () => {
  const claimMock = vi
    .fn()
    .mockResolvedValue({ status: "BUSY", leaseUntil: 1795360920 });
  const readMock = vi.fn();
  const indexMock = vi.fn();
  const ledger: IndexingLedger = {
    claim: claimMock,
    complete: vi.fn(),
    release: vi.fn(),
  };
  const capturedPageReader: CapturedPageReader = { read: readMock };
  const documentWriter: SearchDocumentWriter = { index: indexMock };

  await expect(
    processPageCaptured(event, { ledger, capturedPageReader, documentWriter }),
  ).resolves.toEqual({ status: "BUSY" });

  expect(readMock).not.toHaveBeenCalled();
  expect(indexMock).not.toHaveBeenCalled();
});