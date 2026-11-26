import { expect, it } from "vitest";
import {
  canExposeSnapshot,
  emptyPublicationFacts,
  INDEXING_OUTCOME,
  reconcileManifest,
  recordPublicationDecision,
  recordReplayPublished,
} from "../../src/domain/index.js";

const manifest = [{ snapshotId: "snapshot-1" }, { snapshotId: "snapshot-2" }];

it("identifies work missing from the ledger when completion arrives first", () => {
  const result = reconcileManifest(manifest, [
    { snapshotId: "snapshot-1", outcome: INDEXING_OUTCOME.INDEXED },
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
    { snapshotId: "snapshot-1", outcome: INDEXING_OUTCOME.INDEXED },
    { snapshotId: "snapshot-2", outcome: INDEXING_OUTCOME.FAILED },
  ]);

  expect(result.complete).toBe(true);
  expect(result.terminalCount).toBe(2);
});

it("does not consider pending entries terminal", () => {
  const result = reconcileManifest(manifest, [
    { snapshotId: "snapshot-1", outcome: INDEXING_OUTCOME.PENDING },
    { snapshotId: "snapshot-2", outcome: INDEXING_OUTCOME.UNSUPPORTED },
  ]);

  expect(result.complete).toBe(false);
  expect(result.terminalCount).toBe(1);
});

it("reports ledger entries not present in the immutable manifest", () => {
  const result = reconcileManifest(manifest, [
    { snapshotId: "snapshot-3", outcome: INDEXING_OUTCOME.INDEXED },
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
        { snapshotId: "snapshot-1", outcome: INDEXING_OUTCOME.INDEXED },
        { snapshotId: "snapshot-1", outcome: INDEXING_OUTCOME.FAILED },
      ],
    ),
  ).toThrow("conflicting outcomes");
});

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
  expect(
    canExposeSnapshot(
      "snapshot-1",
      manifest,
      INDEXING_OUTCOME.INDEXED,
      published,
    ),
  ).toBe(true);
  expect(
    canExposeSnapshot(
      "snapshot-1",
      manifest,
      INDEXING_OUTCOME.PENDING,
      published,
    ),
  ).toBe(false);
  expect(
    canExposeSnapshot(
      "snapshot-3",
      manifest,
      INDEXING_OUTCOME.INDEXED,
      published,
    ),
  ).toBe(false);
});

it("keeps indexed documents hidden before both publication facts arrive", () => {
  const decisionOnly = recordPublicationDecision(emptyPublicationFacts(), {
    archiveId: "archive-1",
    decisionVersion: 1,
    packageDigest: "digest",
  });

  expect(
    canExposeSnapshot(
      "snapshot-1",
      manifest,
      INDEXING_OUTCOME.INDEXED,
      decisionOnly,
    ),
  ).toBe(false);
});

it("does not count an active processing claim as terminal", () => {
  const result = reconcileManifest(manifest, [
    { snapshotId: "snapshot-1", outcome: INDEXING_OUTCOME.PROCESSING },
    { snapshotId: "snapshot-2", outcome: INDEXING_OUTCOME.INDEXED },
  ]);

  expect(result.complete).toBe(false);
  expect(result.terminalCount).toBe(1);
});
