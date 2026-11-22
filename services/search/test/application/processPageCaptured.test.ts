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
    capturedAt: "2026-11-22T10:00:00.000Z",
    contentType: "text/html",
    warcArtifacts: [{
      bucket: "capture-artifacts",
      key: "archive-1/snapshot-1.warc",
      sha256: "a".repeat(64),
      sizeBytes: 128,
    }],
  },
};

it("claims, indexes, and records a captured snapshot outcome", async () => {
  const claim = { archiveId: "archive-1", snapshotId: "snapshot-1", token: "claim-1", attempts: 1 };
  const ledger: IndexingLedger = {
    claim: vi.fn().mockResolvedValue({ status: "CLAIMED", claim }),
    complete: vi.fn().mockResolvedValue(undefined),
    release: vi.fn().mockResolvedValue(undefined),
  };
  const capturedPageReader: CapturedPageReader = {
    read: vi.fn().mockResolvedValue({
      archiveId: "archive-1",
      snapshotId: "snapshot-1",
      url: "https://example.com/",
      capturedAt: "2026-11-22T10:00:00.000Z",
      contentType: "text/html",
      content: "<html><body>Indexed content</body></html>",
    }),
  };
  const documentWriter: SearchDocumentWriter = {
    index: vi.fn().mockResolvedValue(undefined),
  };

  await expect(
    processPageCaptured(event, { ledger, capturedPageReader, documentWriter }),
  ).resolves.toEqual({ status: "COMPLETED", outcome: "INDEXED" });

  expect(ledger.claim).toHaveBeenCalledWith("archive-1", "snapshot-1", "message-1", 120);
  expect(documentWriter.index).toHaveBeenCalledOnce();
  expect(ledger.complete).toHaveBeenCalledWith(claim, "INDEXED", undefined);
});

it("does not repeat work when the snapshot already has a terminal result", async () => {
  const ledger: IndexingLedger = {
    claim: vi.fn().mockResolvedValue({ status: "TERMINAL", outcome: "INDEXED" }),
    complete: vi.fn(),
    release: vi.fn(),
  };
  const capturedPageReader: CapturedPageReader = {
    read: vi.fn(),
  };
  const documentWriter: SearchDocumentWriter = {
    index: vi.fn(),
  };

  await expect(
    processPageCaptured(event, { ledger, capturedPageReader, documentWriter }),
  ).resolves.toEqual({ status: "DUPLICATE", outcome: "INDEXED" });

  expect(capturedPageReader.read).not.toHaveBeenCalled();
  expect(documentWriter.index).not.toHaveBeenCalled();
});

it("leaves a snapshot with a live claim untouched", async () => {
  const ledger: IndexingLedger = {
    claim: vi.fn().mockResolvedValue({ status: "BUSY", leaseUntil: 1795360920 }),
    complete: vi.fn(),
    release: vi.fn(),
  };
  const capturedPageReader: CapturedPageReader = {
    read: vi.fn(),
  };
  const documentWriter: SearchDocumentWriter = {
    index: vi.fn(),
  };

  await expect(
    processPageCaptured(event, { ledger, capturedPageReader, documentWriter }),
  ).resolves.toEqual({ status: "BUSY" });

  expect(capturedPageReader.read).not.toHaveBeenCalled();
  expect(documentWriter.index).not.toHaveBeenCalled();
});
