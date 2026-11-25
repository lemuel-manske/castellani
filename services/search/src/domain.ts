import type { ArtifactReference } from "./ports/artifacts.js";

/**
 * Search domain vocabulary.
 *
 * Keep domain concepts and contracts here.
 */

const ARCHIVE_COMPENSATION_DECIDED_EVENT = "ArchiveCompensationDecided";
const ARCHIVE_PUBLICATION_DECIDED_EVENT = "ArchivePublicationDecided";
const ARCHIVE_PUBLISHED_EVENT = "ArchivePublished";
const CRAWL_COMPLETED_EVENT = "CrawlCompleted";
const PAGE_CAPTURED_EVENT = "PageCaptured";
const SEARCH_COMPENSATED_EVENT = "SearchCompensated";

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

interface SearchCompensationAck {
  archiveId: string;
  decisionVersion: number;
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

export {
  ARCHIVE_COMPENSATION_DECIDED_EVENT,
  ARCHIVE_PUBLICATION_DECIDED_EVENT,
  ARCHIVE_PUBLISHED_EVENT,
  CRAWL_COMPLETED_EVENT,
  PAGE_CAPTURED_EVENT,
  SEARCH_COMPENSATED_EVENT,
};

export type {
  CompensationDecision,
  CompletionCrawl,
  IndexingOutcome,
  ManifestReconciliation,
  ManifestSnapshot,
  NonTerminalIndexingOutcome,
  PublicationFacts,
  PublicationIdentity,
  SearchCompensationAck,
  SnapshotLedgerEntry,
  TerminalIndexingOutcome,
};
