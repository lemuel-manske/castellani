import { Client } from "@opensearch-project/opensearch";
import { ensureSearchIndex } from "../../src/adapters/search/opensearch.js";
import { SEARCH_INDEX_NAME } from "../../src/adapters/search/topology.js";

import { SEARCH_OPENSEARCH_URL } from "./env.js";

function createOpenSearchTestSupport() {
  const client = new Client({
    node: SEARCH_OPENSEARCH_URL,
  });

  async function clearIndex(): Promise<void> {
    await client.deleteByQuery({
      index: SEARCH_INDEX_NAME,
      body: { query: { match_all: {} } },
      refresh: true,
    });
  }

  return {
    client,

    async setup(): Promise<void> {
      await ensureSearchIndex(client);
      await clearIndex();
    },

    async teardown(): Promise<void> {
      try {
        await clearIndex();
      } finally {
        await client.close();
      }
    },
  };
}

export { SEARCH_OPENSEARCH_URL, createOpenSearchTestSupport };
