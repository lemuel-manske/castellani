import { RejectedEventError } from "../indexing/indexer.js";
import {
  type ArchiveVisibility,
  type ArtifactRef,
  type PublicationFact,
  type VisibilityResult,
  isVisible,
} from "../indexing/model.js";
import type { Manifest } from "../reconciliation/reconciler.js";

/** Archive-wide operations on the search index. All are idempotent. */
export interface ArchiveIndex {
  /** Removes every indexed snapshot of the archive. */
  purge(archiveId: string): Promise<void>;
}

/** Requests a reconciliation pass for an archive (see `Reconciler`). */
export interface ReconcileTrigger {
  request(archiveId: string): Promise<void>;
}

export interface ManifestLoader {
  loadManifest(ref: ArtifactRef, archiveId: string): Promise<Manifest>;
}

export type PublicationResult = "visible" | "pending" | "compensated" | "manifest-recorded";

/**
 * Records the facts of ADR-0019 and ADR-0027 that govern search visibility.
 * The decision, the replay acknowledgment and the manifest are stored
 * independently and in any order; every recorded fact requests a
 * reconciliation, which reveals the archive's manifest snapshots once all
 * of them agree. Compensation removes the archive's documents and
 * acknowledges with `SearchCompensated` through the outbox.
 */
export class PublicationHandler {
  constructor(
    private readonly visibility: ArchiveVisibility,
    private readonly index: ArchiveIndex,
    private readonly reconcile: ReconcileTrigger,
    private readonly manifests: ManifestLoader,
    private readonly clock: () => Date = () => new Date(),
  ) {}

  async publicationDecided(archiveId: string, fact: PublicationFact): Promise<PublicationResult> {
    return this.afterFact(archiveId, await this.visibility.recordDecision(archiveId, fact));
  }

  async archivePublished(archiveId: string, fact: PublicationFact): Promise<PublicationResult> {
    return this.afterFact(archiveId, await this.visibility.recordPublished(archiveId, fact));
  }

  /** `CrawlCompleted`: verifies and records the immutable final manifest. */
  async crawlCompleted(archiveId: string, ref: ArtifactRef, digest: string): Promise<PublicationResult> {
    const manifest = await this.manifests.loadManifest(ref, archiveId);
    const result = await this.visibility.recordManifest(archiveId, {
      digest,
      ref,
      expected: manifest.snapshots.length,
    });

    if (result.kind === "conflict") {
      throw new RejectedEventError(result.reason);
    }

    await this.reconcile.request(archiveId);

    return "manifest-recorded";
  }

  async compensationDecided(archiveId: string, decisionVersion: number): Promise<PublicationResult> {
    const result = await this.visibility.recordCompensation(archiveId, decisionVersion);

    if (result.kind === "conflict") {
      throw new RejectedEventError(result.reason);
    }

    await this.index.purge(archiveId);

    // Enqueued only after the cleanup, in one transaction with the record that
    // it finished; a crash before that re-runs the idempotent cleanup on
    // redelivery. The deterministic identity lets the Coordinator deduplicate.
    await this.visibility.acknowledgeCompensation(archiveId, {
      messageId: `SearchCompensated:${archiveId}:${String(decisionVersion)}`,
      correlationId: archiveId,
      type: "SearchCompensated",
      version: 1,
      occurredAt: this.clock().toISOString(),
      payload: { archiveId, decisionVersion },
    });

    return "compensated";
  }

  private async afterFact(archiveId: string, result: VisibilityResult): Promise<PublicationResult> {
    if (result.kind === "conflict") {
      throw new RejectedEventError(result.reason);
    }

    // Requested on every matching delivery, so a crash after recording the
    // fact but before the request is repaired by redelivery.
    await this.reconcile.request(archiveId);

    return isVisible(result.state) ? "visible" : "pending";
  }
}
