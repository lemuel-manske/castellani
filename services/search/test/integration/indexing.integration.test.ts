import { randomUUID } from "node:crypto";

import { describe, expect, test } from "vitest";

import { pageCapturedMessage } from "../support/events.js";
import {
  PACKAGE,
  type SnapshotEntry,
  archiveEvent,
  completeCrawl,
  deadLettered,
  inboxRecord,
  ledgerReaches,
  observe,
  outboxRecord,
  publish,
  publishArchive,
  publishRaw,
  search,
  searchUntil,
  storeCapturedPage,
} from "../support/stack.js";

function page(title: string, text: string): string {
  return `<html><head><title>${title}</title></head><body><p>${text}</p></body></html>`;
}

/** Stores a captured page of `archiveId` containing `word`, without delivering it. */
async function captured(archiveId: string, word: string, path = "page"): Promise<SnapshotEntry> {
  const url = `https://example.org/${path}`;
  const ref = await storeCapturedPage(url, page(path, `The ${word} at dawn`));
  const { payload } = pageCapturedMessage({ archiveId, url, warcArtifacts: [ref] });

  return payload as SnapshotEntry;
}

/** Stores a captured page and publishes its `PageCaptured` event. */
async function capturePage(archiveId: string, word: string, path = "page"): Promise<SnapshotEntry> {
  const entry = await captured(archiveId, word, path);
  await publish(pageCapturedMessage({ archiveId, ...entry }));

  return entry;
}

/** Runs a whole archive through crawl completion and publication. */
async function archiveAndPublish(archiveId: string, entries: SnapshotEntry[]): Promise<void> {
  await completeCrawl(archiveId, entries);
  await publishArchive(archiveId);
}

function unique(prefix: string): string {
  return `${prefix}${randomUUID().slice(0, 8)}`;
}

function newArchive(): string {
  return `archive-${randomUUID()}`;
}

describe("indexing through the running stack", () => {
  test("a captured page of a published archive becomes searchable", async () => {
    const archiveId = newArchive();
    const word = unique("harbour");
    const entry = await capturePage(archiveId, word, "harbour");

    await archiveAndPublish(archiveId, [entry]);

    const response = await searchUntil({ q: word }, (r) => r.body.results.length > 0);
    expect(response.body.results).toEqual([
      expect.objectContaining({
        archiveId,
        snapshotId: entry.snapshotId,
        url: "https://example.org/harbour",
        capturedAt: "2026-11-01T12:00:00.000Z",
        title: "harbour",
        snippet: `The ${word} at dawn`,
      }),
    ]);
  });

  test("redelivering the same snapshot does not create a duplicate result", async () => {
    const archiveId = newArchive();
    const word = unique("lighthouse");
    const entry = await captured(archiveId, word);
    const message = pageCapturedMessage({ archiveId, ...entry });
    await publish(message);
    await archiveAndPublish(archiveId, [entry]);
    await searchUntil({ q: word }, (r) => r.body.results.length > 0);

    await publish({ ...message, messageId: randomUUID() });
    await publish(message);
    await ledgerReaches({ archiveId, snapshotId: entry.snapshotId }, "INDEXED");

    const response = await search({ q: word });
    expect(response.body.results).toHaveLength(1);
    // The original delivery is recorded in the inbox after its effect, with
    // an expiry for TTL cleanup.
    const record = await inboxRecord(String(message.messageId));
    expect(record?.expiresAt).toBeGreaterThan(Date.now() / 1_000);
  });

  test("results page through an archive with a cursor without repeating snapshots", async () => {
    const archiveId = newArchive();
    const word = unique("ferry");
    const entries: SnapshotEntry[] = [];

    for (const path of ["one", "two", "three"]) {
      entries.push(await capturePage(archiveId, word, path));
    }
    await archiveAndPublish(archiveId, entries);
    await searchUntil({ q: word, archiveId }, (r) => r.body.results.length === 3);

    const first = await search({ q: word, archiveId, limit: "2" });
    const cursor = first.body.nextCursor;
    expect(cursor).toEqual(expect.any(String));
    const second = await search({ q: word, archiveId, limit: "2", cursor: cursor ?? "" });

    const seen = [...first.body.results, ...second.body.results].map((r) => r.snapshotId);
    expect(first.body.results).toHaveLength(2);
    expect(second.body.results).toHaveLength(1);
    expect(second.body.nextCursor).toBeNull();
    expect(new Set(seen).size).toBe(3);
  });

  test("an archive filter excludes snapshots from other archives", async () => {
    const archiveId = newArchive();
    const word = unique("quay");
    await archiveAndPublish(archiveId, [await capturePage(archiveId, word)]);
    await searchUntil({ q: word }, (r) => r.body.results.length > 0);

    const response = await search({ q: word, archiveId: newArchive() });

    expect(response.status).toBe(200);
    expect(response.body.results).toHaveLength(0);
  });
});

describe("publication visibility through the running stack", () => {
  test("indexed snapshots stay hidden until the archive is published", async () => {
    const archiveId = newArchive();
    const word = unique("staged");
    const entry = await capturePage(archiveId, word);
    await completeCrawl(archiveId, [entry]);
    await ledgerReaches({ archiveId, snapshotId: entry.snapshotId }, "INDEXED");

    await publish(archiveEvent("ArchivePublicationDecided", archiveId, PACKAGE));
    const hidden = await search({ q: word });

    expect(hidden.body.results).toHaveLength(0);

    await publish(archiveEvent("ArchivePublished", archiveId, PACKAGE));
    const visible = await searchUntil({ q: word }, (r) => r.body.results.length > 0);

    expect(visible.body.results).toHaveLength(1);
  });

  test("a replay acknowledgment delivered before the decision still publishes the archive", async () => {
    const archiveId = newArchive();
    const word = unique("reversed");
    await completeCrawl(archiveId, [await capturePage(archiveId, word)]);

    await publish(archiveEvent("ArchivePublished", archiveId, PACKAGE));
    await publish(archiveEvent("ArchivePublicationDecided", archiveId, PACKAGE));

    const response = await searchUntil({ q: word }, (r) => r.body.results.length > 0);
    expect(response.body.results).toEqual([expect.objectContaining({ archiveId })]);
  });

  test("a captured snapshot missing from the manifest stays hidden after publication", async () => {
    const archiveId = newArchive();
    const word = unique("stray");
    const authorized = await capturePage(archiveId, word, "authorized");
    const stray = await capturePage(archiveId, word, "stray");
    await ledgerReaches({ archiveId, snapshotId: stray.snapshotId }, "INDEXED");

    await archiveAndPublish(archiveId, [authorized]);

    const response = await searchUntil({ q: word }, (r) => r.body.results.length > 0);
    expect(response.body.results.map((r) => r.snapshotId)).toEqual([authorized.snapshotId]);
  });

  test("a compensated archive is never searchable and Search acknowledges the cleanup", async () => {
    const archiveId = newArchive();
    const word = unique("aborted");
    const entry = await capturePage(archiveId, word);
    await ledgerReaches({ archiveId, snapshotId: entry.snapshotId }, "INDEXED");
    const acknowledgments = await observe("SearchCompensated");

    await publish(
      archiveEvent("ArchiveCompensationDecided", archiveId, { decisionVersion: 4, reasonCode: "SEED_FAILED" }),
    );

    const acknowledgment = await acknowledgments.next();
    // Emitted through the outbox, which records the broker's confirm.
    await expect.poll(async () => (await outboxRecord(`SearchCompensated:${archiveId}:4`))?.state).toBe("SENT");
    expect(acknowledgment).toMatchObject({
      messageId: `SearchCompensated:${archiveId}:4`,
      correlationId: archiveId,
      type: "SearchCompensated",
      payload: { archiveId, decisionVersion: 4 },
    });

    // Publication facts after compensation are rejected, so even both of
    // them cannot resurrect the archive.
    const [decided, published] = await publishArchive(archiveId);

    expect(await deadLettered(decided ?? "")).toBe(true);
    expect(await deadLettered(published ?? "")).toBe(true);
    const response = await search({ q: word });
    expect(response.body.results).toHaveLength(0);
  });
});

describe("manifest reconciliation through the running stack", () => {
  test("a lost PageCaptured is recovered from the manifest and indexing completion is reported", async () => {
    const archiveId = newArchive();
    const word = unique("recovered");
    const delivered = await capturePage(archiveId, word, "delivered");
    const lost = await captured(archiveId, word, "lost");
    const completions = await observe("SearchIndexingCompleted");

    const digest = await completeCrawl(archiveId, [delivered, lost]);

    const completion = await completions.next();
    expect(completion).toMatchObject({
      messageId: `SearchIndexingCompleted:${archiveId}:${digest}`,
      correlationId: archiveId,
      payload: { archiveId, manifestDigest: digest, expected: 2, indexed: 2, failed: 0, unsupported: 0 },
    });
    await ledgerReaches({ archiveId, snapshotId: lost.snapshotId }, "INDEXED");
  });

  test("SearchReady is reported once the indexed archive is published, and results are searchable", async () => {
    const archiveId = newArchive();
    const word = unique("ready");
    const entry = await capturePage(archiveId, word);
    const digest = await completeCrawl(archiveId, [entry]);
    await ledgerReaches({ archiveId, snapshotId: entry.snapshotId }, "INDEXED");
    const readiness = await observe("SearchReady");

    await publishArchive(archiveId);

    const ready = await readiness.next();
    expect(ready).toMatchObject({
      messageId: `SearchReady:${archiveId}:${PACKAGE.decisionVersion}`,
      payload: { archiveId, decisionVersion: PACKAGE.decisionVersion, manifestDigest: digest },
    });
    // SearchReady promises searchable visibility: no polling needed.
    const response = await search({ q: word });
    expect(response.body.results.map((r) => r.snapshotId)).toEqual([entry.snapshotId]);
  });
});

describe("rejected messages", () => {
  test("a message violating the PageCaptured contract is dead-lettered", async () => {
    const message = { ...pageCapturedMessage({ warcArtifacts: [] }), messageId: randomUUID() };

    await publish(message);

    expect(await deadLettered(message.messageId)).toBe(true);
  });

  test("a message that is not JSON is dead-lettered", async () => {
    const messageId = randomUUID();

    await publishRaw("PageCaptured", "not json", messageId);

    expect(await deadLettered(messageId)).toBe(true);
  });
});
