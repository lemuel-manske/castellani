import { expect, it } from "vitest";
import { createOpenSearchDocumentReader } from "../../src/adapters/search/opensearch-reader.js";
import { createOpenSearchDocumentWriter } from "../../src/adapters/search/opensearch.js";
import { searchPublishedDocuments } from "../../src/application/searchPublishedDocuments.js";
import {
  dynamodb,
  opensearch,
  setupIntegrationEnvironment,
} from "../support/integrationEnvironment.js";
import { createSearchDocumentFixture } from "../support/fixtures.js";

setupIntegrationEnvironment(["dynamodb", "opensearch"]);

it("returns indexed documents only after matching publication and replay facts exist", async () => {
  const published = {
    ...createSearchDocumentFixture("published-search-snapshot"),
    archiveId: "published-search-archive",
    text: "distinctive searchable publication content",
  };
  const staged = {
    ...createSearchDocumentFixture("staged-search-snapshot"),
    archiveId: "staged-search-archive",
    text: "distinctive searchable publication content",
  };
  const writer = createOpenSearchDocumentWriter(
    opensearch.client,
    opensearch.indexName,
  );
  const reader = createOpenSearchDocumentReader(
    opensearch.client,
    opensearch.indexName,
  );
  const identity = {
    archiveId: published.archiveId,
    decisionVersion: 1,
    packageDigest: "sha256:published-package",
  };

  await Promise.all([writer.index(published), writer.index(staged)]);
  await dynamodb.publicationLedger.recordPublicationDecision(identity);
  await dynamodb.publicationLedger.recordReplayPublished(identity);
  await dynamodb.publicationLedger.recordPublicationDecision({
    archiveId: staged.archiveId,
    decisionVersion: 1,
    packageDigest: "sha256:staged-package",
  });
  await opensearch.client.indices.refresh({ index: opensearch.indexName });

  const result = await searchPublishedDocuments(
    { text: "distinctive searchable publication content" },
    reader,
    dynamodb.publicationLedger,
  );

  expect(result.results).toHaveLength(1);
  expect(result.results[0]).toMatchObject({
    archiveId: published.archiveId,
    snapshotId: published.snapshotId,
  });
});
