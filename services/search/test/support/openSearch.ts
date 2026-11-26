import { Client } from "@opensearch-project/opensearch";
import { ensureSearchIndex } from "../../src/adapters/search/opensearch.js";

import type { SearchSettings } from "../../src/config.js";

function createOpenSearchTestSupport(settings: SearchSettings) {
  const client = new Client({
    node: settings.opensearchUrl,
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

export { createOpenSearchTestSupport };
