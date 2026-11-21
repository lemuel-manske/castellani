import { randomUUID } from "node:crypto";

import { verify } from "../../src/indexing/s3-artifacts.js";
import {
  type ArchiveState,
  type ArchiveVisibility,
  type ArtifactRef,
  type ArtifactStore,
  type Claim,
  type ClaimResult,
  type DocumentIndex,
  type IndexingCounts,
  type Ledger,
  type LedgerStatus,
  type ManifestRecord,
  type Outcome,
  type PageCaptured,
  type PublicationFact,
  type SnapshotDocument,
  type VisibilityResult,
  documentId,
} from "../../src/indexing/model.js";
import type { EventPublisher, OutboxClaim, OutboxStore, OutgoingEvent } from "../../src/outbox/outbox.js";
import type { ArchiveIndex } from "../../src/publication/handler.js";
import type { SnapshotReveal } from "../../src/reconciliation/reconciler.js";

type Entry = { status: LedgerStatus; attempts: number; token?: string; reason?: string };

type SnapshotKey = Pick<PageCaptured, "archiveId" | "snapshotId">;

/** In-memory ledger with the same claim semantics as the DynamoDB table. */
export class MemoryLedger implements Ledger {
  /** Keyed like the table: by archive and snapshot. */
  readonly entries = new Map<string, Entry>();

  claim(event: PageCaptured): Promise<ClaimResult> {
    const key = keyOf(event);
    const entry = this.entries.get(key);

    if (entry && entry.status !== "PENDING") {
      return Promise.resolve(entry.status === "PROCESSING" ? { kind: "busy" } : { kind: "done", status: entry.status });
    }

    const token = randomUUID();
    const attempts = (entry?.attempts ?? 0) + 1;
    this.entries.set(key, { status: "PROCESSING", attempts, token });

    return Promise.resolve({
      kind: "claimed",
      claim: { archiveId: event.archiveId, snapshotId: event.snapshotId, token, attempt: attempts },
    });
  }

  release(claim: Claim, reason: string): Promise<void> {
    this.update(claim, { status: "PENDING", reason });

    return Promise.resolve();
  }

  complete(claim: Claim, outcome: Outcome): Promise<void> {
    this.update(claim, outcome.status === "INDEXED" ? { status: "INDEXED" } : outcome);

    return Promise.resolve();
  }

  statuses(archiveId: string, snapshotIds: string[]): Promise<Map<string, LedgerStatus>> {
    const result = new Map<string, LedgerStatus>();

    for (const snapshotId of snapshotIds) {
      const entry = this.entries.get(keyOf({ archiveId, snapshotId }));

      if (entry) {
        result.set(snapshotId, entry.status);
      }
    }

    return Promise.resolve(result);
  }

  /** Simulates another worker holding a live claim on the snapshot. */
  holdByAnotherWorker(snapshot: SnapshotKey): void {
    this.entries.set(keyOf(snapshot), { status: "PROCESSING", attempts: 1, token: "other" });
  }

  /** Simulates the other worker releasing its claim. */
  finishByAnotherWorker(snapshot: SnapshotKey): void {
    const entry = this.entries.get(keyOf(snapshot));

    if (entry) {
      this.entries.set(keyOf(snapshot), { ...entry, status: "PENDING" });
    }
  }

  statusOf(snapshot: SnapshotKey): LedgerStatus | undefined {
    return this.entries.get(keyOf(snapshot))?.status;
  }

  private update(claim: Claim, change: Partial<Entry>): void {
    const entry = this.entries.get(keyOf(claim));

    if (entry?.status === "PROCESSING" && entry.token === claim.token) {
      this.entries.set(keyOf(claim), { ...entry, ...change });
    }
  }
}

function keyOf(snapshot: SnapshotKey): string {
  return documentId(snapshot.archiveId, snapshot.snapshotId);
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

/**
 * Search index that records documents by ID and can be switched offline.
 * Mirrors the OpenSearch adapter: document IDs derive from archive and
 * snapshot, new documents start hidden and re-indexing keeps the current
 * visibility.
 */
export class RecordingIndex implements DocumentIndex, ArchiveIndex, SnapshotReveal {
  /** Keyed by document ID, as in OpenSearch. */
  readonly documents = new Map<string, SnapshotDocument>();
  writes = 0;
  offline = false;

  put(document: Omit<SnapshotDocument, "visible">): Promise<void> {
    if (this.offline) {
      return Promise.reject(new Error("connect ECONNREFUSED opensearch:9200"));
    }

    this.writes += 1;
    const id = documentId(document.archiveId, document.snapshotId);
    const visible = this.documents.get(id)?.visible ?? false;
    this.documents.set(id, { ...document, visible });

    return Promise.resolve();
  }

  reveal(archiveId: string, snapshotIds: string[]): Promise<void> {
    for (const id of snapshotIds.map((snapshotId) => documentId(archiveId, snapshotId))) {
      const document = this.documents.get(id);

      if (document) {
        this.documents.set(id, { ...document, visible: true });
      }
    }

    return Promise.resolve();
  }

  remove(archiveId: string, snapshotId: string): Promise<void> {
    this.documents.delete(documentId(archiveId, snapshotId));

    return Promise.resolve();
  }

  purge(archiveId: string): Promise<void> {
    for (const document of [...this.documents.values()]) {
      if (document.archiveId === archiveId) {
        this.documents.delete(documentId(archiveId, document.snapshotId));
      }
    }

    return Promise.resolve();
  }

  /** The document of a snapshot, in whichever archive it was indexed. */
  document(snapshotId: string): SnapshotDocument | undefined {
    return [...this.documents.values()].find((d) => d.snapshotId === snapshotId);
  }

  /** Snapshot IDs of every indexed document, visible or not. */
  snapshotIds(): string[] {
    return [...this.documents.values()].map((d) => d.snapshotId);
  }

  /** Snapshot IDs a search would return: only visible documents. */
  searchable(): string[] {
    return [...this.documents.values()].filter((d) => d.visible).map((d) => d.snapshotId);
  }
}

/**
 * In-memory archive facts with the same write rules as the DynamoDB table.
 * A report writes its state and its outbox record together, then awaits
 * `onEnqueued`, where in-memory scenarios dispatch inline.
 */
export class MemoryVisibility implements ArchiveVisibility {
  private readonly states = new Map<string, ArchiveState>();
  private readonly pending = new Set<string>();

  constructor(
    readonly outbox = new MemoryOutbox(),
    private readonly onEnqueued: () => Promise<unknown> = () => Promise.resolve(),
  ) {}

  get(archiveId: string): Promise<ArchiveState> {
    return Promise.resolve({ ...this.stateOf(archiveId) });
  }

  recordDecision(archiveId: string, fact: PublicationFact): Promise<VisibilityResult> {
    const state = this.stateOf(archiveId);

    if (state.compensationVersion !== undefined || (state.decision && !same(state.decision, fact))) {
      return Promise.resolve({ kind: "conflict", reason: "decision conflicts with recorded facts" });
    }

    return this.save({ ...state, decision: pick(fact) });
  }

  recordPublished(archiveId: string, fact: PublicationFact): Promise<VisibilityResult> {
    const state = this.stateOf(archiveId);

    if (state.compensationVersion !== undefined || (state.published && !same(state.published, fact))) {
      return Promise.resolve({ kind: "conflict", reason: "publication conflicts with recorded facts" });
    }

    return this.save({ ...state, published: pick(fact) });
  }

  recordCompensation(archiveId: string, decisionVersion: number): Promise<VisibilityResult> {
    const state = this.stateOf(archiveId);
    const otherCompensation = state.compensationVersion !== undefined && state.compensationVersion !== decisionVersion;

    if (state.decision || state.published || otherCompensation) {
      return Promise.resolve({ kind: "conflict", reason: "compensation conflicts with recorded facts" });
    }

    return this.save({ ...state, compensationVersion: decisionVersion });
  }

  recordManifest(archiveId: string, manifest: ManifestRecord): Promise<VisibilityResult> {
    const state = this.stateOf(archiveId);

    if (state.manifest && state.manifest.digest !== manifest.digest) {
      return Promise.resolve({ kind: "conflict", reason: "a different manifest was already recorded" });
    }

    this.pending.add(archiveId);

    return this.save({ ...state, manifest, reconcileRequests: state.reconcileRequests + 1 });
  }

  requestReconcile(archiveId: string): Promise<void> {
    const state = this.stateOf(archiveId);
    this.pending.add(archiveId);
    this.states.set(archiveId, { ...state, reconcileRequests: state.reconcileRequests + 1 });

    return Promise.resolve();
  }

  pendingReconciliations(limit: number): Promise<string[]> {
    return Promise.resolve([...this.pending].slice(0, limit));
  }

  clearReconcile(archiveId: string, requests: number): Promise<boolean> {
    if (this.stateOf(archiveId).reconcileRequests !== requests) {
      return Promise.resolve(false);
    }

    this.pending.delete(archiveId);

    return Promise.resolve(true);
  }

  reportIndexing(archiveId: string, counts: IndexingCounts, event: OutgoingEvent): Promise<void> {
    const state = this.stateOf(archiveId);

    return this.report(state.manifest !== undefined && state.indexingReported === undefined, event, {
      ...state,
      indexingReported: counts,
    });
  }

  reportReady(archiveId: string, event: OutgoingEvent): Promise<void> {
    const state = this.stateOf(archiveId);

    return this.report(state.indexingReported !== undefined && state.readyReported !== true, event, {
      ...state,
      readyReported: true,
    });
  }

  acknowledgeCompensation(archiveId: string, event: OutgoingEvent): Promise<void> {
    const state = this.stateOf(archiveId);

    return this.report(state.compensationVersion !== undefined && state.compensationAcknowledged !== true, event, {
      ...state,
      compensationAcknowledged: true,
    });
  }

  isPending(archiveId: string): boolean {
    return this.pending.has(archiveId);
  }

  private stateOf(archiveId: string): ArchiveState {
    return this.states.get(archiveId) ?? { archiveId, reconcileRequests: 0 };
  }

  /** State change and outbox record together, like the DynamoDB transaction. */
  private async report(allowed: boolean, event: OutgoingEvent, next: ArchiveState): Promise<void> {
    if (!allowed || this.outbox.has(event.messageId)) {
      return;
    }

    this.states.set(next.archiveId, next);
    this.outbox.enqueue(event);
    await this.onEnqueued();
  }

  private save(state: ArchiveState): Promise<VisibilityResult> {
    this.states.set(state.archiveId, state);

    return Promise.resolve({ kind: "recorded", state: { ...state } });
  }
}

type OutboxRecord = { event: OutgoingEvent; sent: boolean; attempts: number; token?: string; leaseUntil?: number };

/** In-memory outbox with the claim and lease rules of the DynamoDB table. */
export class MemoryOutbox implements OutboxStore {
  readonly records = new Map<string, OutboxRecord>();

  enqueue(event: OutgoingEvent): void {
    this.records.set(event.messageId, { event, sent: false, attempts: 0 });
  }

  has(messageId: string): boolean {
    return this.records.has(messageId);
  }

  /** Message IDs still awaiting a broker confirm. */
  unsent(): string[] {
    return [...this.records.entries()].filter(([, record]) => !record.sent).map(([messageId]) => messageId);
  }

  pending(limit: number): Promise<string[]> {
    return Promise.resolve(this.unsent().slice(0, limit));
  }

  claim(messageId: string, now: Date): Promise<OutboxClaim | undefined> {
    const record = this.records.get(messageId);

    if (record === undefined || record.sent || (record.leaseUntil ?? 0) >= now.getTime()) {
      return Promise.resolve(undefined);
    }

    const token = randomUUID();
    const attempts = record.attempts + 1;
    this.records.set(messageId, { ...record, attempts, token, leaseUntil: now.getTime() + 30_000 });

    return Promise.resolve({ messageId, token, event: record.event, attempts });
  }

  markSent(claim: OutboxClaim): Promise<void> {
    this.fenced(claim, { sent: true });

    return Promise.resolve();
  }

  release(claim: OutboxClaim, _reason: string, retryAt: Date): Promise<void> {
    this.fenced(claim, { leaseUntil: retryAt.getTime() });

    return Promise.resolve();
  }

  /** Simulates another dispatcher holding a live claim on the record. */
  holdByAnotherDispatcher(messageId: string, now: Date): void {
    const record = this.records.get(messageId);

    if (record) {
      this.records.set(messageId, { ...record, token: "other", leaseUntil: now.getTime() + 30_000 });
    }
  }

  private fenced(claim: OutboxClaim, change: Partial<OutboxRecord>): void {
    const record = this.records.get(claim.messageId);

    if (record?.token === claim.token) {
      this.records.set(claim.messageId, { ...record, ...change });
    }
  }
}

/**
 * Records events the service emits, as a broker with publisher confirms
 * would accept them. `unroutable` simulates no queue being bound.
 */
export class RecordingPublisher implements EventPublisher {
  readonly published: OutgoingEvent[] = [];
  unroutable = false;

  publish(message: OutgoingEvent): Promise<void> {
    if (this.unroutable) {
      return Promise.reject(new Error(`no queue is bound for ${message.type}`));
    }

    this.published.push(message);

    return Promise.resolve();
  }

  ofType(type: string): OutgoingEvent[] {
    return this.published.filter((event) => event.type === type);
  }
}

function same(a: PublicationFact, b: PublicationFact): boolean {
  return a.decisionVersion === b.decisionVersion && a.packageDigest === b.packageDigest;
}

function pick(fact: PublicationFact): PublicationFact {
  return { decisionVersion: fact.decisionVersion, packageDigest: fact.packageDigest };
}
