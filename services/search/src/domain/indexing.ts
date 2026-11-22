import type {
  IndexingOutcome,
  ManifestReconciliation,
  ManifestSnapshot,
  PublicationFacts,
  SnapshotLedgerEntry,
} from "../domain.js";
import { isPublicationAuthorized } from "./publication.js";

/** Reconciles the immutable Capture manifest against Search's snapshot ledger. */
function reconcileManifest(
  manifestSnapshots: readonly ManifestSnapshot[],
  ledgerEntries: readonly SnapshotLedgerEntry[],
): ManifestReconciliation {
  const expected = new Set<string>();

  for (const snapshot of manifestSnapshots) {
    if (!snapshot.snapshotId) {
      throw new Error("manifest contains an empty snapshotId");
    }
    if (expected.has(snapshot.snapshotId)) {
      throw new Error(
        "manifest contains duplicate snapshotId: " + snapshot.snapshotId,
      );
    }
    expected.add(snapshot.snapshotId);
  }

  const ledger = new Map<string, IndexingOutcome>();
  for (const entry of ledgerEntries) {
    if (!entry.snapshotId) {
      throw new Error("ledger contains an empty snapshotId");
    }
    const previous = ledger.get(entry.snapshotId);
    if (previous !== undefined && previous !== entry.outcome) {
      throw new Error(
        "ledger contains conflicting outcomes for snapshotId: " +
          entry.snapshotId,
      );
    }
    ledger.set(entry.snapshotId, entry.outcome);
  }

  const missingSnapshotIds: string[] = [];
  let terminalCount = 0;

  for (const snapshotId of expected) {
    const outcome = ledger.get(snapshotId);
    if (outcome === undefined) {
      missingSnapshotIds.push(snapshotId);
    } else if (outcome !== "PENDING" && outcome !== "PROCESSING") {
      terminalCount += 1;
    }
  }

  const unexpectedSnapshotIds = [...ledger.keys()].filter(
    (snapshotId) => !expected.has(snapshotId),
  );

  return {
    expectedCount: expected.size,
    terminalCount,
    missingSnapshotIds,
    unexpectedSnapshotIds,
    complete:
      missingSnapshotIds.length === 0 && terminalCount === expected.size,
  };
}

/** A snapshot is visible only after indexing and publication are both complete. */
function canExposeSnapshot(
  snapshotId: string,
  manifestSnapshots: readonly ManifestSnapshot[],
  outcome: IndexingOutcome,
  publication: PublicationFacts,
): boolean {
  if (
    !snapshotId ||
    outcome !== "INDEXED" ||
    !isPublicationAuthorized(publication)
  ) {
    return false;
  }

  return manifestSnapshots.some(
    (snapshot) => snapshot.snapshotId === snapshotId,
  );
}

export { canExposeSnapshot, reconcileManifest };
