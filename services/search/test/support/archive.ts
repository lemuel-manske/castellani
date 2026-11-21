import { randomUUID } from "node:crypto";

import { Indexer } from "../../src/indexing/indexer.js";
import type { ArtifactRef, PageCaptured, PublicationFact } from "../../src/indexing/model.js";
import { Contracts } from "../../src/messaging/contracts.js";
import { OutboxDispatcher } from "../../src/outbox/outbox.js";
import { PublicationHandler } from "../../src/publication/handler.js";
import { type ManifestEntry, Reconciler } from "../../src/reconciliation/reconciler.js";
import {
  MemoryArtifacts,
  MemoryLedger,
  MemoryOutbox,
  MemoryVisibility,
  RecordingIndex,
  RecordingPublisher,
} from "./doubles.js";
import { artifactRefFor, buildWarc } from "./warc.js";

export const PACKAGE: PublicationFact = { decisionVersion: 1, packageDigest: "sha256:package-1" };

export type CapturedPage = { event: PageCaptured; entry: ManifestEntry };

const silent = { warn: () => undefined };

/**
 * The Search service wired in memory. Reconciliation requests and outbox
 * dispatch run inline, so a scenario observes their effects as soon as the
 * triggering call returns. `advance` moves the dispatcher's clock past
 * retry backoffs.
 */
export function searchService() {
  let now = Date.parse("2026-11-01T12:30:00Z");
  const clock = () => new Date(now);
  const ledger = new MemoryLedger();
  const artifacts = new MemoryArtifacts();
  const index = new RecordingIndex();
  const events = new RecordingPublisher();
  const outbox = new MemoryOutbox();
  const dispatcher = new OutboxDispatcher(outbox, events, { intervalMs: 1_000 }, silent, clock);
  const visibility = new MemoryVisibility(outbox, () => dispatcher.dispatchPending());
  const contracts = new Contracts();
  const indexer = new Indexer(ledger, artifacts, index, visibility, { maxDocumentAttempts: 2 });
  const reconciler = new Reconciler(visibility, ledger, indexer, artifacts, contracts, index, silent);
  const publication = new PublicationHandler(
    visibility,
    index,
    {
      request: async (archiveId) => {
        await visibility.requestReconcile(archiveId);
        await reconciler.reconcile(archiveId);
      },
    },
    reconciler,
  );

  /** Stores a captured page's WARC, as Capture would; nothing is delivered yet. */
  async function capture(
    archiveId: string,
    path: string,
    response: { body?: string; contentType?: string } = {},
  ): Promise<CapturedPage> {
    const url = `https://example.org/${path}`;
    const warc = await buildWarc([
      {
        url,
        body: response.body ?? `<title>${path}</title><p>${path} text</p>`,
        ...(response.contentType ? { contentType: response.contentType } : {}),
      },
    ]);
    const key = `${archiveId}/${path}.warc.gz`;
    artifacts.put(key, warc);

    const entry: ManifestEntry = {
      snapshotId: `snapshot-${randomUUID()}`,
      urlKey: url,
      url,
      finalUrl: url,
      capturedAt: "2026-11-01T12:00:00Z",
      warcArtifacts: [artifactRefFor(warc, key)],
    };

    return { entry, event: { messageId: randomUUID(), archiveId, ...entry } };
  }

  /** Captures a page and delivers its `PageCaptured` event. */
  async function captureAndDeliver(archiveId: string, path: string): Promise<CapturedPage> {
    const page = await capture(archiveId, path);
    await indexer.handle(page.event);

    return page;
  }

  /** Writes the final manifest to the object store and returns its reference. */
  function storeManifest(
    archiveId: string,
    pages: CapturedPage[],
    manifestArchiveId = archiveId,
    collectionId?: string,
  ): ArtifactRef {
    const manifest = {
      schemaVersion: 1,
      archiveId: manifestArchiveId,
      ...(collectionId !== undefined ? { collectionId } : {}),
      normalizerVersion: "1",
      seedUrl: "https://example.org/",
      createdAt: "2026-11-01T12:10:00Z",
      snapshots: pages.map((page) => page.entry),
      failedPages: [],
    };
    const bytes = new TextEncoder().encode(JSON.stringify(manifest));
    const key = `${archiveId}/manifest-${randomUUID()}.json`;
    artifacts.put(key, bytes);

    return artifactRefFor(bytes, key);
  }

  /** Delivers `CrawlCompleted` with a manifest listing `pages`. */
  async function completeCrawl(archiveId: string, pages: CapturedPage[], digest = "sha256:manifest-1") {
    return publication.crawlCompleted(archiveId, storeManifest(archiveId, pages), digest);
  }

  /** Delivers the Coordinator's decision and Capture's replay acknowledgment. */
  async function publish(archiveId: string, fact: PublicationFact = PACKAGE): Promise<void> {
    await publication.publicationDecided(archiveId, fact);
    await publication.archivePublished(archiveId, fact);
  }

  /** Moves time forward and runs one dispatch pass, as the periodic dispatcher would. */
  async function advance(ms: number): Promise<number> {
    now += ms;

    return dispatcher.dispatchPending();
  }

  return {
    ledger,
    outbox,
    dispatcher,
    advance,
    artifacts,
    index,
    visibility,
    events,
    indexer,
    reconciler,
    publication,
    capture,
    captureAndDeliver,
    storeManifest,
    completeCrawl,
    publish,
  };
}
