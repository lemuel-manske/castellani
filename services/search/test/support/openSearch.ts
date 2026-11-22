import { randomUUID } from "node:crypto";
import { Client } from "@opensearch-project/opensearch";
import { ensureSearchIndex } from "../../src/adapters/search/opensearch.js";

const SEARCH_OPENSEARCH_URL = process.env.SEARCH_OPENSEARCH_URL;

function createOpenSearchTestSupport() {
  const client = new Client({
    node: SEARCH_OPENSEARCH_URL ?? "http://localhost:9200",
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
