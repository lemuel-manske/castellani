import { expect, it } from "vitest";
import { createOpenSearchDocumentWriter } from "../../src/adapters/search/opensearch.js";
import {
  opensearch,
  setupIntegrationEnvironment,
} from "../support/integrationEnvironment.js";
import { createSearchDocumentFixture } from "../support/fixtures.js";

setupIntegrationEnvironment("opensearch");

it("creates the index and persists a searchable document", async () => {
  const document = createSearchDocumentFixture();
  const writer = createOpenSearchDocumentWriter(
    opensearch.client,
    opensearch.indexName,
  );

  await writer.index(document);
  await opensearch.client.indices.refresh({ index: opensearch.indexName });

  const response = await opensearch.client.get({
    index: opensearch.indexName,
    id: document.snapshotId,
  });

  expect(response.body._source).toMatchObject(document);
});
