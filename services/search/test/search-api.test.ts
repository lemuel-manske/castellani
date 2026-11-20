import { describe, expect, test } from "vitest";

import { get, startServer, StubSearcher } from "./support/http.js";

const RESULT = {
  archiveId: "archive-1",
  snapshotId: "snapshot-1",
  url: "https://example.org/history",
  capturedAt: "2026-11-01T12:00:00.000Z",
  title: "Harbour history",
  snippet: "Fishing boats & ferries left at dawn.",
  score: 1.5,
};

describe("GET /search", () => {
  test("returns matching snapshots and the next page cursor", async () => {
    const searcher = new StubSearcher();
    searcher.page = { results: [RESULT], nextCursor: "next-page" };
    const server = startServer(searcher);

    const response = await get(server, "/search?q=harbour");

    expect(response.status).toBe(200);
    expect(response.json()).toEqual({ results: [RESULT], nextCursor: "next-page" });
  });

  test("passes filters and pagination through to the search backend", async () => {
    const searcher = new StubSearcher();
    const server = startServer(searcher);

    await get(
      server,
      "/search?q=harbour&archiveId=archive-1&snapshotId=snapshot-1&collectionId=c-1" +
        "&capturedFrom=2026-01-01T00:00:00Z&capturedTo=2026-12-31T23:59:59Z&limit=10&cursor=abc",
    );

    expect(searcher.queries).toEqual([
      {
        text: "harbour",
        archiveId: "archive-1",
        snapshotId: "snapshot-1",
        collectionId: "c-1",
        capturedFrom: "2026-01-01T00:00:00Z",
        capturedTo: "2026-12-31T23:59:59Z",
        limit: 10,
        cursor: "abc",
      },
    ]);
  });

  test("uses a default page size of 25", async () => {
    const searcher = new StubSearcher();
    const server = startServer(searcher);

    await get(server, "/search?q=harbour");

    expect(searcher.queries[0]?.limit).toBe(25);
  });

  test("rejects a request without a query as a problem response", async () => {
    const server = startServer(new StubSearcher());

    const response = await get(server, "/search");

    expect(response.status).toBe(400);
    expect(response.mediaType).toBe("application/problem+json");
    expect(response.json()).toMatchObject({
      type: "urn:distributed-web-archive:problem:invalid-search",
      title: "Invalid Search",
      status: 400,
      instance: "/search",
    });
  });

  test("rejects an unknown parameter", async () => {
    const searcher = new StubSearcher();
    const server = startServer(searcher);

    const response = await get(server, "/search?q=harbour&sort=date");

    expect(response.status).toBe(400);
    expect(searcher.queries).toHaveLength(0);
  });

  test("rejects a repeated parameter", async () => {
    const server = startServer(new StubSearcher());

    const response = await get(server, "/search?q=harbour&archiveId=a&archiveId=b");

    expect(response.status).toBe(400);
  });

  test("rejects a page size above 100", async () => {
    const server = startServer(new StubSearcher());

    const response = await get(server, "/search?q=harbour&limit=101");

    expect(response.status).toBe(400);
  });

  test("rejects a capture time range that ends before it starts", async () => {
    const server = startServer(new StubSearcher());

    const response = await get(
      server,
      "/search?q=harbour&capturedFrom=2026-12-01T00:00:00Z&capturedTo=2026-01-01T00:00:00Z",
    );

    expect(response.status).toBe(400);
  });

  test("rejects a capture time that is not an RFC 3339 date-time", async () => {
    const server = startServer(new StubSearcher());

    const response = await get(server, "/search?q=harbour&capturedFrom=yesterday");

    expect(response.status).toBe(400);
  });

  test("reports an unavailable search index as 503 without leaking internals", async () => {
    const searcher = new StubSearcher();
    searcher.unavailable = true;
    const server = startServer(searcher);

    const response = await get(server, "/search?q=harbour");

    expect(response.status).toBe(503);
    expect(response.json()).toMatchObject({
      type: "urn:distributed-web-archive:problem:search-unavailable",
      status: 503,
    });
    expect(response.text).not.toContain("ECONNREFUSED");
  });
});

describe("health", () => {
  test("liveness succeeds while the service is running", async () => {
    const server = startServer(new StubSearcher(), false);

    const response = await get(server, "/health/live");

    expect(response.status).toBe(200);
    expect(response.text).toBe("ok\n");
  });

  test("readiness fails until the index and broker are ready", async () => {
    const server = startServer(new StubSearcher(), false);

    const response = await get(server, "/health/ready");

    expect(response.status).toBe(503);
  });

  test("readiness succeeds once the index and broker are ready", async () => {
    const server = startServer(new StubSearcher(), true);

    const response = await get(server, "/health/ready");

    expect(response.status).toBe(200);
  });
});
