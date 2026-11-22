import { expect, it } from "vitest";
import { createOpenSearchDocumentReader } from "../../src/adapters/search/opensearch-reader.js";
import { createOpenSearchDocumentWriter } from "../../src/adapters/search/opensearch.js";
import {
  opensearch,
  setupIntegrationEnvironment,
} from "../support/integrationEnvironment.js";
import { createSearchDocumentFixture } from "../support/fixtures.js";

setupIntegrationEnvironment("opensearch");

it("continues OpenSearch pagination from the last returned hit", async () => {
  const writer = createOpenSearchDocumentWriter(
    opensearch.client,
    opensearch.indexName,
  );
  const reader = createOpenSearchDocumentReader(
    opensearch.client,
    opensearch.indexName,
  );
  const documents = [
    {
      ...createSearchDocumentFixture("cursor-snapshot-a"),
      text: "cursor pagination searchable content",
    },
    {
      ...createSearchDocumentFixture("cursor-snapshot-b"),
      text: "cursor pagination searchable content",
    },
  ];

  await Promise.all(documents.map((document) => writer.index(document)));
  await opensearch.client.indices.refresh({ index: opensearch.indexName });

  const first = await reader.search({ text: "cursor pagination" }, 1);
  const second = await reader.search(
    { text: "cursor pagination" },
    1,
    first.nextCursor ?? undefined,
  );

  expect(first.candidates).toHaveLength(1);
  expect(first.nextCursor).toBeTruthy();
  expect(second.candidates).toHaveLength(1);
  expect(second.candidates[0]?.document.snapshotId).not.toBe(
    first.candidates[0]?.document.snapshotId,
  );
});
