import type { Client } from "@opensearch-project/opensearch";
import type { SearchDocument } from "../domain/content.js";
import type { SearchDocumentWriter } from "../application/indexCapturedPage.js";

const DEFAULT_SEARCH_INDEX = "archive-pages-v1";

const SEARCH_INDEX_BODY = {
  settings: {
    number_of_shards: 1,
    number_of_replicas: 0,
  },
  mappings: {
    properties: {
      archiveId: { type: "keyword" },
      snapshotId: { type: "keyword" },
      url: { type: "keyword", ignore_above: 2048 },
      finalUrl: { type: "keyword", ignore_above: 2048 },
      capturedAt: { type: "date" },
      contentType: { type: "keyword" },
      title: { type: "text" },
      description: { type: "text" },
      language: { type: "keyword" },
      text: { type: "text" },
    },
  },
} as const;

async function ensureSearchIndex(
  client: Client,
  indexName: string = DEFAULT_SEARCH_INDEX,
): Promise<void> {
  const existing = await client.indices.exists({ index: indexName });

  if (existing.body) {
    return;
  }

  try {
    await client.indices.create({ index: indexName, body: SEARCH_INDEX_BODY });
  } catch (error) {
    const createdByAnotherInstance = await client.indices.exists({
      index: indexName,
    });

    if (!createdByAnotherInstance.body) {
      throw error;
    }
  }
}

function createOpenSearchDocumentWriter(
  client: Client,
  indexName: string = DEFAULT_SEARCH_INDEX,
): SearchDocumentWriter {
  if (!indexName.trim()) {
    throw new Error("OpenSearch index name must not be empty");
  }

  return {
    async index(document: SearchDocument) {
      await client.index({
        index: indexName,
        id: document.snapshotId,
        body: document,
        refresh: false,
      });
    },
  };
}

export {
  DEFAULT_SEARCH_INDEX,
  SEARCH_INDEX_BODY,
  createOpenSearchDocumentWriter,
  ensureSearchIndex,
};
