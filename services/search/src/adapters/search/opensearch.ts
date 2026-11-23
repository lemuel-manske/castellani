import type { Client } from "@opensearch-project/opensearch";
import type { SearchDocumentWriter } from "../../ports/search-index.js";
import type { SearchDocument } from "../../domain/content.js";

import { SEARCH_INDEX_NAME } from "./topology.js";

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

async function ensureSearchIndex(client: Client): Promise<void> {
  const existing = await client.indices.exists({ index: SEARCH_INDEX_NAME });

  if (existing.body) {
    return;
  }

  try {
    await client.indices.create({
      index: SEARCH_INDEX_NAME,
      body: SEARCH_INDEX_BODY,
    });
  } catch (error) {
    const createdByAnotherInstance = await client.indices.exists({
      index: SEARCH_INDEX_NAME,
    });

    if (!createdByAnotherInstance.body) {
      throw error;
    }
  }
}

function createOpenSearchDocumentWriter(client: Client): SearchDocumentWriter {
  return {
    async index(document: SearchDocument) {
      await client.index({
        index: SEARCH_INDEX_NAME,
        id: document.snapshotId,
        body: document,
        refresh: false,
      });
    },
  };
}

export {
  SEARCH_INDEX_NAME,
  SEARCH_INDEX_BODY,
  createOpenSearchDocumentWriter,
  ensureSearchIndex,
};
