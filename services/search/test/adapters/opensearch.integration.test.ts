import { afterAll, beforeAll, expect, it } from "vitest";
import type { SearchDocument } from "../../src/domain/content.js";
import {
  SEARCH_OPENSEARCH_URL,
  createOpenSearchTestSupport,
} from "../support/openSearch.js";
import { createOpenSearchDocumentWriter } from "../../src/adapters/search/opensearch.js";

const support = createOpenSearchTestSupport();

const document: SearchDocument = {
  archiveId: "integration-archive",
  snapshotId: "integration-snapshot",
  url: "https://example.com/",
  finalUrl: "https://example.com/final",
  capturedAt: "2026-11-22T10:00:00.000Z",
  contentType: "text/html",
  title: "Integration document",
  description: "Indexed against a real OpenSearch node",
  language: "en",
  text: "Search integration test content",
};

beforeAll(async () => {
  if (!SEARCH_OPENSEARCH_URL?.trim()) {
    throw new Error(
      "SEARCH_OPENSEARCH_URL is required; start the Search Compose dependencies and configure the integration-test environment",
    );
  }

  await support.setup();
});

afterAll(async () => {
  if (SEARCH_OPENSEARCH_URL?.trim()) {
    await support.teardown();
  }
});

it("creates the index and persists a searchable document", async () => {
  const writer = createOpenSearchDocumentWriter(
    support.client,
    support.indexName,
  );

  await writer.index(document);
  await support.client.indices.refresh({ index: support.indexName });

  const response = await support.client.get({
    index: support.indexName,
    id: document.snapshotId,
  });

  expect(response.body._source).toMatchObject(document);
});
