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
  snapshotId: string;
  token: string;
  attempt: number;
};

export type ClaimResult =
  | { kind: "claimed"; claim: Claim }
  | { kind: "done"; status: LedgerStatus }
  | { kind: "busy" }
  | { kind: "conflict"; reason: string };

export type Outcome = { status: "INDEXED" } | { status: "FAILED" | "UNSUPPORTED" | "DISCARDED"; reason: string };

/** Durable, snapshot-keyed indexing ledger owned by Search. */
export interface Ledger {
  claim(event: PageCaptured, now: Date): Promise<ClaimResult>;
  release(claim: Claim, reason: string, now: Date): Promise<void>;
  complete(claim: Claim, outcome: Outcome, now: Date): Promise<void>;
}

export interface ArtifactStore {
  /** Reads an artifact fully, verifying its declared size and SHA-256 digest. */
  read(ref: ArtifactRef): Promise<Uint8Array>;
}

export interface DocumentIndex {
  /** Idempotent upsert keyed by `snapshotId`. */
  put(document: SnapshotDocument): Promise<void>;
  /** Marks one snapshot searchable; a missing document is not an error. */
  reveal(snapshotId: string): Promise<void>;
  /** Removes one snapshot; a missing document is not an error. */
  remove(snapshotId: string): Promise<void>;
}

/**
 * Publication facts Search records per archive (ADR-0019, ADR-0027). They
 * arrive independently and in any order; results are visible only when the
 * Coordinator's decision and Capture's replay acknowledgment match.
 */
export type PublicationFact = { decisionVersion: number; packageDigest: string };

export type ArchiveState = {
  archiveId: string;
  decision?: PublicationFact;
  published?: PublicationFact;
  compensationVersion?: number;
};

export type VisibilityResult = { kind: "recorded"; state: ArchiveState } | { kind: "conflict"; reason: string };

export interface ArchiveVisibility {
  get(archiveId: string): Promise<ArchiveState>;
  recordDecision(archiveId: string, fact: PublicationFact): Promise<VisibilityResult>;
  recordPublished(archiveId: string, fact: PublicationFact): Promise<VisibilityResult>;
  recordCompensation(archiveId: string, decisionVersion: number): Promise<VisibilityResult>;
}

/** Both publication facts are present, agree, and the run was not compensated. */
export function isVisible(state: ArchiveState): boolean {
  const { decision, published } = state;

  return (
    state.compensationVersion === undefined &&
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
