/**
 * Search domain vocabulary.
 *
 * Keep domain concepts and contracts here; behavior lives in the focused
 * modules under ./domain. This file is the stable surface for comparing
 * Search's language with Capture and Coordinator.
 */

export interface PublicationIdentity {
  archiveId: string;
  decisionVersion: number;
  packageDigest: string;
}

export interface PublicationFacts {
  decision: PublicationIdentity | null;
  replay: PublicationIdentity | null;
  compensated: boolean;
}

export type IndexingOutcome = "PENDING" | "INDEXED" | "UNSUPPORTED" | "FAILED";

export interface ManifestSnapshot {
  snapshotId: string;
}

export interface SnapshotLedgerEntry {
  snapshotId: string;
  outcome: IndexingOutcome;
}

export interface ManifestReconciliation {
  expectedCount: number;
  terminalCount: number;
  missingSnapshotIds: string[];
  unexpectedSnapshotIds: string[];
  complete: boolean;
}
