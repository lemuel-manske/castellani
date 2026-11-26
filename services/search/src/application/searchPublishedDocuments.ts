import { isPublicationAuthorized } from "../domain/index.js";

import type { ManifestLedger } from "../ports/manifest-ledger.js";
import type { PublicationLedger } from "../ports/publication-ledger.js";
import type {
  SearchDocumentReader,
  SearchQuery,
} from "../ports/search-reader.js";

import {
  PublishedSearchPage,
  PublishedSearchResult,
  SearchPublishedDocumentsInput,
} from "./types.js";

async function searchPublishedDocuments(
  input: SearchPublishedDocumentsInput,
  reader: SearchDocumentReader,
  publicationLedger: PublicationLedger,
  manifestLedger: ManifestLedger,
): Promise<PublishedSearchPage> {
  const {
    limit,
    cursor,
  } = input;

  const query: SearchQuery = {
    ...input,
  };

  const results: PublishedSearchResult[] = [];

  const authorization = new Map<string, ReturnType<PublicationLedger["get"]>>();

  let nextCursor = cursor;

  const page = await reader.search(query, limit, nextCursor);

  if (page.candidates.length === 0) return { results, nextCursor: null };

  const archiveIds = [
    ...new Set(page.candidates.map(({ document }) => document.archiveId)),
  ];

  archiveIds.forEach((archiveId) => {
    if (!authorization.has(archiveId)) {
      authorization.set(archiveId, publicationLedger.get(archiveId));
    }
  });

  for (const candidate of page.candidates) {
    const archiveId = candidate.document.archiveId;

    const facts = await authorization.get(archiveId);

    const exists = await manifestLedger.contains(
      archiveId,
      candidate.document.snapshotId,
      input.collectionId,
    );

    const authorized = isPublicationAuthorized(facts) && exists;

    if (authorized)
      results.push({
        archiveId,
        snapshotId: candidate.document.snapshotId,
        url: candidate.document.url,
        capturedAt: candidate.document.capturedAt,
        title: candidate.document.title,
        snippet: candidate.snippet,
        score: candidate.score,
      });

    nextCursor = candidate.cursor;

    if (results.length === limit) return { results, nextCursor };

    if (page.nextCursor === null) return { results, nextCursor: null };

    nextCursor = page.nextCursor;
  }

  return { results, nextCursor: nextCursor ?? null };
}

export { searchPublishedDocuments };
