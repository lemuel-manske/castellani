import { expect, it } from "vitest";
import { SearchSettings } from "../../src/assembly/config.js";

const requiredEnvironment = {
  SEARCH_AWS_REGION: "sa-east-1",
  SEARCH_DYNAMODB_ENDPOINT_URL: "http://localhost:8000",
  SEARCH_S3_ENDPOINT_URL: "http://localhost:9000",
  SEARCH_RABBITMQ_URL: "amqp://localhost",
  SEARCH_OPENSEARCH_URL: "http://localhost:9200",
  SEARCH_INDEXING_MAX_ATTEMPTS: "3",
};

it("loads service-specific environment settings", () => {
  const settings = SearchSettings.fromEnvironment({
    ...requiredEnvironment,
  });

  expect(settings.awsRegion).toBe("sa-east-1");
  expect(settings.dynamodbEndpointUrl).toBe("http://localhost:8000");
  expect(settings.s3EndpointUrl).toBe("http://localhost:9000");
  expect(settings.rabbitmqUrl).toBe("amqp://localhost");
  expect(settings.opensearchUrl).toBe("http://localhost:9200");
  expect(settings.indexingMaxAttempts).toBe(3);
});
