import { describe, expect, test } from "vitest";

import { RejectedEventError } from "../src/indexing/indexer.js";
import { RepairSweep } from "../src/reconciliation/reconciler.js";
import { PACKAGE, searchService } from "./support/archive.js";
import { MemoryVisibility } from "./support/doubles.js";

describe("manifest reconciliation", () => {
  test("a manifest snapshot whose PageCaptured was lost is indexed from the manifest", async () => {
    const service = searchService();
    const delivered = await service.captureAndDeliver("archive-1", "delivered");
    const lost = await service.capture("archive-1", "lost");

    await service.completeCrawl("archive-1", [delivered, lost]);

    expect(service.ledger.statusOf(lost.event)).toBe("INDEXED");
    expect(service.index.document(lost.entry.snapshotId)?.title).toBe("lost");
  });

  test("indexing completion reports the outcome of every manifest snapshot", async () => {
    const service = searchService();
    const indexed = await service.captureAndDeliver("archive-1", "page");
    const unsupported = await service.capture("archive-1", "data", { body: "{}", contentType: "application/json" });

    await service.completeCrawl("archive-1", [indexed, unsupported], "sha256:manifest-1");

    expect(service.events.ofType("SearchIndexingCompleted")).toEqual([
      expect.objectContaining({
        messageId: "SearchIndexingCompleted:archive-1:sha256:manifest-1",
        correlationId: "archive-1",
        payload: {
          archiveId: "archive-1",
          manifestDigest: "sha256:manifest-1",
          expected: 2,
          indexed: 1,
          failed: 0,
          unsupported: 1,
        },
      }),
    ]);
  });

  test("indexing completion is not reported while a manifest snapshot is still being indexed", async () => {
    const service = searchService();
    const done = await service.captureAndDeliver("archive-1", "done");
    const inFlight = await service.capture("archive-1", "in-flight");
    service.ledger.holdByAnotherWorker(inFlight.event);

    await service.completeCrawl("archive-1", [done, inFlight]);

    expect(service.events.ofType("SearchIndexingCompleted")).toEqual([]);
    expect(service.visibility.isPending("archive-1")).toBe(true);
  });

  test("a pending reconciliation completes once the in-flight snapshot is released", async () => {
    const service = searchService();
    const inFlight = await service.capture("archive-1", "in-flight");
    service.ledger.holdByAnotherWorker(inFlight.event);
    await service.completeCrawl("archive-1", [inFlight]);

    service.ledger.finishByAnotherWorker(inFlight.event);
    const result = await service.reconciler.reconcile("archive-1");

    expect(result).toBe("complete");
    expect(service.events.ofType("SearchIndexingCompleted")).toHaveLength(1);
    expect(service.visibility.isPending("archive-1")).toBe(false);
  });

  test("repeated reconciliation reports indexing completion once", async () => {
    const service = searchService();
    const page = await service.captureAndDeliver("archive-1", "page");
    await service.completeCrawl("archive-1", [page]);

    await service.reconciler.reconcile("archive-1");
    await service.reconciler.reconcile("archive-1");

    expect(service.events.ofType("SearchIndexingCompleted")).toHaveLength(1);
  });

  test("an unroutable completion report stays in the outbox and is delivered on a later dispatch", async () => {
    const service = searchService();
    const page = await service.captureAndDeliver("archive-1", "page");
    service.events.unroutable = true;

    await service.completeCrawl("archive-1", [page], "sha256:manifest-1");

    expect(service.events.ofType("SearchIndexingCompleted")).toEqual([]);
    expect(service.outbox.unsent()).toEqual(["SearchIndexingCompleted:archive-1:sha256:manifest-1"]);

    service.events.unroutable = false;
    await service.advance(60_000);

    expect(service.events.ofType("SearchIndexingCompleted")).toHaveLength(1);
    expect(service.outbox.unsent()).toEqual([]);
  });

  test("a failed dispatch is not retried before its backoff elapses", async () => {
    const service = searchService();
    const page = await service.captureAndDeliver("archive-1", "page");
    service.events.unroutable = true;
    await service.completeCrawl("archive-1", [page]);
    service.events.unroutable = false;

    expect(await service.advance(0)).toBe(0);
    expect(await service.advance(2_001)).toBe(1);
  });

  test("an outbox record claimed by another dispatcher is not published twice", async () => {
    const service = searchService();
    const page = await service.captureAndDeliver("archive-1", "page");
    service.events.unroutable = true;
    await service.completeCrawl("archive-1", [page], "sha256:manifest-1");
    service.events.unroutable = false;
    service.outbox.holdByAnotherDispatcher("SearchIndexingCompleted:archive-1:sha256:manifest-1", new Date());

    await service.dispatcher.dispatchPending();

    expect(service.events.ofType("SearchIndexingCompleted")).toEqual([]);
  });

  test("a CrawlCompleted with a different manifest for the same archive is rejected", async () => {
    const service = searchService();
    const page = await service.captureAndDeliver("archive-1", "page");
    await service.completeCrawl("archive-1", [page], "sha256:manifest-1");

    await expect(service.completeCrawl("archive-1", [page], "sha256:manifest-2")).rejects.toBeInstanceOf(
      RejectedEventError,
    );
  });

  test("a manifest whose bytes fail digest verification is rejected", async () => {
    const service = searchService();
    const page = await service.captureAndDeliver("archive-1", "page");
    const ref = service.storeManifest("archive-1", [page]);

    await expect(
      service.publication.crawlCompleted("archive-1", { ...ref, sha256: "0".repeat(64) }, "sha256:m"),
    ).rejects.toBeInstanceOf(RejectedEventError);
  });

  test("a manifest belonging to another archive is rejected", async () => {
    const service = searchService();
    const page = await service.captureAndDeliver("archive-1", "page");
    const ref = service.storeManifest("archive-1", [page], "archive-2");

    await expect(service.publication.crawlCompleted("archive-1", ref, "sha256:m")).rejects.toBeInstanceOf(
      RejectedEventError,
    );
  });
});

describe("search readiness", () => {
  test("SearchReady is reported once indexing is complete and the archive is published", async () => {
    const service = searchService();
    const page = await service.captureAndDeliver("archive-1", "page");
    await service.completeCrawl("archive-1", [page], "sha256:manifest-1");

    await service.publish("archive-1", { decisionVersion: 2, packageDigest: "sha256:p" });

    expect(service.events.ofType("SearchReady")).toEqual([
      expect.objectContaining({
        messageId: "SearchReady:archive-1:2",
        correlationId: "archive-1",
        payload: { archiveId: "archive-1", decisionVersion: 2, manifestDigest: "sha256:manifest-1" },
      }),
    ]);
  });

  test("SearchReady is not reported before the archive is published", async () => {
    const service = searchService();
    const page = await service.captureAndDeliver("archive-1", "page");

    await service.completeCrawl("archive-1", [page]);
    await service.publication.publicationDecided("archive-1", PACKAGE);

    expect(service.events.ofType("SearchReady")).toEqual([]);
  });

  test("SearchReady is not reported while manifest snapshots are still being indexed", async () => {
    const service = searchService();
    const inFlight = await service.capture("archive-1", "in-flight");
    service.ledger.holdByAnotherWorker(inFlight.event);
    await service.completeCrawl("archive-1", [inFlight]);

    await service.publish("archive-1");

    expect(service.events.ofType("SearchReady")).toEqual([]);
  });

  test("a compensated archive reports neither completion nor readiness", async () => {
    const service = searchService();
    const page = await service.captureAndDeliver("archive-1", "page");
    await service.publication.compensationDecided("archive-1", 3);

    await service.completeCrawl("archive-1", [page]);

    expect(service.events.ofType("SearchIndexingCompleted")).toEqual([]);
    expect(service.events.ofType("SearchReady")).toEqual([]);
    expect(service.index.documents.size).toBe(0);
  });
});

describe("collections", () => {
  test("revealed snapshots carry the collection of their manifest", async () => {
    const service = searchService();
    const page = await service.captureAndDeliver("archive-1", "page");
    const ref = service.storeManifest("archive-1", [page], "archive-1", "collection-7");
    await service.publication.crawlCompleted("archive-1", ref, "sha256:manifest-1");

    await service.publish("archive-1");

    expect(service.index.document(page.entry.snapshotId)).toMatchObject({
      collectionId: "collection-7",
      visible: true,
    });
  });
});

describe("ledger and index divergence repair", () => {
  test("an indexed snapshot whose document was lost from the index is reindexed and stays searchable", async () => {
    const service = searchService();
    const page = await service.captureAndDeliver("archive-1", "page");
    await service.completeCrawl("archive-1", [page]);
    await service.publish("archive-1");
    service.index.lose("archive-1", page.entry.snapshotId);

    await service.reconciler.reconcile("archive-1");

    expect(service.index.searchable()).toEqual([page.entry.snapshotId]);
    expect(service.ledger.statusOf(page.event)).toBe("INDEXED");
  });

  test("a repaired archive does not report indexing completion or readiness again", async () => {
    const service = searchService();
    const page = await service.captureAndDeliver("archive-1", "page");
    await service.completeCrawl("archive-1", [page]);
    await service.publish("archive-1");
    service.index.lose("archive-1", page.entry.snapshotId);

    await service.reconciler.reconcile("archive-1");

    expect(service.events.ofType("SearchIndexingCompleted")).toHaveLength(1);
    expect(service.events.ofType("SearchReady")).toHaveLength(1);
  });

  test("an unavailable index leaves the reconciliation pending without reopening any snapshot", async () => {
    const service = searchService();
    const page = await service.captureAndDeliver("archive-1", "page");
    await service.completeCrawl("archive-1", [page]);
    await service.visibility.requestReconcile("archive-1");
    service.index.offline = true;

    await expect(service.reconciler.reconcile("archive-1")).rejects.toThrow("ECONNREFUSED");

    expect(service.ledger.statusOf(page.event)).toBe("INDEXED");
    expect(service.visibility.isPending("archive-1")).toBe(true);
  });

  test("the repair sweep requests reconciliation of every archive with a manifest, across pages", async () => {
    const visibility = new MemoryVisibility();
    const ref = { bucket: "b", key: "k", sha256: "0".repeat(64), sizeBytes: 1 };

    for (let n = 0; n < 150; n += 1) {
      await visibility.recordManifest(`archive-${String(n)}`, { digest: "sha256:m", ref, expected: 1 });
    }
    await visibility.recordDecision("archive-without-manifest", PACKAGE);
    const requested: string[] = [];
    const sweep = new RepairSweep(
      visibility,
      (archiveId) => {
        requested.push(archiveId);

        return Promise.resolve();
      },
      60_000,
      { warn: () => undefined },
    );

    expect(await sweep.sweep()).toBe(150);
    expect(new Set(requested).size).toBe(150);
    expect(requested).not.toContain("archive-without-manifest");
  });
});
