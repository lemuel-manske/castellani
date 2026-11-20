import { randomUUID } from "node:crypto";

import { verify } from "../../src/indexing/s3-artifacts.js";
import type {
  ArchiveState,
  ArchiveVisibility,
  ArtifactRef,
  ArtifactStore,
  Claim,
  ClaimResult,
  DocumentIndex,
  Ledger,
  LedgerStatus,
  Outcome,
  PageCaptured,
  PublicationFact,
  SnapshotDocument,
  VisibilityResult,
} from "../../src/indexing/model.js";
import type { ArchiveIndex, EventPublisher, OutgoingEvent } from "../../src/publication/handler.js";

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
export class RecordingIndex implements DocumentIndex, ArchiveIndex {
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

  reveal(snapshotId: string): Promise<void> {
    const document = this.documents.get(snapshotId);

    if (document) {
      this.documents.set(snapshotId, { ...document, visible: true });
    }

    return Promise.resolve();
  }

  remove(snapshotId: string): Promise<void> {
    this.documents.delete(snapshotId);

    return Promise.resolve();
  }

  activate(archiveId: string): Promise<void> {
    for (const document of this.archive(archiveId)) {
      this.documents.set(document.snapshotId, { ...document, visible: true });
    }

    return Promise.resolve();
  }

  purge(archiveId: string): Promise<void> {
    for (const document of this.archive(archiveId)) {
      this.documents.delete(document.snapshotId);
    }

    return Promise.resolve();
  }

  /** Snapshot IDs a search would return: only visible documents. */
  searchable(): string[] {
    return [...this.documents.values()].filter((d) => d.visible).map((d) => d.snapshotId);
  }

  private archive(archiveId: string): SnapshotDocument[] {
    return [...this.documents.values()].filter((d) => d.archiveId === archiveId);
  }
}

/** In-memory publication facts with the same write rules as the DynamoDB table. */
export class MemoryVisibility implements ArchiveVisibility {
  private readonly states = new Map<string, ArchiveState>();

  get(archiveId: string): Promise<ArchiveState> {
    return Promise.resolve({ ...(this.states.get(archiveId) ?? { archiveId }) });
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

  private stateOf(archiveId: string): ArchiveState {
    return this.states.get(archiveId) ?? { archiveId };
  }

  private save(state: ArchiveState): Promise<VisibilityResult> {
    this.states.set(state.archiveId, state);

    return Promise.resolve({ kind: "recorded", state: { ...state } });
  }
}

/** Records events the service emits, as a broker with publisher confirms would accept them. */
export class RecordingPublisher implements EventPublisher {
  readonly published: OutgoingEvent[] = [];

  publish(message: OutgoingEvent): Promise<void> {
    this.published.push(message);

    return Promise.resolve();
  }
}

function same(a: PublicationFact, b: PublicationFact): boolean {
  return a.decisionVersion === b.decisionVersion && a.packageDigest === b.packageDigest;
}

function pick(fact: PublicationFact): PublicationFact {
  return { decisionVersion: fact.decisionVersion, packageDigest: fact.packageDigest };
}
