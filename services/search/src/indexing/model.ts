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
};

export type ExtractedPage = {
  title?: string;
  content: string;
  contentType: string;
};

/** Terminal and in-flight ledger states for one snapshot. */
export type LedgerStatus = "PENDING" | "PROCESSING" | "INDEXED" | "FAILED" | "UNSUPPORTED";

export const terminalStatuses: ReadonlySet<LedgerStatus> = new Set(["INDEXED", "FAILED", "UNSUPPORTED"]);

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

export type Outcome = { status: "INDEXED" } | { status: "FAILED" | "UNSUPPORTED"; reason: string };

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
}

/**
 * The artifact or its content is unusable for indexing. Retrying the same
 * bytes cannot succeed, so this counts against the document attempt policy.
 */
export class DocumentError extends Error {}

/** Content was read correctly but is not indexable under the content policy. */
export class UnsupportedContentError extends Error {}
