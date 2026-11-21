import { Client, errors } from "@opensearch-project/opensearch";

import { type DocumentIndex, type SnapshotDocument, DocumentError, documentId } from "../indexing/model.js";
import type { ArchiveIndex } from "../publication/handler.js";
import type { RevealScope, SnapshotReveal } from "../reconciliation/reconciler.js";
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
      visible: { type: "boolean" },
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

type BulkItem = { update?: { status?: number; error?: { type?: string } } };

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
 * Only `visible` snapshots match: documents of staged, unpublished or
 * compensated archives exist in the index but are never returned.
 */
export function buildSearchBody(query: SearchQuery): Record<string, unknown> {
  const filter: unknown[] = [{ term: { visible: true } }];

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

export class OpenSearchIndex implements DocumentIndex, ArchiveIndex, SnapshotReveal {
  constructor(
    private readonly client: Client,
    private readonly index: string,
  ) {}

  static connect(url: string, index: string): OpenSearchIndex {
    return new OpenSearchIndex(new Client({ node: url, requestTimeout: 10_000 }), index);
  }

  /**
   * Creates the index with its strict mapping, or adds new fields to an
   * existing index. Mapping changes are additive only; documents written
   * before a field existed simply lack it (for `visible`, they stay hidden).
   */
  async ensureIndex(): Promise<void> {
    const exists = await this.client.indices.exists({ index: this.index });

    if (exists.body) {
      await this.client.indices.putMapping({
        index: this.index,
        body: { properties: INDEX_DEFINITION.mappings.properties },
      });

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

  /**
   * Upsert that never touches `visible` on an existing document: a new
   * document is created hidden, and re-indexing keeps a revealed snapshot
   * revealed (a stale worker cannot hide it again).
   */
  async put(document: Omit<SnapshotDocument, "visible">): Promise<void> {
    try {
      await this.client.update({
        index: this.index,
        id: documentId(document.archiveId, document.snapshotId),
        retry_on_conflict: 3,
        body: { doc: document, upsert: { ...document, visible: false } },
      });
    } catch (error) {
      if (error instanceof errors.ResponseError && error.statusCode === 400) {
        throw new DocumentError(`OpenSearch rejected snapshot ${document.snapshotId}: ${errorType(error)}`);
      }

      throw error;
    }
  }

  /**
   * Bulk-reveals snapshots, stamping the archive's collection from its
   * manifest, and refreshes, so they are searchable on return.
   */
  async reveal(archiveId: string, snapshotIds: string[], scope: RevealScope = {}): Promise<void> {
    const fields = { visible: true, ...(scope.collectionId !== undefined ? { collectionId: scope.collectionId } : {}) };

    for (let start = 0; start < snapshotIds.length; start += 500) {
      const batch = snapshotIds.slice(start, start + 500);
      const body = batch.flatMap((id) => [
        { update: { _index: this.index, _id: documentId(archiveId, id), retry_on_conflict: 3 } },
        { doc: fields },
      ]);
      const response = await this.client.bulk({ body, refresh: true });
      const failures = (response.body.items as BulkItem[])
        .map((item) => item.update)
        .filter((result) => result?.error !== undefined && result.status !== 404);

      if (failures.length > 0) {
        throw new Error(
          `OpenSearch failed to reveal ${failures.length} snapshot(s): ${failures[0]?.error?.type ?? ""}`,
        );
      }
    }
  }

  /** The snapshots of the archive that have a document in the index. */
  async present(archiveId: string, snapshotIds: string[]): Promise<Set<string>> {
    const found = new Set<string>();

    for (let start = 0; start < snapshotIds.length; start += 500) {
      const batch = snapshotIds.slice(start, start + 500);
      const response = await this.client.mget({
        index: this.index,
        _source: false,
        body: { ids: batch.map((id) => documentId(archiveId, id)) },
      });
      const docs = response.body.docs as { found?: boolean }[];

      docs.forEach((doc, position) => {
        const snapshotId = batch[position];

        if (doc.found === true && snapshotId !== undefined) {
          found.add(snapshotId);
        }
      });
    }

    return found;
  }

  async remove(archiveId: string, snapshotId: string): Promise<void> {
    await ignoreNotFound(this.client.delete({ index: this.index, id: documentId(archiveId, snapshotId) }));
  }

  async purge(archiveId: string): Promise<void> {
    await this.client.indices.refresh({ index: this.index });
    await this.client.deleteByQuery({
      index: this.index,
      conflicts: "proceed",
      refresh: true,
      body: { query: { term: { archiveId } } },
    });
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

async function ignoreNotFound(request: Promise<unknown>): Promise<void> {
  try {
    await request;
  } catch (error) {
    if (!(error instanceof errors.ResponseError && error.statusCode === 404)) {
      throw error;
    }
  }
}
