import { randomUUID } from "node:crypto";
import { Client } from "@opensearch-project/opensearch";
import { ensureSearchIndex } from "../../src/adapters/search/opensearch.js";

import { SEARCH_OPENSEARCH_URL } from "./env.js";

function createOpenSearchTestSupport() {
  const client = new Client({
    node: SEARCH_OPENSEARCH_URL,
  });

  const indexName = `search-integration-${randomUUID().replaceAll("-", "")}`;

  return {
    client,
    indexName,

    async setup(): Promise<void> {
      await ensureSearchIndex(client, indexName);
    },

    async teardown(): Promise<void> {
      await client.indices.delete({ index: indexName }).catch(() => undefined);
      await client.close();
    },
  };
}

export { SEARCH_OPENSEARCH_URL, createOpenSearchTestSupport };
