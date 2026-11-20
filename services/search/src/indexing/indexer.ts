import { extractPage } from "./extract.js";
import {
  type ArchiveVisibility,
  type ArtifactStore,
  type Claim,
  type DocumentIndex,
  type Ledger,
  type PageCaptured,
  DocumentError,
  UnsupportedContentError,
  isCompensated,
  isVisible,
} from "./model.js";

/** The event cannot be processed now; redeliver it later. */
export class RetryableError extends Error {}

/** The event contradicts durable state and must not be retried. */
export class RejectedEventError extends Error {}

export type IndexResult = "indexed" | "duplicate" | "failed" | "unsupported" | "discarded";

export type IndexerOptions = {
  maxDocumentAttempts: number;
  clock?: () => Date;
};

const COMPENSATED_REASON = "archive was compensated";

/**
 * Indexes one captured snapshot. Processing is keyed by `snapshotId`: repeated
 * or concurrent deliveries resolve through the ledger claim, and the search
 * document identity is the snapshot ID, so a crash between the OpenSearch
 * write and the ledger update is repaired by simply indexing again.
 *
 * Visibility follows the archive's publication facts. The indexer writes the
 * document, then re-reads those facts; archive activation and purge record
 * the facts, then update documents. Whichever runs second sees the other's
 * write, so a snapshot indexed concurrently with activation or compensation
 * cannot end up hidden or left behind.
 */
export class Indexer {
  private readonly clock: () => Date;

  constructor(
    private readonly ledger: Ledger,
    private readonly artifacts: ArtifactStore,
    private readonly index: DocumentIndex,
    private readonly visibility: ArchiveVisibility,
    private readonly options: IndexerOptions,
  ) {
    this.clock = options.clock ?? (() => new Date());
  }

  async handle(event: PageCaptured): Promise<IndexResult> {
    const claimed = await this.ledger.claim(event, this.clock());

    switch (claimed.kind) {
      case "done":
        return "duplicate";
      case "busy":
        throw new RetryableError(`snapshot ${event.snapshotId} is being indexed by another worker`);
      case "conflict":
        throw new RejectedEventError(claimed.reason);
      case "claimed":
        break;
    }

    const { claim } = claimed;

    try {
      const before = await this.visibility.get(event.archiveId);

      if (isCompensated(before)) {
        return await this.discard(claim);
      }

      const warcs = await Promise.all(event.warcArtifacts.map((ref) => this.artifacts.read(ref)));
      const targets = event.finalUrl ? [event.finalUrl, event.url] : [event.url];
      const page = await extractPage(warcs, targets);
      const visible = isVisible(before);

      await this.index.put({
        snapshotId: event.snapshotId,
        archiveId: event.archiveId,
        urlKey: event.urlKey,
        url: event.url,
        ...(event.finalUrl ? { finalUrl: event.finalUrl } : {}),
        capturedAt: event.capturedAt,
        contentType: page.contentType,
        ...(page.title ? { title: page.title } : {}),
        content: page.content,
        indexedAt: this.clock().toISOString(),
        visible,
      });

      const after = await this.visibility.get(event.archiveId);

      if (isCompensated(after)) {
        await this.index.remove(event.snapshotId);

        return await this.discard(claim);
      }

      if (!visible && isVisible(after)) {
        await this.index.reveal(event.snapshotId);
      }
    } catch (error) {
      return this.fail(claim, error);
    }

    await this.ledger.complete(claim, { status: "INDEXED" }, this.clock());

    return "indexed";
  }

  private async discard(claim: Claim): Promise<"discarded"> {
    await this.ledger.complete(claim, { status: "DISCARDED", reason: COMPENSATED_REASON }, this.clock());

    return "discarded";
  }

  private async fail(claim: Claim, error: unknown): Promise<"failed" | "unsupported"> {
    const reason = error instanceof Error ? error.message : String(error);

    if (error instanceof UnsupportedContentError) {
      await this.ledger.complete(claim, { status: "UNSUPPORTED", reason }, this.clock());

      return "unsupported";
    }

    if (error instanceof DocumentError && claim.attempt >= this.options.maxDocumentAttempts) {
      await this.ledger.complete(claim, { status: "FAILED", reason }, this.clock());

      return "failed";
    }

    // Infrastructure failures (S3, OpenSearch, DynamoDB) and document errors
    // with attempts left stay recoverable: release the claim and redeliver.
    await this.ledger.release(claim, reason, this.clock());

    throw new RetryableError(reason, { cause: error });
  }
}
