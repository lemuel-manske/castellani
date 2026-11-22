import { randomUUID } from "node:crypto";
import { afterAll, beforeAll, describe, expect, it } from "vitest";
import { Client } from "@opensearch-project/opensearch";
import {
  createOpenSearchDocumentWriter,
  ensureSearchIndex,
} from "../../src/adapters/search/opensearch.js";
import type { SearchDocument } from "../../src/domain/content.js";

const node = process.env.SEARCH_TEST_OPENSEARCH_URL;

describe.skipIf(node === undefined)("OpenSearch indexing integration", () => {
  const client = new Client({ node: node ?? "http://localhost:9200" });
  const indexName = `search-integration-${randomUUID().replaceAll("-", "")}`;

  beforeAll(async () => {
    await ensureSearchIndex(client, indexName);
  });

  afterAll(async () => {
    await client.indices.delete({ index: indexName }).catch(() => undefined);
    await client.close();
  });

  it("writes a snapshot document that can be retrieved by its deterministic ID", async () => {
    const document: SearchDocument = {
      archiveId: "integration-archive",
      snapshotId: "integration-snapshot",
      url: "https://example.com/",
      finalUrl: "https://example.com/",
      capturedAt: "2026-11-22T10:00:00.000Z",
      contentType: "text/html",
      title: "Integration test",
      description: "OpenSearch adapter integration",
      language: "en",
      text: "A searchable integration-test document",
    };

    const writer = createOpenSearchDocumentWriter(client, indexName);
    await writer.index(document);

    const response = await client.get({
      index: indexName,
      id: document.snapshotId,
    });

    expect(response.body._source).toEqual(document);
  });
});