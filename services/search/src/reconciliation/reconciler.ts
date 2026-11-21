import { type Indexer, RejectedEventError } from "../indexing/indexer.js";
import {
  type ArchiveState,
  type ArchiveVisibility,
  type ArtifactRef,
  type ArtifactStore,
  type IndexingCounts,
  type Ledger,
  type LedgerStatus,
  type PageCaptured,
  DocumentError,
  UnsupportedContentError,
  isCompensated,
  isVisible,
  terminalStatuses,
} from "../indexing/model.js";
import type { OutgoingEvent } from "../outbox/outbox.js";
import type { ArchiveIndex } from "../publication/handler.js";
import { Wakeable } from "../support/wakeable.js";

/** One authorized snapshot in the immutable final manifest. */
export type ManifestEntry = {
  snapshotId: string;
  urlKey: string;
  url: string;
  finalUrl: string;
  capturedAt: string;
  contentType?: string;
  warcArtifacts: ArtifactRef[];
};

export type Manifest = { archiveId: string; collectionId?: string; snapshots: ManifestEntry[] };

export interface ManifestParser {
  parseManifest(document: unknown): Manifest;
}

/** Archive-level fields stamped on documents when they are revealed. */
export type RevealScope = { collectionId?: string };

export interface SnapshotReveal {
  /** Marks indexed snapshots of the archive searchable; missing documents are skipped. */
  reveal(archiveId: string, snapshotIds: string[], scope?: RevealScope): Promise<void>;
  /** The snapshots of the archive that currently have a search document. */
  present(archiveId: string, snapshotIds: string[]): Promise<Set<string>>;
}

/** Reason recorded on a ledger entry reopened by divergence repair. */
export const MISSING_DOCUMENT_REASON = "search document missing from the index";

export type ReconcileResult = "compensated" | "no-manifest" | "incomplete" | "complete";

type Logger = { warn(object: object, message: string): void };

/**
 * Converges one archive's search projection against its final manifest
 * (ADR-0019). Every step is idempotent, so reconciliation can be triggered by
 * events, repeated periodically, and run concurrently by several replicas:
 *
 * 1. Repair divergence: a snapshot the ledger records as `INDEXED` whose
 *    document is missing from OpenSearch (lost or rebuilt index) is reopened.
 *    Then index manifest snapshots without a terminal ledger outcome from the
 *    manifest's own artifact references, recovering lost `PageCaptured`.
 * 2. When the archive is published, reveal its indexed manifest snapshots,
 *    stamped with the manifest's collection. Snapshots outside the manifest
 *    are never revealed.
 * 3. Once every manifest snapshot is terminal, report `SearchIndexingCompleted`;
 *    once that holds and the archive is published, report `SearchReady`. Each
 *    report and its outbox record are written in one transaction.
 */
export class Reconciler {
  constructor(
    private readonly visibility: ArchiveVisibility,
    private readonly ledger: Ledger,
    private readonly indexer: Pick<Indexer, "handle">,
    private readonly artifacts: ArtifactStore,
    private readonly manifests: ManifestParser,
    private readonly index: ArchiveIndex & SnapshotReveal,
    private readonly log: Logger,
    private readonly clock: () => Date = () => new Date(),
  ) {}

  /**
   * Reads and verifies a manifest. Integrity or schema failures of an
   * immutable manifest cannot be fixed by retrying, so they reject the event.
   */
  async loadManifest(ref: ArtifactRef, archiveId: string): Promise<Manifest> {
    let manifest: Manifest;

    try {
      const bytes = await this.artifacts.read(ref);
      manifest = this.manifests.parseManifest(JSON.parse(Buffer.from(bytes).toString("utf8")));
    } catch (error) {
      if (error instanceof SyntaxError || error instanceof DocumentError || error instanceof UnsupportedContentError) {
        throw new RejectedEventError(`unusable manifest for archive ${archiveId}: ${error.message}`, { cause: error });
      }

      throw error;
    }

    if (manifest.archiveId !== archiveId) {
      throw new RejectedEventError(`manifest belongs to archive ${manifest.archiveId}, not ${archiveId}`);
    }

    return manifest;
  }

  async reconcile(archiveId: string): Promise<ReconcileResult> {
    const state = await this.visibility.get(archiveId);

    if (isCompensated(state)) {
      await this.index.purge(archiveId);
      await this.visibility.clearReconcile(archiveId, state.reconcileRequests);

      return "compensated";
    }

    if (state.manifest === undefined) {
      await this.visibility.clearReconcile(archiveId, state.reconcileRequests);

      return "no-manifest";
    }

    const manifest = await this.loadManifest(state.manifest.ref, archiveId);
    const ids = manifest.snapshots.map((entry) => entry.snapshotId);
    const recorded = await this.repairDivergence(archiveId, await this.ledger.statuses(archiveId, ids));
    const statuses = await this.indexMissing(manifest, state.manifest.digest, recorded);

    if (isVisible(state)) {
      await this.index.reveal(
        archiveId,
        ids.filter((id) => statuses.get(id) === "INDEXED"),
        manifest.collectionId !== undefined ? { collectionId: manifest.collectionId } : {},
      );
    }

    if (ids.some((id) => !isTerminal(statuses.get(id)))) {
      // The request stays pending; the periodic pass retries.
      return "incomplete";
    }

    await this.report(state, countOutcomes(ids, statuses));
    await this.visibility.clearReconcile(archiveId, state.reconcileRequests);

    return "complete";
  }

  /**
   * Neither DynamoDB nor OpenSearch alone proves the other succeeded: reopens
   * `INDEXED` snapshots whose document is gone, so they are indexed again.
   */
  private async repairDivergence(
    archiveId: string,
    statuses: Map<string, LedgerStatus>,
  ): Promise<Map<string, LedgerStatus>> {
    const indexed = [...statuses].filter(([, status]) => status === "INDEXED").map(([id]) => id);

    if (indexed.length === 0) {
      return statuses;
    }

    const present = await this.index.present(archiveId, indexed);
    const lost = indexed.filter((id) => !present.has(id));

    if (lost.length === 0) {
      return statuses;
    }

    this.log.warn({ archiveId, snapshotIds: lost }, "indexed snapshots missing from the search index; reindexing");
    await this.ledger.reopen(archiveId, lost, MISSING_DOCUMENT_REASON, this.clock());

    const repaired = new Map(statuses);

    for (const id of lost) {
      repaired.set(id, "PENDING");
    }

    return repaired;
  }

  private async indexMissing(
    manifest: Manifest,
    digest: string,
    statuses: Map<string, LedgerStatus>,
  ): Promise<Map<string, LedgerStatus>> {
    const missing = manifest.snapshots.filter((entry) => !isTerminal(statuses.get(entry.snapshotId)));

    if (missing.length === 0) {
      return statuses;
    }

    for (const entry of missing) {
      try {
        await this.indexer.handle(toEvent(manifest.archiveId, digest, entry));
      } catch (error) {
        // Retryable outcomes (busy, outage, document error with attempts
        // left) keep the snapshot non-terminal; the next pass picks it up.
        this.log.warn({ err: error, snapshotId: entry.snapshotId }, "manifest snapshot not indexed yet");
      }
    }

    return this.ledger.statuses(
      manifest.archiveId,
      manifest.snapshots.map((entry) => entry.snapshotId),
    );
  }

  private async report(state: ArchiveState, counts: IndexingCounts): Promise<void> {
    const { archiveId } = state;
    const digest = state.manifest?.digest ?? "";

    if (state.indexingReported === undefined) {
      await this.visibility.reportIndexing(
        archiveId,
        counts,
        this.event(`SearchIndexingCompleted:${archiveId}:${digest}`, "SearchIndexingCompleted", archiveId, {
          manifestDigest: digest,
          ...counts,
        }),
      );
    }

    if (isVisible(state) && state.readyReported !== true && state.decision !== undefined) {
      const { decisionVersion } = state.decision;

      await this.visibility.reportReady(
        archiveId,
        this.event(`SearchReady:${archiveId}:${String(decisionVersion)}`, "SearchReady", archiveId, {
          decisionVersion,
          manifestDigest: digest,
        }),
      );
    }
  }

  private event(messageId: string, type: string, archiveId: string, payload: object): OutgoingEvent {
    return {
      messageId,
      correlationId: archiveId,
      type,
      version: 1,
      occurredAt: this.clock().toISOString(),
      payload: { archiveId, ...payload },
    };
  }
}

function toEvent(archiveId: string, digest: string, entry: ManifestEntry): PageCaptured {
  return {
    messageId: `manifest:${digest}:${entry.snapshotId}`,
    archiveId,
    snapshotId: entry.snapshotId,
    urlKey: entry.urlKey,
    url: entry.url,
    finalUrl: entry.finalUrl,
    capturedAt: entry.capturedAt,
    ...(entry.contentType ? { contentType: entry.contentType } : {}),
    warcArtifacts: entry.warcArtifacts,
  };
}

function isTerminal(status: LedgerStatus | undefined): boolean {
  return status !== undefined && terminalStatuses.has(status);
}

function countOutcomes(ids: string[], statuses: Map<string, LedgerStatus>): IndexingCounts {
  const counts: IndexingCounts = { expected: ids.length, indexed: 0, failed: 0, unsupported: 0 };

  for (const id of ids) {
    switch (statuses.get(id)) {
      case "INDEXED":
        counts.indexed += 1;
        break;
      case "UNSUPPORTED":
        counts.unsupported += 1;
        break;
      default:
        // FAILED, or DISCARDED in a compensation race: not indexed.
        counts.failed += 1;
    }
  }

  return counts;
}

/**
 * Periodically requests reconciliation of every archive with a manifest, so
 * divergence between the ledger and OpenSearch (a lost or rebuilt index, a
 * deleted document) is repaired even when no event arrives. The first pass
 * runs at startup. Requests are idempotent and served by the scheduler.
 */
export class RepairSweep {
  private readonly sleeper = new Wakeable();
  private stopping = false;

  constructor(
    private readonly visibility: Pick<ArchiveVisibility, "archivesWithManifest">,
    private readonly request: (archiveId: string) => Promise<void>,
    private readonly intervalMs: number,
    private readonly log: Logger,
  ) {}

  async run(): Promise<void> {
    while (!this.isStopping()) {
      try {
        await this.sweep();
      } catch (error) {
        this.log.warn({ err: error }, "repair sweep failed; retrying on the next pass");
      }

      await this.sleeper.sleep(this.intervalMs);
    }
  }

  stop(): void {
    this.stopping = true;
    this.sleeper.wake();
  }

  /** One pass over every archive with a manifest. Returns how many were requested. */
  async sweep(): Promise<number> {
    let requested = 0;
    let after: string | undefined;

    do {
      const page = await this.visibility.archivesWithManifest(100, after);

      for (const archiveId of page.archiveIds) {
        if (this.isStopping()) {
          return requested;
        }

        await this.request(archiveId);
        requested += 1;
      }

      after = page.next;
    } while (after !== undefined);

    return requested;
  }

  /** Read through a method: `stop()` flips the flag concurrently with `run()`. */
  private isStopping(): boolean {
    return this.stopping;
  }
}

/**
 * Runs reconciliations off the message path: event-triggered requests run
 * promptly, and a periodic pass picks up durable requests left by crashes,
 * restarts, or other replicas.
 */
export class ReconcileScheduler {
  private readonly queued = new Set<string>();
  private readonly sleeper = new Wakeable();
  private stopping = false;

  constructor(
    private readonly reconciler: Pick<Reconciler, "reconcile">,
    private readonly visibility: Pick<ArchiveVisibility, "pendingReconciliations">,
    private readonly intervalMs: number,
    private readonly log: Logger,
  ) {}

  schedule(archiveId: string): void {
    this.queued.add(archiveId);
    this.sleeper.wake();
  }

  async run(): Promise<void> {
    let nextScan = 0;

    while (!this.stopping) {
      if (Date.now() >= nextScan) {
        nextScan = Date.now() + this.intervalMs;

        try {
          for (const archiveId of await this.visibility.pendingReconciliations(100)) {
            this.queued.add(archiveId);
          }
        } catch (error) {
          this.log.warn({ err: error }, "could not list pending reconciliations");
        }
      }

      for (const archiveId of [...this.queued]) {
        this.queued.delete(archiveId);

        try {
          await this.reconciler.reconcile(archiveId);
        } catch (error) {
          this.log.warn({ err: error, archiveId }, "reconciliation failed; it stays pending");
        }
      }

      // Requests scheduled while the batch ran are served without sleeping.
      if (this.queued.size > 0) {
        continue;
      }

      await this.sleeper.sleep(nextScan - Date.now());
    }
  }

  stop(): void {
    this.stopping = true;
    this.sleeper.wake();
  }
}
