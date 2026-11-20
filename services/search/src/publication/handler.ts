import { RejectedEventError } from "../indexing/indexer.js";
import { type ArchiveVisibility, type PublicationFact, type VisibilityResult, isVisible } from "../indexing/model.js";

/** Archive-wide operations on the search index. All are idempotent. */
export interface ArchiveIndex {
  /** Makes every indexed snapshot of the archive searchable. */
  activate(archiveId: string): Promise<void>;
  /** Removes every indexed snapshot of the archive. */
  purge(archiveId: string): Promise<void>;
}

export interface EventPublisher {
  /** Publishes an event and resolves once the broker confirms it. */
  publish(message: OutgoingEvent): Promise<void>;
}

export type OutgoingEvent = {
  messageId: string;
  correlationId: string;
  type: string;
  version: 1;
  occurredAt: string;
  payload: Record<string, unknown>;
};

export type PublicationResult = "visible" | "pending" | "compensated";

/**
 * Applies the publication protocol of ADR-0027 to search visibility. The
 * decision and the replay acknowledgment are stored independently; whichever
 * completes the matching pair activates the archive. Compensation removes the
 * archive's documents and acknowledges with `SearchCompensated`.
 */
export class PublicationHandler {
  constructor(
    private readonly visibility: ArchiveVisibility,
    private readonly index: ArchiveIndex,
    private readonly events: EventPublisher,
    private readonly clock: () => Date = () => new Date(),
  ) {}

  async publicationDecided(archiveId: string, fact: PublicationFact): Promise<PublicationResult> {
    return this.activateIfVisible(archiveId, await this.visibility.recordDecision(archiveId, fact));
  }

  async archivePublished(archiveId: string, fact: PublicationFact): Promise<PublicationResult> {
    return this.activateIfVisible(archiveId, await this.visibility.recordPublished(archiveId, fact));
  }

  async compensationDecided(archiveId: string, decisionVersion: number): Promise<PublicationResult> {
    const result = await this.visibility.recordCompensation(archiveId, decisionVersion);

    if (result.kind === "conflict") {
      throw new RejectedEventError(result.reason);
    }

    await this.index.purge(archiveId);

    // Deterministic identity: a redelivered compensation command re-emits the
    // same logical acknowledgment, which the Coordinator deduplicates.
    await this.events.publish({
      messageId: `SearchCompensated:${archiveId}:${decisionVersion}`,
      correlationId: archiveId,
      type: "SearchCompensated",
      version: 1,
      occurredAt: this.clock().toISOString(),
      payload: { archiveId, decisionVersion },
    });

    return "compensated";
  }

  private async activateIfVisible(archiveId: string, result: VisibilityResult): Promise<PublicationResult> {
    if (result.kind === "conflict") {
      throw new RejectedEventError(result.reason);
    }

    if (!isVisible(result.state)) {
      return "pending";
    }

    // Repeated on every matching delivery, so a crash after recording the
    // fact but before activating is repaired by redelivery.
    await this.index.activate(archiveId);

    return "visible";
  }
}
