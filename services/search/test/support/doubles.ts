import { randomUUID } from "node:crypto";

import { verify } from "../../src/indexing/s3-artifacts.js";
import type {
  ArtifactRef,
  ArtifactStore,
  Claim,
  ClaimResult,
  DocumentIndex,
  Ledger,
  LedgerStatus,
  Outcome,
  PageCaptured,
  SnapshotDocument,
} from "../../src/indexing/model.js";

type Entry = { archiveId: string; status: LedgerStatus; attempts: number; token?: string; reason?: string };

/** In-memory ledger with the same claim semantics as the DynamoDB table. */
export class MemoryLedger implements Ledger {
  readonly entries = new Map<string, Entry>();

  claim(event: PageCaptured): Promise<ClaimResult> {
    const entry = this.entries.get(event.snapshotId);

    if (entry && entry.archiveId !== event.archiveId) {
      return Promise.resolve({ kind: "conflict", reason: `snapshot belongs to ${entry.archiveId}` });
    }

    if (entry && entry.status !== "PENDING") {
      return Promise.resolve(entry.status === "PROCESSING" ? { kind: "busy" } : { kind: "done", status: entry.status });
    }

    const token = randomUUID();
    const attempts = (entry?.attempts ?? 0) + 1;
    this.entries.set(event.snapshotId, { archiveId: event.archiveId, status: "PROCESSING", attempts, token });

    return Promise.resolve({ kind: "claimed", claim: { snapshotId: event.snapshotId, token, attempt: attempts } });
  }

  release(claim: Claim, reason: string): Promise<void> {
    this.update(claim, { status: "PENDING", reason });

    return Promise.resolve();
  }

  complete(claim: Claim, outcome: Outcome): Promise<void> {
    this.update(claim, outcome.status === "INDEXED" ? { status: "INDEXED" } : outcome);

    return Promise.resolve();
  }

  /** Simulates another worker holding a live claim on the snapshot. */
  holdByAnotherWorker(event: PageCaptured): void {
    this.entries.set(event.snapshotId, {
      archiveId: event.archiveId,
      status: "PROCESSING",
      attempts: 1,
      token: "other",
    });
  }

  statusOf(snapshotId: string): LedgerStatus | undefined {
    return this.entries.get(snapshotId)?.status;
  }

  private update(claim: Claim, change: Partial<Entry>): void {
    const entry = this.entries.get(claim.snapshotId);

    if (entry?.status === "PROCESSING" && entry.token === claim.token) {
      this.entries.set(claim.snapshotId, { ...entry, ...change });
    }
  }
}

/** Object store holding immutable artifacts by key; verifies digests like S3ArtifactStore. */
export class MemoryArtifacts implements ArtifactStore {
  private readonly objects = new Map<string, Uint8Array>();

  put(key: string, bytes: Uint8Array): void {
    this.objects.set(key, bytes);
  }

  read(ref: ArtifactRef): Promise<Uint8Array> {
    const bytes = this.objects.get(ref.key);

    if (bytes === undefined) {
      return Promise.reject(new Error(`no object ${ref.key}`));
    }

    verify(ref, bytes);

    return Promise.resolve(bytes);
  }
}

/** Search index that records documents by ID and can be switched offline. */
export class RecordingIndex implements DocumentIndex {
  readonly documents = new Map<string, SnapshotDocument>();
  writes = 0;
  offline = false;

  put(document: SnapshotDocument): Promise<void> {
    if (this.offline) {
      return Promise.reject(new Error("connect ECONNREFUSED opensearch:9200"));
    }

    this.writes += 1;
    this.documents.set(document.snapshotId, document);

    return Promise.resolve();
  }
}
