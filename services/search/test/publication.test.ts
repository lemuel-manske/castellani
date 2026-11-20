import { describe, expect, test } from "vitest";

import { Indexer, RejectedEventError } from "../src/indexing/indexer.js";
import { PublicationHandler } from "../src/publication/handler.js";
import {
  MemoryArtifacts,
  MemoryLedger,
  MemoryVisibility,
  RecordingIndex,
  RecordingPublisher,
} from "./support/doubles.js";
import { pageCaptured } from "./support/events.js";
import { artifactRefFor, buildWarc } from "./support/warc.js";

const PACKAGE = { decisionVersion: 1, packageDigest: "sha256:package-1" };

function fixture() {
  const artifacts = new MemoryArtifacts();
  const index = new RecordingIndex();
  const visibility = new MemoryVisibility();
  const events = new RecordingPublisher();
  const indexer = new Indexer(new MemoryLedger(), artifacts, index, visibility, { maxDocumentAttempts: 2 });
  const publication = new PublicationHandler(visibility, index, events);

  /** Captures and indexes one page of `archiveId`, returning its snapshot ID. */
  async function capture(archiveId: string, path = "page"): Promise<string> {
    const url = `https://example.org/${path}`;
    const warc = await buildWarc([{ url, body: `<title>${path}</title><p>${path} text</p>` }]);
    artifacts.put(`${archiveId}/${path}`, warc);
    const event = pageCaptured({ archiveId, url, warcArtifacts: [artifactRefFor(warc, `${archiveId}/${path}`)] });

    await indexer.handle(event);

    return event.snapshotId;
  }

  return { index, events, indexer, publication, capture, artifacts };
}

describe("search visibility", () => {
  test("an indexed snapshot is not searchable before its archive is published", async () => {
    const { index, capture } = fixture();

    const snapshotId = await capture("archive-1");

    expect(index.documents.has(snapshotId)).toBe(true);
    expect(index.searchable()).toEqual([]);
  });

  test("a publication decision alone does not make results searchable", async () => {
    const { index, publication, capture } = fixture();
    await capture("archive-1");

    const result = await publication.publicationDecided("archive-1", PACKAGE);

    expect(result).toBe("pending");
    expect(index.searchable()).toEqual([]);
  });

  test("results become searchable once the decision and the replay acknowledgment match", async () => {
    const { index, publication, capture } = fixture();
    const snapshotId = await capture("archive-1");
    await publication.publicationDecided("archive-1", PACKAGE);

    const result = await publication.archivePublished("archive-1", PACKAGE);

    expect(result).toBe("visible");
    expect(index.searchable()).toEqual([snapshotId]);
  });

  test("a replay acknowledgment delivered before the decision is honored once the decision arrives", async () => {
    const { index, publication, capture } = fixture();
    const snapshotId = await capture("archive-1");

    await publication.archivePublished("archive-1", PACKAGE);
    expect(index.searchable()).toEqual([]);

    await publication.publicationDecided("archive-1", PACKAGE);

    expect(index.searchable()).toEqual([snapshotId]);
  });

  test("a replay acknowledgment for a different package keeps results hidden", async () => {
    const { index, publication, capture } = fixture();
    await capture("archive-1");
    await publication.publicationDecided("archive-1", PACKAGE);

    const result = await publication.archivePublished("archive-1", { ...PACKAGE, packageDigest: "sha256:other" });

    expect(result).toBe("pending");
    expect(index.searchable()).toEqual([]);
  });

  test("a page captured after publication is searchable as soon as it is indexed", async () => {
    const { index, publication, capture } = fixture();
    await publication.publicationDecided("archive-1", PACKAGE);
    await publication.archivePublished("archive-1", PACKAGE);

    const snapshotId = await capture("archive-1", "late");

    expect(index.searchable()).toEqual([snapshotId]);
  });

  test("publishing one archive does not reveal another archive's snapshots", async () => {
    const { index, publication, capture } = fixture();
    const published = await capture("archive-1");
    await capture("archive-2");

    await publication.publicationDecided("archive-1", PACKAGE);
    await publication.archivePublished("archive-1", PACKAGE);

    expect(index.searchable()).toEqual([published]);
  });

  test("a second, different publication decision for the same archive is rejected", async () => {
    const { publication } = fixture();
    await publication.publicationDecided("archive-1", PACKAGE);

    await expect(
      publication.publicationDecided("archive-1", { decisionVersion: 2, packageDigest: "sha256:package-2" }),
    ).rejects.toBeInstanceOf(RejectedEventError);
  });
});

describe("compensation", () => {
  test("compensation removes the archive's documents and acknowledges with SearchCompensated", async () => {
    const { index, events, publication, capture } = fixture();
    await capture("archive-1", "one");
    await capture("archive-1", "two");

    const result = await publication.compensationDecided("archive-1", 3);

    expect(result).toBe("compensated");
    expect(index.documents.size).toBe(0);
    expect(events.published).toEqual([
      expect.objectContaining({
        messageId: "SearchCompensated:archive-1:3",
        correlationId: "archive-1",
        type: "SearchCompensated",
        version: 1,
        payload: { archiveId: "archive-1", decisionVersion: 3 },
      }),
    ]);
  });

  test("a redelivered compensation command re-emits the same acknowledgment", async () => {
    const { events, publication } = fixture();
    await publication.compensationDecided("archive-1", 3);

    await publication.compensationDecided("archive-1", 3);

    expect(events.published.map((event) => event.messageId)).toEqual([
      "SearchCompensated:archive-1:3",
      "SearchCompensated:archive-1:3",
    ]);
  });

  test("a page captured after compensation is never indexed", async () => {
    const { index, publication, capture } = fixture();
    await publication.compensationDecided("archive-1", 3);

    await capture("archive-1", "late");

    expect(index.documents.size).toBe(0);
  });

  test("compensation does not touch other archives", async () => {
    const { index, publication, capture } = fixture();
    const kept = await capture("archive-2");

    await publication.compensationDecided("archive-1", 3);

    expect([...index.documents.keys()]).toEqual([kept]);
  });

  test("compensation after an irreversible publication decision is rejected and results stay searchable", async () => {
    const { index, events, publication, capture } = fixture();
    const snapshotId = await capture("archive-1");
    await publication.publicationDecided("archive-1", PACKAGE);
    await publication.archivePublished("archive-1", PACKAGE);

    await expect(publication.compensationDecided("archive-1", 2)).rejects.toBeInstanceOf(RejectedEventError);

    expect(index.searchable()).toEqual([snapshotId]);
    expect(events.published).toEqual([]);
  });

  test("a publication decision after compensation is rejected", async () => {
    const { publication } = fixture();
    await publication.compensationDecided("archive-1", 3);

    await expect(publication.publicationDecided("archive-1", PACKAGE)).rejects.toBeInstanceOf(RejectedEventError);
  });
});
