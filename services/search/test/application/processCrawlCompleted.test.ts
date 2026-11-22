import { createHash } from "node:crypto";
import { Readable } from "node:stream";
import { expect, it, vi } from "vitest";
import { processCrawlCompleted } from "../../src/application/processCrawlCompleted.js";
import type { ProcessPageCapturedDependencies } from "../../src/application/processPageCaptured.js";
import type {
  ArtifactObjectReader,
  CapturedPageReference,
} from "../../src/ports/artifacts.js";
import type { ManifestLedger } from "../../src/ports/manifest-ledger.js";

it("verifies the immutable manifest, records membership, and recovers every snapshot", async () => {
  const artifact = {
    bucket: "capture-artifacts",
    key: "archives/manifest-archive/snapshot.warc.gz",
    sha256: "a".repeat(64),
    sizeBytes: 10,
  };
  const data = Buffer.from(
    JSON.stringify({
      schemaVersion: 1,
      archiveId: "manifest-archive",
      collectionId: "collection-a",
      normalizerVersion: "v1",
      seedUrl: "https://example.com",
      createdAt: "2026-11-22T10:00:00.000Z",
      snapshots: [
        {
          snapshotId: "snapshot-a",
          urlKey: "url-a",
          url: "https://example.com/a",
          finalUrl: "https://example.com/a",
          capturedAt: "2026-11-22T10:00:00.000Z",
          warcArtifacts: [artifact],
        },
        {
          snapshotId: "snapshot-b",
          urlKey: "url-b",
          url: "https://example.com/b",
          finalUrl: "https://example.com/b",
          redirectChain: ["https://example.com/old", "https://example.com/b"],
          capturedAt: "2026-11-22T10:01:00.000Z",
          contentType: "text/html",
          warcArtifacts: [artifact],
        },
      ],
      failedPages: [],
    }),
  );
  const digest = createHash("sha256").update(data).digest("hex");
  const artifactReader: ArtifactObjectReader = {
    getObject: vi.fn().mockResolvedValue(Readable.from([data])),
  };
  const record = vi.fn().mockResolvedValue(undefined);
  const manifestLedger: ManifestLedger = { record, contains: vi.fn() };
  const claim = vi
    .fn()
    .mockImplementation((archiveId: string, snapshotId: string) =>
      Promise.resolve({
        status: "CLAIMED" as const,
        claim: { archiveId, snapshotId, token: "claim-token", attempts: 1 },
      }),
    );
  const complete = vi.fn().mockResolvedValue(undefined);
  const release = vi.fn().mockResolvedValue(undefined);
  const ledger: ProcessPageCapturedDependencies["ledger"] = {
    claim,
    complete,
    release,
    listByArchive: vi.fn().mockResolvedValue([]),
  };
  const read = vi.fn().mockImplementation((page: CapturedPageReference) =>
    Promise.resolve({
      archiveId: page.archiveId,
      snapshotId: page.snapshotId,
      url: page.url,
      finalUrl: page.finalUrl ?? page.url,
      capturedAt: page.capturedAt,
      contentType: "text/html",
      content: "<html><body>Recovered content</body></html>",
    }),
  );
  const capturedPageReader: ProcessPageCapturedDependencies["capturedPageReader"] =
    { read };
  const index = vi.fn().mockResolvedValue(undefined);
  const documentWriter: ProcessPageCapturedDependencies["documentWriter"] = {
    index,
  };
  const indexing: ProcessPageCapturedDependencies = {
    ledger,
    capturedPageReader,
    documentWriter,
  };

  await processCrawlCompleted(
    {
      archiveId: "manifest-archive",
      manifestDigest: digest,
      manifest: {
        bucket: "archive-manifests",
        key: "manifest.json",
        sha256: digest,
        sizeBytes: data.byteLength,
      },
    },
    artifactReader,
    manifestLedger,
    indexing,
  );

  expect(record).toHaveBeenCalledWith({
    archiveId: "manifest-archive",
    manifestDigest: digest,
    collectionId: "collection-a",
    snapshotIds: ["snapshot-a", "snapshot-b"],
  });
  expect(claim).toHaveBeenCalledTimes(2);
  expect(complete).toHaveBeenCalledTimes(2);
  expect(index).toHaveBeenCalledTimes(2);
  expect(read).toHaveBeenNthCalledWith(
    1,
    expect.objectContaining({
      archiveId: "manifest-archive",
      snapshotId: "snapshot-a",
      url: "https://example.com/a",
      finalUrl: "https://example.com/a",
      capturedAt: "2026-11-22T10:00:00.000Z",
      urlKey: "url-a",
      redirectChain: ["https://example.com/a", "https://example.com/a"],
      warcArtifacts: [artifact],
    }),
    [artifact],
  );
  expect(claim).toHaveBeenNthCalledWith(
    1,
    "manifest-archive",
    "snapshot-a",
    `manifest:${digest}:snapshot-a`,
    120,
    5,
  );
});

it("rejects manifest bytes that do not match the immutable digest", async () => {
  const data = Buffer.from("{}");
  const artifactReader: ArtifactObjectReader = {
    getObject: vi.fn().mockResolvedValue(Readable.from([data])),
  };
  const record = vi.fn();
  const manifestLedger: ManifestLedger = { record, contains: vi.fn() };
  const indexing = {
    ledger: {
      claim: vi.fn(),
      complete: vi.fn(),
      release: vi.fn(),
      listByArchive: vi.fn(),
    },
    capturedPageReader: { read: vi.fn() },
    documentWriter: { index: vi.fn() },
  } as unknown as ProcessPageCapturedDependencies;

  await expect(
    processCrawlCompleted(
      {
        archiveId: "manifest-archive",
        manifestDigest: "0".repeat(64),
        manifest: {
          bucket: "archive-manifests",
          key: "manifest.json",
          sha256: "0".repeat(64),
          sizeBytes: data.byteLength,
        },
      },
      artifactReader,
      manifestLedger,
      indexing,
    ),
  ).rejects.toThrow("archive manifest digest");
  expect(record).not.toHaveBeenCalled();
});
