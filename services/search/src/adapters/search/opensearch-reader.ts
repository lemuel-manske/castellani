import type { Client } from "@opensearch-project/opensearch";
import type { SearchDocument } from "../../domain/content.js";
import type {
  SearchDocumentCandidate,
  SearchDocumentPage,
  SearchDocumentReader,
  SearchQuery,
} from "../../ports/search-reader.js";
import { readJSON } from "../../utils.js";

type SearchSortCursor = [number, string | number, string];

interface SearchHit {
  _source?: SearchDocument;
  _score?: number | null;
  sort?: SearchSortCursor;
  highlight?: {
    title?: string[];
    text?: string[];
    description?: string[];
  };
}

interface SearchResponse {
  hits?: {
    hits?: SearchHit[];
  };
}

function decodeCursor(
  cursor: string | undefined,
): SearchSortCursor | undefined {
  if (cursor === undefined) {
    return undefined;
  }

  try {
    const value = readJSON(cursor);

    if (!Array.isArray(value) || value.length !== 3) {
      throw new Error("invalid search cursor");
    }

    const sortValues: unknown[] = value;

    const [score, capturedAt, snapshotId] = sortValues;

    if (
      typeof score !== "number" ||
      (typeof capturedAt !== "string" && typeof capturedAt !== "number") ||
      typeof snapshotId !== "string"
    ) {
      throw new Error("invalid search cursor");
    }

    return [score, capturedAt, snapshotId];
  } catch {
    throw new Error("invalid search cursor");
  }
}

function encodeCursor(sort: SearchSortCursor | undefined): string {
  if (sort === undefined) {
    throw new Error("OpenSearch returned a hit without pagination sort values");
  }

  return Buffer.from(JSON.stringify(sort)).toString("base64url");
}

function snippetFromHit(hit: SearchHit, document: SearchDocument): string {
  const fragment =
    hit.highlight?.text?.[0] ||
    hit.highlight?.title?.[0] ||
    hit.highlight?.description?.[0] ||
    document.description ||
    document.text.slice(0, 240);

  return fragment
    .replace(/<[^>]*>/g, "")
    .replace(/\s+/g, " ")
    .trim();
}

function createOpenSearchDocumentReader(
  client: Client,
  indexName: string,
): SearchDocumentReader {
  if (!indexName.trim()) {
    throw new Error("OpenSearch index name must not be empty");
  }

  return {
    async search(
      query: SearchQuery,
      limit: number,
      cursor?: string,
    ): Promise<SearchDocumentPage> {
      const filters = [
        ...(query.archiveId === undefined
          ? []
          : [{ term: { archiveId: query.archiveId } }]),

        ...(query.snapshotId === undefined
          ? []
          : [{ term: { snapshotId: query.snapshotId } }]),

        ...(query.capturedFrom === undefined && query.capturedTo === undefined
          ? []
          : [
              {
                range: {
                  capturedAt: {
                    ...(query.capturedFrom === undefined
                      ? {}
                      : { gte: query.capturedFrom }),
                    ...(query.capturedTo === undefined
                      ? {}
                      : { lte: query.capturedTo }),
                  },
                },
              },
            ]),
      ];

      const searchAfter = decodeCursor(cursor);

      const response = (await client.search({
        index: indexName,
        body: {
          size: limit,
          query: {
            bool: {
              must: [
                {
                  multi_match: {
                    query: query.text,
                    fields: ["title^4", "description^2", "text"],
                    type: "best_fields",
                  },
                },
              ],
              filter: filters,
            },
          },
          sort: [
            { _score: "desc" },
            { capturedAt: "desc" },
            { snapshotId: "asc" },
          ],
          ...(searchAfter === undefined ? {} : { search_after: searchAfter }),
          highlight: {
            fields: {
              title: { number_of_fragments: 1, fragment_size: 160 },
              description: { number_of_fragments: 1, fragment_size: 200 },
              text: { number_of_fragments: 1, fragment_size: 240 },
            },
          },
        },
      })) as unknown as { body: SearchResponse };

      const hits = response.body.hits?.hits ?? [];

      const candidates: SearchDocumentCandidate[] = hits.flatMap((hit) => {
        if (!hit._source) {
          return [];
        }

        return [
          {
            document: hit._source,
            score: hit._score ?? 0,
            snippet: snippetFromHit(hit, hit._source),
            cursor: encodeCursor(hit.sort),
          },
        ];
      });

      const nextCursor =
        hits.length === limit && hits.length > 0
          ? encodeCursor(hits[hits.length - 1]?.sort)
          : null;

      return { candidates, nextCursor };
    },
  };
}

export { createOpenSearchDocumentReader };
