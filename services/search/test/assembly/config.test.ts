import { expect, it } from "vitest";
import { SearchSettings } from "../../src/assembly/config.js";

const requiredEnvironment = {
  SEARCH_AWS_REGION: "sa-east-1",
  SEARCH_DYNAMODB_ENDPOINT_URL: "http://localhost:8000",
  SEARCH_S3_ENDPOINT_URL: "http://localhost:9000",
  SEARCH_RABBITMQ_URL: "amqp://localhost",
  SEARCH_OPENSEARCH_URL: "http://localhost:9200",
  SEARCH_ARTIFACT_BUCKET: "search-artifacts",
  SEARCH_INDEXING_LEDGER_TABLE: "search-ledger-test",
  SEARCH_PUBLICATION_LEDGER_TABLE: "search-publication-test",
  SEARCH_MANIFEST_LEDGER_TABLE: "search-manifest-test",
  SEARCH_INDEX_NAME: "search-index-test",
};

it("loads service-specific environment settings", () => {
  const settings = SearchSettings.fromEnvironment({
    ...requiredEnvironment,
    SEARCH_INDEXING_MAX_ATTEMPTS: "3",
  });

  expect(settings.awsRegion).toBe("sa-east-1");
  expect(settings.httpHost).toBe("0.0.0.0");
  expect(settings.httpPort).toBe(8082);
  expect(settings.dynamodbEndpointUrl).toBe("http://localhost:8000");
  expect(settings.s3EndpointUrl).toBe("http://localhost:9000");
  expect(settings.indexingLedgerTableName).toBe("search-ledger-test");
  expect(settings.publicationLedgerTableName).toBe("search-publication-test");
  expect(settings.manifestLedgerTableName).toBe("search-manifest-test");
  expect(settings.indexingMaxAttempts).toBe(3);
});

it("rejects invalid numeric environment settings", () => {
  expect(() =>
    SearchSettings.fromEnvironment({
      ...requiredEnvironment,
      SEARCH_INDEXING_MAX_ATTEMPTS: "0",
    }),
  ).toThrow("SEARCH_INDEXING_MAX_ATTEMPTS must be a positive integer");
});
