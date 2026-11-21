import type { OutgoingEvent } from "../outbox/outbox.js";

/** Reference to an immutable artifact in S3, as defined by the manifest contract. */
export type ArtifactRef = {
  bucket: string;
  key: string;
  versionId?: string;
  sha256: string;
  sizeBytes: number;
};

/** Payload of a `PageCaptured` v1 event. */
export type PageCaptured = {
  messageId: string;
  archiveId: string;
  snapshotId: string;
  urlKey: string;
  url: string;
  finalUrl?: string;
  capturedAt: string;
  contentType?: string;
  warcArtifacts: ArtifactRef[];
};

/** Searchable projection of one historical snapshot. */
export type SnapshotDocument = {
  snapshotId: string;
  archiveId: string;
  urlKey: string;
  url: string;
  finalUrl?: string;
  capturedAt: string;
  contentType?: string;
  title?: string;
  content: string;
  indexedAt: string;
  /** True only once the archive's publication is authorized (see `ArchiveVisibility`). */
  visible: boolean;
};

export type ExtractedPage = {
  title?: string;
  content: string;
  contentType: string;
};

/**
 * Terminal and in-flight ledger states for one snapshot. `DISCARDED` means the
 * snapshot belongs to a compensated archive and must never be searchable.
 */
export type LedgerStatus = "PENDING" | "PROCESSING" | "INDEXED" | "FAILED" | "UNSUPPORTED" | "DISCARDED";

export const terminalStatuses: ReadonlySet<LedgerStatus> = new Set(["INDEXED", "FAILED", "UNSUPPORTED", "DISCARDED"]);

export type Claim = {
  archiveId: string;
  snapshotId: string;
  token: string;
  attempt: number;
};

export type ClaimResult = { kind: "claimed"; claim: Claim } | { kind: "done"; status: LedgerStatus } | { kind: "busy" };

export type Outcome = { status: "INDEXED" } | { status: "FAILED" | "UNSUPPORTED" | "DISCARDED"; reason: string };

/** Durable indexing ledger owned by Search, keyed by `archiveId` and `snapshotId`. */
export interface Ledger {
  claim(event: PageCaptured, now: Date): Promise<ClaimResult>;
  release(claim: Claim, reason: string, now: Date): Promise<void>;
  complete(claim: Claim, outcome: Outcome, now: Date): Promise<void>;
  /** Current status per snapshot of the archive; snapshots never claimed are absent. */
  statuses(archiveId: string, snapshotIds: string[]): Promise<Map<string, LedgerStatus>>;
}

/**
 * Stable OpenSearch document ID of a snapshot, derived from the ledger key:
 * the same snapshot ID in two archives can never overwrite the other's document.
 */
export function documentId(archiveId: string, snapshotId: string): string {
  return `${archiveId}/${snapshotId}`;
}

export interface ArtifactStore {
  /** Reads an artifact fully, verifying its declared size and SHA-256 digest. */
  read(ref: ArtifactRef): Promise<Uint8Array>;
}

export interface DocumentIndex {
  /**
   * Idempotent upsert keyed by `documentId`. A new document starts hidden; an
   * existing document keeps its visibility, so a late or stale re-index can
   * never hide a snapshot that was already revealed.
   */
  put(document: Omit<SnapshotDocument, "visible">): Promise<void>;
  /** Removes one snapshot; a missing document is not an error. */
  remove(archiveId: string, snapshotId: string): Promise<void>;
}

/**
 * Publication facts Search records per archive (ADR-0019, ADR-0027). They
 * arrive independently and in any order; results are visible only when the
 * Coordinator's decision and Capture's replay acknowledgment match.
 */
export type PublicationFact = { decisionVersion: number; packageDigest: string };

/** The immutable final manifest of a run, as referenced by `CrawlCompleted`. */
export type ManifestRecord = { digest: string; ref: ArtifactRef; expected: number };

export type IndexingCounts = { expected: number; indexed: number; failed: number; unsupported: number };

export type ArchiveState = {
  archiveId: string;
  decision?: PublicationFact;
  published?: PublicationFact;
  compensationVersion?: number;
  manifest?: ManifestRecord;
  /** `SearchIndexingCompleted` is in the outbox with these counts. */
  indexingReported?: IndexingCounts;
  /** `SearchReady` is in the outbox. */
  readyReported?: boolean;
  /** `SearchCompensated` is in the outbox: the cleanup finished. */
  compensationAcknowledged?: boolean;
  /** Increments on every reconciliation request; fences clearing the request. */
  reconcileRequests: number;
};

export type VisibilityResult = { kind: "recorded"; state: ArchiveState } | { kind: "conflict"; reason: string };

/**
 * Search's per-archive publication record (`search_publications`). Every
 * emitted event is written to the outbox in the same transaction as the state
 * change it reports, so a crash can neither lose nor invent an emission.
 */
export interface ArchiveVisibility {
  get(archiveId: string): Promise<ArchiveState>;
  recordDecision(archiveId: string, fact: PublicationFact): Promise<VisibilityResult>;
  recordPublished(archiveId: string, fact: PublicationFact): Promise<VisibilityResult>;
  recordCompensation(archiveId: string, decisionVersion: number): Promise<VisibilityResult>;
  /** Records the run's manifest once; a different digest is a conflict. */
  recordManifest(archiveId: string, manifest: ManifestRecord): Promise<VisibilityResult>;

  /** Durably marks the archive for reconciliation. */
  requestReconcile(archiveId: string): Promise<void>;
  /** Archives with an outstanding reconciliation request. */
  pendingReconciliations(limit: number): Promise<string[]>;
  /**
   * Clears the request only if no new request arrived since `requests` was
   * read, so a concurrent request is never lost. Returns whether it cleared.
   */
  clearReconcile(archiveId: string, requests: number): Promise<boolean>;

  /** Records indexing completion and enqueues `SearchIndexingCompleted`, once. */
  reportIndexing(archiveId: string, counts: IndexingCounts, event: OutgoingEvent): Promise<void>;
  /** Records readiness and enqueues `SearchReady`, once. */
  reportReady(archiveId: string, event: OutgoingEvent): Promise<void>;
  /** Records that the compensation cleanup finished and enqueues `SearchCompensated`, once. */
  acknowledgeCompensation(archiveId: string, event: OutgoingEvent): Promise<void>;
}

/**
 * Both publication facts are present and agree, the manifest that bounds the
 * authorized snapshots is known, and the run was not compensated.
 */
export function isVisible(state: ArchiveState): boolean {
  const { decision, published } = state;

  return (
    state.compensationVersion === undefined &&
    state.manifest !== undefined &&
    decision !== undefined &&
    published !== undefined &&
    decision.decisionVersion === published.decisionVersion &&
    decision.packageDigest === published.packageDigest
  );
}

export function isCompensated(state: ArchiveState): boolean {
  return state.compensationVersion !== undefined;
}

/**
 * The artifact or its content is unusable for indexing. Retrying the same
 * bytes cannot succeed, so this counts against the document attempt policy.
 */
export class DocumentError extends Error {}

/** Content was read correctly but is not indexable under the content policy. */
export class UnsupportedContentError extends Error {}
