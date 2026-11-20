import { randomUUID } from "node:crypto";

import { describe, expect, test } from "vitest";

import { pageCapturedMessage } from "../support/events.js";
import { deadLettered, publish, publishRaw, search, searchUntil, storeCapturedPage } from "../support/stack.js";

function page(title: string, text: string): string {
  return `<html><head><title>${title}</title></head><body><p>${text}</p></body></html>`;
}

describe("indexing through the running stack", () => {
  test("a captured page published to the broker becomes searchable", async () => {
    const word = `harbour${randomUUID().slice(0, 8)}`;
    const ref = await storeCapturedPage("https://example.org/harbour", page("Harbour history", `The ${word} at dawn`));
    const message = pageCapturedMessage({ url: "https://example.org/harbour", warcArtifacts: [ref] });

    await publish(message);

    const response = await searchUntil({ q: word }, (r) => r.body.results.length > 0);
    const payload = message.payload as Record<string, string>;
    expect(response.body.results).toEqual([
      expect.objectContaining({
        archiveId: payload.archiveId,
        snapshotId: payload.snapshotId,
        url: "https://example.org/harbour",
        capturedAt: "2026-11-01T12:00:00.000Z",
        title: "Harbour history",
        snippet: `The ${word} at dawn`,
      }),
    ]);
  });

  test("redelivering the same snapshot does not create a duplicate result", async () => {
    const word = `lighthouse${randomUUID().slice(0, 8)}`;
    const ref = await storeCapturedPage("https://example.org/light", page("Lighthouse", word));
    const message = pageCapturedMessage({ url: "https://example.org/light", warcArtifacts: [ref] });
    await publish(message);
    await searchUntil({ q: word }, (r) => r.body.results.length > 0);

    await publish({ ...message, messageId: randomUUID() });
    await publish(message);

    // Settles on the duplicates being consumed; a duplicate document would
    // appear as a second result for the same unique word.
    const sentinel = `sentinel${randomUUID().slice(0, 8)}`;
    const sentinelRef = await storeCapturedPage("https://example.org/s", page("Sentinel", sentinel));
    await publish(pageCapturedMessage({ url: "https://example.org/s", warcArtifacts: [sentinelRef] }));
    await searchUntil({ q: sentinel }, (r) => r.body.results.length > 0);

    const response = await search({ q: word });
    expect(response.body.results).toHaveLength(1);
  });

  test("results page through an archive with a cursor without repeating snapshots", async () => {
    const archiveId = `archive-${randomUUID()}`;
    const word = `ferry${randomUUID().slice(0, 8)}`;

    for (const path of ["one", "two", "three"]) {
      const url = `https://example.org/${path}`;
      const ref = await storeCapturedPage(url, page(path, `${word} route ${path}`));
      await publish(pageCapturedMessage({ archiveId, url, warcArtifacts: [ref] }));
    }
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
    const word = `quay${randomUUID().slice(0, 8)}`;
    const ref = await storeCapturedPage("https://example.org/quay", page("Quay", word));
    await publish(pageCapturedMessage({ url: "https://example.org/quay", warcArtifacts: [ref] }));
    await searchUntil({ q: word }, (r) => r.body.results.length > 0);

    const response = await search({ q: word, archiveId: `archive-${randomUUID()}` });

    expect(response.status).toBe(200);
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
