import { expect, it } from "vitest";
import { SearchSettings } from "../../src/assembly/config.js";

it("loads service defaults", () => {
  const settings = SearchSettings.fromEnvironment({});

  expect(settings.awsRegion).toBe("us-east-1");
  expect(settings.indexingLedgerTableName).toBe("search_indexing_ledger");
  expect(settings.searchIndexName).toBe("archive-pages-v1");
  expect(settings.indexingLeaseDurationSeconds).toBe(120);
});

it("loads service-specific environment settings", () => {
  const settings = SearchSettings.fromEnvironment({
    SEARCH_AWS_REGION: "sa-east-1",
    SEARCH_DYNAMODB_ENDPOINT_URL: "http://localhost:8000",
    SEARCH_S3_ENDPOINT_URL: "http://localhost:9000",
    SEARCH_INDEXING_LEDGER_TABLE: "search-ledger-test",
    SEARCH_INDEXING_MAX_ATTEMPTS: "3",
  });

  expect(settings.awsRegion).toBe("sa-east-1");
  expect(settings.dynamodbEndpointUrl).toBe("http://localhost:8000");
  expect(settings.s3EndpointUrl).toBe("http://localhost:9000");
  expect(settings.indexingLedgerTableName).toBe("search-ledger-test");
  expect(settings.indexingMaxAttempts).toBe(3);
});

it("rejects invalid numeric environment settings", () => {
  expect(() =>
    SearchSettings.fromEnvironment({
      SEARCH_INDEXING_MAX_ATTEMPTS: "0",
    }),
  ).toThrow("SEARCH_INDEXING_MAX_ATTEMPTS must be a positive integer");
});
