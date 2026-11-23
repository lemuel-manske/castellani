import { Client } from "@opensearch-project/opensearch";
import { ensureSearchIndex } from "../../src/adapters/search/opensearch.js";

import { SEARCH_OPENSEARCH_URL } from "./env.js";

function createOpenSearchTestSupport() {
  const client = new Client({
    node: SEARCH_OPENSEARCH_URL,
  });

  return {
    client,

    async setup(): Promise<void> {
      await ensureSearchIndex(client);
    },

    async teardown(): Promise<void> {
      await client.close();
    },
  };
}

export { SEARCH_OPENSEARCH_URL, createOpenSearchTestSupport };
