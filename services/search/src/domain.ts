import type { ArtifactReference } from "./ports/artifacts.js";

/**
 * Search domain vocabulary.
 *
 * Keep domain concepts and contracts here.
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

interface CompletionCrawl {
  archiveId: string;
  manifestDigest: string;
  manifest: ArtifactReference;
  seedSucceeded: boolean;
  capturedCount: number;
  failedCount: number;
}

interface PublicationFacts {
  publicationDecision: PublicationIdentity | null;
  replayPublication: PublicationIdentity | null;
  compensationDecision: CompensationDecision | null;
}

type IndexingOutcome =
  "PENDING" | "PROCESSING" | "INDEXED" | "UNSUPPORTED" | "FAILED";

type NonTerminalIndexingOutcome = Extract<
  IndexingOutcome,
  "PENDING" | "PROCESSING"
>;

type TerminalIndexingOutcome = Extract<
  IndexingOutcome,
  "INDEXED" | "UNSUPPORTED" | "FAILED"
>;

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
  CompletionCrawl,
  IndexingOutcome,
  ManifestReconciliation,
  ManifestSnapshot,
  NonTerminalIndexingOutcome,
  PublicationFacts,
  PublicationIdentity,
  SnapshotLedgerEntry,
  TerminalIndexingOutcome,
};
