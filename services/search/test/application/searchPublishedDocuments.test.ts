import { expect, it, vi } from "vitest";
import { searchPublishedDocuments } from "../../src/application/searchPublishedDocuments.js";
import type { PublicationFacts } from "../../src/domain.js";
import type { SearchDocument } from "../../src/domain/content.js";
import type { PublicationLedger } from "../../src/ports/publication-ledger.js";
import type { SearchDocumentReader } from "../../src/ports/search-reader.js";

const document = (archiveId: string, snapshotId: string): SearchDocument => ({
  archiveId,
  snapshotId,
  url: `https://example.com/${snapshotId}`,
  finalUrl: `https://example.com/${snapshotId}`,
  capturedAt: "2026-11-22T10:00:00.000Z",
  contentType: "text/html",
  title: "Search result",
  description: "",
  language: "en",
  text: "published searchable content",
});

const authorizedFacts: PublicationFacts = {
  publicationDecision: {
    archiveId: "published-archive",
    decisionVersion: 1,
    packageDigest: "sha256:package",
  },
  replayPublication: {
    archiveId: "published-archive",
    decisionVersion: 1,
    packageDigest: "sha256:package",
  },
  compensationDecision: null,
};

const unpublishedFacts: PublicationFacts = {
  publicationDecision: {
    archiveId: "unpublished-archive",
    decisionVersion: 1,
    packageDigest: "sha256:package",
  },
  replayPublication: null,
  compensationDecision: null,
};

it("filters uncommitted documents and continues paging until the requested result count is reached", async () => {
  const reader: SearchDocumentReader = {
    search: vi
      .fn()
      .mockResolvedValueOnce({
        candidates: [
          {
            document: document("unpublished-archive", "staged-snapshot"),
            score: 4,
            snippet: "staged content",
            cursor: "cursor-one",
          },
        ],
        nextCursor: "cursor-one",
      })
      .mockResolvedValueOnce({
        candidates: [
          {
            document: document("published-archive", "published-snapshot"),
            score: 3,
            snippet: "published content",
            cursor: "cursor-two",
          },
        ],
        nextCursor: null,
      }),
  };
  const publicationLedger: PublicationLedger = {
    get: vi.fn((archiveId: string) =>
      Promise.resolve(
        archiveId === "published-archive"
          ? authorizedFacts
          : unpublishedFacts,
      ),
    ),
    recordPublicationDecision: vi.fn(),
    recordReplayPublished: vi.fn(),
    recordCompensationDecision: vi.fn(),
  };

  const result = await searchPublishedDocuments(
    { text: "published", limit: 1 },
    reader,
    publicationLedger,
  );

  expect(result).toEqual({
    results: [
      {
        archiveId: "published-archive",
        snapshotId: "published-snapshot",
        url: "https://example.com/published-snapshot",
        capturedAt: "2026-11-22T10:00:00.000Z",
        title: "Search result",
        snippet: "published content",
        score: 3,
      },
    ],
    nextCursor: "cursor-two",
  });
  expect(reader.search).toHaveBeenCalledTimes(2);
  expect(reader.search).toHaveBeenLastCalledWith(
    { text: "published" },
    1,
    "cursor-one",
  );
});

it("fails closed when publication authorization cannot be read", async () => {
  const reader: SearchDocumentReader = {
    search: vi.fn().mockResolvedValue({
      candidates: [
        {
          document: document("unavailable-ledger-archive", "candidate-snapshot"),
          score: 1,
          snippet: "candidate content",
          cursor: "cursor",
        },
      ],
      nextCursor: null,
    }),
  };
  const publicationLedger: PublicationLedger = {
    get: vi.fn().mockRejectedValue(new Error("DynamoDB unavailable")),
    recordPublicationDecision: vi.fn(),
    recordReplayPublished: vi.fn(),
    recordCompensationDecision: vi.fn(),
  };

  await expect(
    searchPublishedDocuments({ text: "candidate" }, reader, publicationLedger),
  ).rejects.toThrow("DynamoDB unavailable");
});
