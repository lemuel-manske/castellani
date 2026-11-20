import { extractPage } from "./extract.js";
import {
  type ArtifactStore,
  type DocumentIndex,
  type Ledger,
  type PageCaptured,
  DocumentError,
  UnsupportedContentError,
} from "./model.js";

/** The event cannot be processed now; redeliver it later. */
export class RetryableError extends Error {}

/** The event contradicts durable state and must not be retried. */
export class RejectedEventError extends Error {}

export type IndexResult = "indexed" | "duplicate" | "failed" | "unsupported";

export type IndexerOptions = {
  maxDocumentAttempts: number;
  clock?: () => Date;
};

/**
 * Indexes one captured snapshot. Processing is keyed by `snapshotId`: repeated
 * or concurrent deliveries resolve through the ledger claim, and the search
 * document identity is the snapshot ID, so a crash between the OpenSearch
 * write and the ledger update is repaired by simply indexing again.
 */
export class Indexer {
  private readonly clock: () => Date;

  constructor(
    private readonly ledger: Ledger,
    private readonly artifacts: ArtifactStore,
    private readonly index: DocumentIndex,
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
      const warcs = await Promise.all(event.warcArtifacts.map((ref) => this.artifacts.read(ref)));
      const targets = event.finalUrl ? [event.finalUrl, event.url] : [event.url];
      const page = await extractPage(warcs, targets);

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
      });
    } catch (error) {
      return this.fail(claim, error);
    }

    await this.ledger.complete(claim, { status: "INDEXED" }, this.clock());

    return "indexed";
  }

  private async fail(claim: Parameters<Ledger["release"]>[0], error: unknown): Promise<"failed" | "unsupported"> {
    const reason = error instanceof Error ? error.message : String(error);

    if (error instanceof UnsupportedContentError) {
      await this.ledger.complete(claim, { status: "UNSUPPORTED", reason }, this.clock());

      return "unsupported";
    }

    if (error instanceof DocumentError && claim.attempt >= this.options.maxDocumentAttempts) {
      await this.ledger.complete(claim, { status: "FAILED", reason }, this.clock());

      return "failed";
    }

    // Infrastructure failures (S3, OpenSearch) and document errors with
    // attempts left stay recoverable: release the claim and redeliver.
    await this.ledger.release(claim, reason, this.clock());

    throw new RetryableError(reason, { cause: error });
  }
}
