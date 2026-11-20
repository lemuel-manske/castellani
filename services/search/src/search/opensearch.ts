import { Client, errors } from "@opensearch-project/opensearch";

import { type DocumentIndex, type SnapshotDocument, DocumentError } from "../indexing/model.js";
import { type SortKey, decodeCursor, encodeCursor } from "./cursor.js";
import { type SearchQuery, fingerprint } from "./query.js";

export const SNIPPET_CHARS = 200;

export const INDEX_DEFINITION = {
  settings: { number_of_shards: 1, number_of_replicas: 0 },
  mappings: {
    dynamic: "strict",
    properties: {
      snapshotId: { type: "keyword" },
      archiveId: { type: "keyword" },
      collectionId: { type: "keyword" },
      urlKey: { type: "keyword" },
      url: { type: "keyword" },
      finalUrl: { type: "keyword" },
      capturedAt: { type: "date" },
      contentType: { type: "keyword" },
      title: { type: "text" },
      content: { type: "text" },
      indexedAt: { type: "date" },
    },
  },
} as const;

export type SearchResult = {
  collectionId?: string;
  archiveId: string;
  snapshotId: string;
  url: string;
  capturedAt: string;
  title?: string;
  snippet: string;
  score: number;
};

export type SearchPage = { results: SearchResult[]; nextCursor: string | null };

export class SearchUnavailableError extends Error {}

type Hit = {
  _score?: number | null;
  _source?: Partial<SnapshotDocument> & { collectionId?: string };
  highlight?: Record<string, string[]>;
  sort?: unknown[];
};

/**
 * Builds the OpenSearch request for one page. Fetches `limit + 1` hits to
 * learn whether another page exists without counting the full result set.
 *
 * Publication visibility (ADR-0019/0029) is not enforced yet: every indexed
 * snapshot is searchable. It must become a filter here once Search records
 * the publication decision and replay acknowledgment.
 */
export function buildSearchBody(query: SearchQuery): Record<string, unknown> {
  const filter: unknown[] = [];

  for (const field of ["collectionId", "archiveId", "snapshotId"] as const) {
    const value = query[field];

    if (value !== undefined) {
      filter.push({ term: { [field]: value } });
    }
  }

  if (query.capturedFrom !== undefined || query.capturedTo !== undefined) {
    filter.push({
      range: {
        capturedAt: {
          ...(query.capturedFrom !== undefined ? { gte: query.capturedFrom } : {}),
          ...(query.capturedTo !== undefined ? { lte: query.capturedTo } : {}),
        },
      },
    });
  }

  const body: Record<string, unknown> = {
    size: query.limit + 1,
    track_total_hits: false,
    track_scores: true,
    _source: ["snapshotId", "archiveId", "collectionId", "url", "capturedAt", "title"],
    query: {
      bool: {
        must: [{ multi_match: { query: query.text, fields: ["title^2", "content"] } }],
        filter,
      },
    },
    sort: [{ _score: "desc" }, { capturedAt: "desc" }, { snapshotId: "asc" }],
    // Empty tags keep snippets plain text: they are never trusted HTML.
    highlight: {
      pre_tags: [""],
      post_tags: [""],
      fields: {
        content: { fragment_size: SNIPPET_CHARS, number_of_fragments: 1, no_match_size: SNIPPET_CHARS },
      },
    },
  };

  if (query.cursor !== undefined) {
    body.search_after = decodeCursor(query.cursor, fingerprint(query));
  }

  return body;
}

export function toSearchPage(query: SearchQuery, hits: Hit[]): SearchPage {
  const page = hits.slice(0, query.limit);
  const results = page.map(toResult);
  const last = page.at(-1);
  const hasMore = hits.length > query.limit && last?.sort !== undefined;

  return {
    results,
    nextCursor: hasMore ? encodeCursor(fingerprint(query), last.sort as SortKey) : null,
  };
}

function toResult(hit: Hit): SearchResult {
  const source = hit._source ?? {};
  const snippet = hit.highlight?.content?.[0] ?? "";

  return {
    ...(source.collectionId ? { collectionId: source.collectionId } : {}),
    archiveId: String(source.archiveId),
    snapshotId: String(source.snapshotId),
    url: String(source.url),
    capturedAt: new Date(String(source.capturedAt)).toISOString(),
    ...(source.title ? { title: source.title } : {}),
    snippet: snippet.trim(),
    score: hit._score ?? 0,
  };
}

export class OpenSearchIndex implements DocumentIndex {
  constructor(
    private readonly client: Client,
    private readonly index: string,
  ) {}

  static connect(url: string, index: string): OpenSearchIndex {
    return new OpenSearchIndex(new Client({ node: url, requestTimeout: 10_000 }), index);
  }

  /** Creates the index with its strict mapping when it does not exist. */
  async ensureIndex(): Promise<void> {
    const exists = await this.client.indices.exists({ index: this.index });

    if (exists.body) {
      return;
    }

    try {
      await this.client.indices.create({ index: this.index, body: INDEX_DEFINITION });
    } catch (error) {
      if (!(error instanceof errors.ResponseError && errorType(error) === "resource_already_exists_exception")) {
        throw error;
      }
    }
  }

  async ping(): Promise<boolean> {
    try {
      await this.client.cluster.health({ index: this.index, timeout: "2s" });

      return true;
    } catch {
      return false;
    }
  }

  async put(document: SnapshotDocument): Promise<void> {
    try {
      await this.client.index({ index: this.index, id: document.snapshotId, body: document });
    } catch (error) {
      if (error instanceof errors.ResponseError && error.statusCode === 400) {
        throw new DocumentError(`OpenSearch rejected snapshot ${document.snapshotId}: ${errorType(error)}`);
      }

      throw error;
    }
  }

  async search(query: SearchQuery): Promise<SearchPage> {
    const body = buildSearchBody(query);

    try {
      const response = await this.client.search({ index: this.index, body });
      const hits = response.body.hits.hits as Hit[];

      return toSearchPage(query, hits);
    } catch (error) {
      throw new SearchUnavailableError(`OpenSearch query failed: ${describe(error)}`, { cause: error });
    }
  }
}

function errorType(error: InstanceType<typeof errors.ResponseError>): string {
  const body = error.body as { error?: { type?: string } } | undefined;

  return body?.error?.type ?? `HTTP ${String(error.statusCode)}`;
}

function describe(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}
