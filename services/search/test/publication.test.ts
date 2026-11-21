import { describe, expect, test } from "vitest";

import { RejectedEventError } from "../src/indexing/indexer.js";
import { PACKAGE, searchService } from "./support/archive.js";

describe("search visibility", () => {
  test("an indexed snapshot is not searchable before its archive is published", async () => {
    const service = searchService();
    const page = await service.captureAndDeliver("archive-1", "page");

    await service.completeCrawl("archive-1", [page]);

    expect(service.index.document(page.entry.snapshotId)).toBeDefined();
    expect(service.index.searchable()).toEqual([]);
  });

  test("a publication decision alone does not make results searchable", async () => {
    const service = searchService();
    const page = await service.captureAndDeliver("archive-1", "page");
    await service.completeCrawl("archive-1", [page]);

    const result = await service.publication.publicationDecided("archive-1", PACKAGE);

    expect(result).toBe("pending");
    expect(service.index.searchable()).toEqual([]);
  });

  test("manifest snapshots become searchable once the decision and the replay acknowledgment match", async () => {
    const service = searchService();
    const page = await service.captureAndDeliver("archive-1", "page");
    await service.completeCrawl("archive-1", [page]);
    await service.publication.publicationDecided("archive-1", PACKAGE);

    const result = await service.publication.archivePublished("archive-1", PACKAGE);

    expect(result).toBe("visible");
    expect(service.index.searchable()).toEqual([page.entry.snapshotId]);
  });

  test("a replay acknowledgment delivered before the decision is honored once the decision arrives", async () => {
    const service = searchService();
    const page = await service.captureAndDeliver("archive-1", "page");
    await service.completeCrawl("archive-1", [page]);

    await service.publication.archivePublished("archive-1", PACKAGE);
    expect(service.index.searchable()).toEqual([]);

    await service.publication.publicationDecided("archive-1", PACKAGE);

    expect(service.index.searchable()).toEqual([page.entry.snapshotId]);
  });

  test("publication facts that arrive before the manifest take effect once it is recorded", async () => {
    const service = searchService();
    const page = await service.captureAndDeliver("archive-1", "page");
    await service.publish("archive-1");
    expect(service.index.searchable()).toEqual([]);

    await service.completeCrawl("archive-1", [page]);

    expect(service.index.searchable()).toEqual([page.entry.snapshotId]);
  });

  test("a captured snapshot missing from the manifest is never searchable", async () => {
    const service = searchService();
    const authorized = await service.captureAndDeliver("archive-1", "authorized");
    const stale = await service.captureAndDeliver("archive-1", "stale-attempt");
    await service.completeCrawl("archive-1", [authorized]);

    await service.publish("archive-1");

    expect(service.index.document(stale.entry.snapshotId)).toBeDefined();
    expect(service.index.searchable()).toEqual([authorized.entry.snapshotId]);
  });

  test("a replay acknowledgment for a different package keeps results hidden", async () => {
    const service = searchService();
    const page = await service.captureAndDeliver("archive-1", "page");
    await service.completeCrawl("archive-1", [page]);
    await service.publication.publicationDecided("archive-1", PACKAGE);

    const result = await service.publication.archivePublished("archive-1", {
      ...PACKAGE,
      packageDigest: "sha256:other",
    });

    expect(result).toBe("pending");
    expect(service.index.searchable()).toEqual([]);
  });

  test("publishing one archive does not reveal another archive's snapshots", async () => {
    const service = searchService();
    const published = await service.captureAndDeliver("archive-1", "page");
    const other = await service.captureAndDeliver("archive-2", "page");
    await service.completeCrawl("archive-1", [published]);
    await service.completeCrawl("archive-2", [other]);

    await service.publish("archive-1");

    expect(service.index.searchable()).toEqual([published.entry.snapshotId]);
  });

  test("re-indexing a revealed snapshot keeps it searchable", async () => {
    const service = searchService();
    const page = await service.captureAndDeliver("archive-1", "page");
    await service.completeCrawl("archive-1", [page]);
    await service.publish("archive-1");

    await service.index.put({ ...page.entry, archiveId: "archive-1", content: "re-indexed", indexedAt: "now" });

    expect(service.index.searchable()).toEqual([page.entry.snapshotId]);
  });

  test("a second, different publication decision for the same archive is rejected", async () => {
    const service = searchService();
    await service.publication.publicationDecided("archive-1", PACKAGE);

    await expect(
      service.publication.publicationDecided("archive-1", { decisionVersion: 2, packageDigest: "sha256:package-2" }),
    ).rejects.toBeInstanceOf(RejectedEventError);
  });
});

describe("compensation", () => {
  test("compensation removes the archive's documents and acknowledges with SearchCompensated", async () => {
    const service = searchService();
    await service.captureAndDeliver("archive-1", "one");
    await service.captureAndDeliver("archive-1", "two");

    const result = await service.publication.compensationDecided("archive-1", 3);

    expect(result).toBe("compensated");
    expect(service.index.documents.size).toBe(0);
    expect(service.events.ofType("SearchCompensated")).toEqual([
      expect.objectContaining({
        messageId: "SearchCompensated:archive-1:3",
        correlationId: "archive-1",
        version: 1,
        payload: { archiveId: "archive-1", decisionVersion: 3 },
      }),
    ]);
  });

  test("a redelivered compensation command repeats the cleanup but acknowledges once", async () => {
    const service = searchService();
    await service.publication.compensationDecided("archive-1", 3);

    await service.publication.compensationDecided("archive-1", 3);

    expect(service.events.ofType("SearchCompensated").map((event) => event.messageId)).toEqual([
      "SearchCompensated:archive-1:3",
    ]);
  });

  test("an acknowledgment no queue accepts stays in the outbox and is delivered once a queue is bound", async () => {
    const service = searchService();
    service.events.unroutable = true;

    await service.publication.compensationDecided("archive-1", 3);

    expect(service.events.ofType("SearchCompensated")).toEqual([]);
    expect(service.outbox.unsent()).toEqual(["SearchCompensated:archive-1:3"]);

    service.events.unroutable = false;
    await service.advance(60_000);

    expect(service.events.ofType("SearchCompensated")).toHaveLength(1);
  });

  test("a page captured after compensation is never indexed", async () => {
    const service = searchService();
    await service.publication.compensationDecided("archive-1", 3);

    await service.captureAndDeliver("archive-1", "late");

    expect(service.index.documents.size).toBe(0);
  });

  test("compensation does not touch other archives", async () => {
    const service = searchService();
    const kept = await service.captureAndDeliver("archive-2", "page");

    await service.publication.compensationDecided("archive-1", 3);

    expect(service.index.snapshotIds()).toEqual([kept.entry.snapshotId]);
  });

  test("compensation after an irreversible publication decision is rejected and results stay searchable", async () => {
    const service = searchService();
    const page = await service.captureAndDeliver("archive-1", "page");
    await service.completeCrawl("archive-1", [page]);
    await service.publish("archive-1");

    await expect(service.publication.compensationDecided("archive-1", 2)).rejects.toBeInstanceOf(RejectedEventError);

    expect(service.index.searchable()).toEqual([page.entry.snapshotId]);
    expect(service.events.ofType("SearchCompensated")).toEqual([]);
  });

  test("a publication decision after compensation is rejected", async () => {
    const service = searchService();
    await service.publication.compensationDecided("archive-1", 3);

    await expect(service.publication.publicationDecided("archive-1", PACKAGE)).rejects.toBeInstanceOf(
      RejectedEventError,
    );
  });
});
