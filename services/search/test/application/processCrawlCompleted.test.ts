import { createHash } from "node:crypto";
import { Readable } from "node:stream";
import { expect, it, vi } from "vitest";
import { processCrawlCompleted } from "../../src/application/processCrawlCompleted.js";
import type { ArtifactObjectReader } from "../../src/ports/artifacts.js";
import type { ManifestLedger } from "../../src/ports/manifest-ledger.js";

it("verifies and records immutable manifest snapshot membership", async () => {
  const data = Buffer.from(JSON.stringify({
    schemaVersion: 1,
    archiveId: "manifest-archive",
    collectionId: "collection-a",
    normalizerVersion: "v1",
    seedUrl: "https://example.com",
    createdAt: "2026-11-22T10:00:00.000Z",
    snapshots: [{ snapshotId: "snapshot-a" }, { snapshotId: "snapshot-b" }],
    failedPages: [],
  }));
  const digest = createHash("sha256").update(data).digest("hex");
  const artifactReader: ArtifactObjectReader = {
    getObject: vi.fn().mockResolvedValue(Readable.from([data])),
  };
  const manifestLedger: ManifestLedger = { record: vi.fn(), contains: vi.fn() };

  await processCrawlCompleted({
    archiveId: "manifest-archive",
    manifestDigest: digest,
    manifest: { bucket: "archive-manifests", key: "manifest.json", sha256: digest, sizeBytes: data.byteLength },
  }, artifactReader, manifestLedger);

  expect(manifestLedger.record).toHaveBeenCalledWith({
    archiveId: "manifest-archive",
    manifestDigest: digest,
    collectionId: "collection-a",
    snapshotIds: ["snapshot-a", "snapshot-b"],
  });
});

it("rejects manifest bytes that do not match the immutable digest", async () => {
  const data = Buffer.from("{}");
  const artifactReader: ArtifactObjectReader = {
    getObject: vi.fn().mockResolvedValue(Readable.from([data])),
  };
  const manifestLedger: ManifestLedger = { record: vi.fn(), contains: vi.fn() };

  await expect(processCrawlCompleted({
    archiveId: "manifest-archive",
    manifestDigest: "0".repeat(64),
    manifest: { bucket: "archive-manifests", key: "manifest.json", sha256: "0".repeat(64), sizeBytes: data.byteLength },
  }, artifactReader, manifestLedger)).rejects.toThrow("archive manifest digest");
  expect(manifestLedger.record).not.toHaveBeenCalled();
});
