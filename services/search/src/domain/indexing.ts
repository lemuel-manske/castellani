import { isPublicationAuthorized } from "./publication.js";
import type { PublicationFacts } from "./publication.js";

const INDEXING_OUTCOME = {
  PENDING: "PENDING",
  PROCESSING: "PROCESSING",
  INDEXED: "INDEXED",
  UNSUPPORTED: "UNSUPPORTED",
  FAILED: "FAILED",
} as const;

const INDEXING_CLAIM_STATUS = {
  CLAIMED: "CLAIMED",
  BUSY: "BUSY",
  TERMINAL: "TERMINAL",
} as const;

const PAGE_CAPTURE_STATUS = {
  COMPLETED: "COMPLETED",
  BUSY: INDEXING_CLAIM_STATUS.BUSY,
} as const;

const INDEXING_REASON_CODE = {
  ATTEMPTS_EXHAUSTED: "INDEXING_ATTEMPTS_EXHAUSTED",
} as const;

type IndexingOutcome = (typeof INDEXING_OUTCOME)[keyof typeof INDEXING_OUTCOME];

type NonTerminalIndexingOutcome =
  typeof INDEXING_OUTCOME.PENDING | typeof INDEXING_OUTCOME.PROCESSING;

type TerminalIndexingOutcome =
  | typeof INDEXING_OUTCOME.INDEXED
  | typeof INDEXING_OUTCOME.UNSUPPORTED
  | typeof INDEXING_OUTCOME.FAILED;

interface ManifestSnapshot {
  snapshotId: string;
}

interface SnapshotLedgerEntry {
  snapshotId: string;
  outcome: IndexingOutcome;
}

interface ManifestReconciliation {
  expectedCount: number;
  terminalCount: number;
  missingSnapshotIds: string[];
  unexpectedSnapshotIds: string[];
  complete: boolean;
}

function isTerminalIndexingOutcome(
  outcome: IndexingOutcome,
): outcome is TerminalIndexingOutcome {
  return (
    outcome === INDEXING_OUTCOME.INDEXED ||
    outcome === INDEXING_OUTCOME.UNSUPPORTED ||
    outcome === INDEXING_OUTCOME.FAILED
  );
}

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
    } else if (isTerminalIndexingOutcome(outcome)) {
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
    outcome !== INDEXING_OUTCOME.INDEXED ||
    !isPublicationAuthorized(publication)
  ) {
    return false;
  }

  return manifestSnapshots.some(
    (snapshot) => snapshot.snapshotId === snapshotId,
  );
}

export {
  INDEXING_CLAIM_STATUS,
  INDEXING_OUTCOME,
  INDEXING_REASON_CODE,
  PAGE_CAPTURE_STATUS,
  canExposeSnapshot,
  reconcileManifest,
};

export type {
  IndexingOutcome,
  ManifestReconciliation,
  ManifestSnapshot,
  NonTerminalIndexingOutcome,
  SnapshotLedgerEntry,
  TerminalIndexingOutcome,
};
