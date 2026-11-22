/**
 * Search domain vocabulary.
 *
 * Keep domain concepts and contracts here; behavior lives in the focused
 * modules under ./domain. This file is the stable surface for comparing
 * Search's language with Capture and Coordinator.
 */

interface PublicationIdentity {
  archiveId: string;
  decisionVersion: number;
  packageDigest: string;
}

interface CompensationDecision {
  archiveId: string;
  decisionVersion: number;
  reasonCode: string;
}

interface PublicationFacts {
  publicationDecision: PublicationIdentity | null;
  replayPublication: PublicationIdentity | null;
  compensationDecision: CompensationDecision | null;
}

type IndexingOutcome =
  "PENDING" | "PROCESSING" | "INDEXED" | "UNSUPPORTED" | "FAILED";

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

export type {
  CompensationDecision,
  IndexingOutcome,
  ManifestReconciliation,
  ManifestSnapshot,
  PublicationFacts,
  PublicationIdentity,
  SnapshotLedgerEntry,
};
