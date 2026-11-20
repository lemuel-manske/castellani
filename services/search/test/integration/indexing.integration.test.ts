import { randomUUID } from "node:crypto";

import { describe, expect, test } from "vitest";

import { pageCapturedMessage } from "../support/events.js";
import {
  PACKAGE,
  archiveEvent,
  deadLettered,
  ledgerReaches,
  observe,
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

/** Captures one page of `archiveId` containing `word` and publishes PageCaptured. */
async function capturePage(archiveId: string, word: string, path = "page") {
  const url = `https://example.org/${path}`;
  const ref = await storeCapturedPage(url, page(path, `The ${word} at dawn`));
  const message = pageCapturedMessage({ archiveId, url, warcArtifacts: [ref] });

  await publish(message);

  return message.payload as Record<string, string>;
}

function unique(prefix: string): string {
  return `${prefix}${randomUUID().slice(0, 8)}`;
}

describe("indexing through the running stack", () => {
  test("a captured page of a published archive becomes searchable", async () => {
    const archiveId = `archive-${randomUUID()}`;
    const word = unique("harbour");
    const captured = await capturePage(archiveId, word, "harbour");

    await publishArchive(archiveId);

    const response = await searchUntil({ q: word }, (r) => r.body.results.length > 0);
    expect(response.body.results).toEqual([
      expect.objectContaining({
        archiveId,
        snapshotId: captured.snapshotId,
        url: "https://example.org/harbour",
        capturedAt: "2026-11-01T12:00:00.000Z",
        title: "harbour",
        snippet: `The ${word} at dawn`,
      }),
    ]);
  });

  test("redelivering the same snapshot does not create a duplicate result", async () => {
    const archiveId = `archive-${randomUUID()}`;
    const word = unique("lighthouse");
    const ref = await storeCapturedPage("https://example.org/light", page("Lighthouse", word));
    const message = pageCapturedMessage({ archiveId, url: "https://example.org/light", warcArtifacts: [ref] });
    await publish(message);
    await publishArchive(archiveId);
    await searchUntil({ q: word }, (r) => r.body.results.length > 0);

    await publish({ ...message, messageId: randomUUID() });
    await publish(message);

    // Settles on the duplicates being consumed; a duplicate document would
    // appear as a second result for the same unique word.
    const sentinel = unique("sentinel");
    await capturePage(archiveId, sentinel, "sentinel");
    await searchUntil({ q: sentinel }, (r) => r.body.results.length > 0);

    const response = await search({ q: word });
    expect(response.body.results).toHaveLength(1);
  });

  test("results page through an archive with a cursor without repeating snapshots", async () => {
    const archiveId = `archive-${randomUUID()}`;
    const word = unique("ferry");

    for (const path of ["one", "two", "three"]) {
      await capturePage(archiveId, word, path);
    }
    await publishArchive(archiveId);
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
    const archiveId = `archive-${randomUUID()}`;
    const word = unique("quay");
    await capturePage(archiveId, word, "quay");
    await publishArchive(archiveId);
    await searchUntil({ q: word }, (r) => r.body.results.length > 0);

    const response = await search({ q: word, archiveId: `archive-${randomUUID()}` });

    expect(response.status).toBe(200);
    expect(response.body.results).toHaveLength(0);
  });
});

describe("publication visibility through the running stack", () => {
  test("indexed snapshots stay hidden until the archive is published", async () => {
    const archiveId = `archive-${randomUUID()}`;
    const word = unique("staged");
    const captured = await capturePage(archiveId, word);
    await ledgerReaches(captured.snapshotId ?? "", "INDEXED");

    await publish(archiveEvent("ArchivePublicationDecided", archiveId, PACKAGE));
    const hidden = await search({ q: word });

    expect(hidden.body.results).toHaveLength(0);

    await publish(archiveEvent("ArchivePublished", archiveId, PACKAGE));
    const visible = await searchUntil({ q: word }, (r) => r.body.results.length > 0);

    expect(visible.body.results).toHaveLength(1);
  });

  test("a replay acknowledgment delivered before the decision still publishes the archive", async () => {
    const archiveId = `archive-${randomUUID()}`;
    const word = unique("reversed");
    await capturePage(archiveId, word);

    await publish(archiveEvent("ArchivePublished", archiveId, PACKAGE));
    await publish(archiveEvent("ArchivePublicationDecided", archiveId, PACKAGE));

    const response = await searchUntil({ q: word }, (r) => r.body.results.length > 0);
    expect(response.body.results).toEqual([expect.objectContaining({ archiveId })]);
  });

  test("a compensated archive is never searchable and Search acknowledges the cleanup", async () => {
    const archiveId = `archive-${randomUUID()}`;
    const word = unique("aborted");
    const captured = await capturePage(archiveId, word);
    await ledgerReaches(captured.snapshotId ?? "", "INDEXED");
    const acknowledgments = await observe("SearchCompensated");

    await publish(
      archiveEvent("ArchiveCompensationDecided", archiveId, { decisionVersion: 4, reasonCode: "SEED_FAILED" }),
    );

    const acknowledgment = await acknowledgments.next();
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
