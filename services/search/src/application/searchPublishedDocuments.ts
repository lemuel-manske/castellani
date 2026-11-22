import { isPublicationAuthorized } from "../domain/publication.js";
import type { PublicationLedger } from "../ports/publication-ledger.js";
import type {
  SearchDocumentReader,
  SearchQuery,
} from "../ports/search-reader.js";

interface SearchPublishedDocumentsInput extends SearchQuery {
  limit?: number;
  cursor?: string;
}

interface PublishedSearchResult {
  archiveId: string;
  snapshotId: string;
  url: string;
  capturedAt: string;
  title: string;
  snippet: string;
  score: number;
}

interface PublishedSearchPage {
  results: PublishedSearchResult[];
  nextCursor: string | null;
}

const DEFAULT_SEARCH_LIMIT = 25;
const MAX_SEARCH_LIMIT = 100;

async function searchPublishedDocuments(
  input: SearchPublishedDocumentsInput,
  reader: SearchDocumentReader,
  publicationLedger: PublicationLedger,
): Promise<PublishedSearchPage> {
  const limit = input.limit ?? DEFAULT_SEARCH_LIMIT;

  if (!Number.isSafeInteger(limit) || limit < 1 || limit > MAX_SEARCH_LIMIT) {
    throw new Error(`search limit must be between 1 and ${MAX_SEARCH_LIMIT}`);
  }

  if (!input.text.trim()) {
    throw new Error("search text must not be empty");
  }

  const query: SearchQuery = {
    text: input.text,
    ...(input.archiveId === undefined ? {} : { archiveId: input.archiveId }),
    ...(input.snapshotId === undefined
      ? {}
      : { snapshotId: input.snapshotId }),
    ...(input.capturedFrom === undefined
      ? {}
      : { capturedFrom: input.capturedFrom }),
    ...(input.capturedTo === undefined ? {} : { capturedTo: input.capturedTo }),
  };
  const results: PublishedSearchResult[] = [];
  const authorization = new Map<
    string,
    ReturnType<PublicationLedger["get"]>
  >();
  let cursor = input.cursor;
  let nextCursor: string | null = null;

  while (results.length < limit) {
    const page = await reader.search(query, limit, cursor);

    if (page.candidates.length === 0) {
      return { results, nextCursor: null };
    }

    const archiveIds = [
      ...new Set(page.candidates.map(({ document }) => document.archiveId)),
    ];
    await Promise.all(
      archiveIds.map((archiveId) => {
        if (!authorization.has(archiveId)) {
          authorization.set(archiveId, publicationLedger.get(archiveId));
        }

        return authorization.get(archiveId);
      }),
    );

    for (const candidate of page.candidates) {
      const facts = await authorization.get(candidate.document.archiveId);

      if (facts && isPublicationAuthorized(facts)) {
        results.push({
          archiveId: candidate.document.archiveId,
          snapshotId: candidate.document.snapshotId,
          url: candidate.document.url,
          capturedAt: candidate.document.capturedAt,
          title: candidate.document.title,
          snippet: candidate.snippet,
          score: candidate.score,
        });
      }

      nextCursor = candidate.cursor;

      if (results.length === limit) {
        return { results, nextCursor };
      }
    }

    if (page.nextCursor === null) {
      return { results, nextCursor: null };
    }

    cursor = page.nextCursor;
    nextCursor = page.nextCursor;
  }

  return { results, nextCursor };
}

export { searchPublishedDocuments };
export type {
  PublishedSearchPage,
  PublishedSearchResult,
  SearchPublishedDocumentsInput,
};
