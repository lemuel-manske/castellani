import { describe, expect, it } from "vitest";
import { canExposeSnapshot, reconcileManifest } from "../../src/domain/indexing.js";
import {
  emptyPublicationFacts,
  recordPublicationDecision,
  recordReplayPublished,
} from "../../src/domain/publication.js";

const manifest = [{ snapshotId: "snapshot-1" }, { snapshotId: "snapshot-2" }];

describe("manifest reconciliation", () => {
  it("identifies work missing from the ledger when completion arrives first", () => {
    const result = reconcileManifest(manifest, [
      { snapshotId: "snapshot-1", outcome: "INDEXED" },
    ]);

    expect(result).toEqual({
      expectedCount: 2,
      terminalCount: 1,
      missingSnapshotIds: ["snapshot-2"],
      unexpectedSnapshotIds: [],
      complete: false,
    });
  });

  it("counts each expected snapshot once and treats terminal failures as accounted", () => {
    const result = reconcileManifest(manifest, [
      { snapshotId: "snapshot-1", outcome: "INDEXED" },
      { snapshotId: "snapshot-2", outcome: "FAILED" },
    ]);

    expect(result.complete).toBe(true);
    expect(result.terminalCount).toBe(2);
  });

  it("does not consider pending entries terminal", () => {
    const result = reconcileManifest(manifest, [
      { snapshotId: "snapshot-1", outcome: "PENDING" },
      { snapshotId: "snapshot-2", outcome: "UNSUPPORTED" },
    ]);

    expect(result.complete).toBe(false);
    expect(result.terminalCount).toBe(1);
  });

  it("reports ledger entries not present in the immutable manifest", () => {
    const result = reconcileManifest(manifest, [
      { snapshotId: "snapshot-3", outcome: "INDEXED" },
    ]);
    expect(result.unexpectedSnapshotIds).toEqual(["snapshot-3"]);
  });

  it("rejects duplicate manifest identities", () => {
    expect(() =>
      reconcileManifest([{ snapshotId: "same" }, { snapshotId: "same" }], []),
    ).toThrow("duplicate snapshotId");
  });

  it("rejects conflicting ledger outcomes for one snapshot", () => {
    expect(() =>
      reconcileManifest(
        [{ snapshotId: "snapshot-1" }],
        [
          { snapshotId: "snapshot-1", outcome: "INDEXED" },
          { snapshotId: "snapshot-1", outcome: "FAILED" },
        ],
      ),
    ).toThrow("conflicting outcomes");
  });
});

describe("search visibility", () => {
  const published = recordReplayPublished(
    recordPublicationDecision(emptyPublicationFacts(), {
      archiveId: "archive-1",
      decisionVersion: 1,
      packageDigest: "digest",
    }),
    {
      archiveId: "archive-1",
      decisionVersion: 1,
      packageDigest: "digest",
    },
  );

  it("exposes only indexed snapshots in the manifest after publication", () => {
    expect(canExposeSnapshot("snapshot-1", manifest, "INDEXED", published)).toBe(true);
    expect(canExposeSnapshot("snapshot-1", manifest, "PENDING", published)).toBe(false);
    expect(canExposeSnapshot("snapshot-3", manifest, "INDEXED", published)).toBe(false);
  });

  it("keeps indexed documents hidden before both publication facts arrive", () => {
    const decisionOnly = recordPublicationDecision(emptyPublicationFacts(), {
      archiveId: "archive-1",
      decisionVersion: 1,
      packageDigest: "digest",
    });
    expect(canExposeSnapshot("snapshot-1", manifest, "INDEXED", decisionOnly)).toBe(false);
  });
});
