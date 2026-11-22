import { expect, it, vi } from "vitest";
import { createSearchServer } from "../../src/api/server.js";
import type { PublicationFacts } from "../../src/domain.js";
import type { ManifestLedger } from "../../src/ports/manifest-ledger.js";
import type { PublicationLedger } from "../../src/ports/publication-ledger.js";
import type { SearchDocumentReader } from "../../src/ports/search-reader.js";

const facts: PublicationFacts = {
  publicationDecision: {
    archiveId: "archive-a",
    decisionVersion: 1,
    packageDigest: "sha256:package",
  },
  replayPublication: {
    archiveId: "archive-a",
    decisionVersion: 1,
    packageDigest: "sha256:package",
  },
  compensationDecision: null,
};

it("serves the Gateway search query contract and returns only authorized results", async () => {
  const reader: SearchDocumentReader = {
    search: vi.fn().mockResolvedValue({
      candidates: [
        {
          document: {
            archiveId: "archive-a",
            snapshotId: "snapshot-a",
            url: "https://example.com",
            finalUrl: "https://example.com",
            capturedAt: "2026-11-22T10:00:00.000Z",
            contentType: "text/html",
            title: "Example",
            description: "",
            language: "en",
            text: "searchable content",
          },
          score: 1,
          snippet: "searchable content",
          cursor: "Y3Vyc29y",
        },
      ],
      nextCursor: null,
    }),
  };
  const publicationLedger: PublicationLedger = {
    get: vi.fn().mockResolvedValue(facts),
    recordPublicationDecision: vi.fn(),
    recordReplayPublished: vi.fn(),
    recordCompensationDecision: vi.fn(),
  };
  const contains = vi.fn().mockResolvedValue(true);
  const manifestLedger: ManifestLedger = {
    record: vi.fn(),
    contains,
  };
  const server = createSearchServer(reader, publicationLedger, manifestLedger);
  const response = await server.inject({
    method: "GET",
    url: "/search?q=searchable&collectionId=collection-a&limit=5",
  });

  expect(response.statusCode).toBe(200);
  expect(response.json()).toMatchObject({
    results: [{ archiveId: "archive-a", snapshotId: "snapshot-a" }],
    nextCursor: null,
  });
  expect(contains).toHaveBeenCalledWith(
    "archive-a",
    "snapshot-a",
    "collection-a",
  );
  await server.close();
});

it("rejects malformed query parameters as problem details", async () => {
  const reader: SearchDocumentReader = { search: vi.fn() };
  const publicationLedger: PublicationLedger = {
    get: vi.fn(),
    recordPublicationDecision: vi.fn(),
    recordReplayPublished: vi.fn(),
    recordCompensationDecision: vi.fn(),
  };
  const manifestLedger: ManifestLedger = { record: vi.fn(), contains: vi.fn() };
  const server = createSearchServer(reader, publicationLedger, manifestLedger);
  const response = await server.inject({
    method: "GET",
    url: "/search?q=&limit=0",
  });

  expect(response.statusCode).toBe(400);
  expect(response.headers["content-type"]).toContain(
    "application/problem+json",
  );
  expect(response.json()).toMatchObject({
    title: "Invalid Search",
    status: 400,
  });
  await server.close();
});
