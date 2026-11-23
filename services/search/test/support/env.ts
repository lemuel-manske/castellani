const SEARCH_DYNAMODB_ENDPOINT_URL = process.env.SEARCH_DYNAMODB_ENDPOINT_URL;
const SEARCH_OPENSEARCH_URL = process.env.SEARCH_OPENSEARCH_URL;
const SEARCH_RABBITMQ_URL = process.env.SEARCH_RABBITMQ_URL;
const SEARCH_S3_ENDPOINT_URL = process.env.SEARCH_S3_ENDPOINT_URL;

function required(name: string): string {
  const value = process.env[name];

  if (!value?.trim()) {
    throw new Error(`${name} must not be empty`);
  }

  return value;
}

const ACCESS_KEY_ID = required("SEARCH_AWS_ACCESS_KEY_ID");
const SECRET_ACCESS_KEY = required("SEARCH_AWS_SECRET_ACCESS_KEY");
const REGION = required("SEARCH_AWS_REGION");

export {
  ACCESS_KEY_ID,
  REGION,
  SEARCH_DYNAMODB_ENDPOINT_URL,
  SEARCH_OPENSEARCH_URL,
  SEARCH_RABBITMQ_URL,
  SEARCH_S3_ENDPOINT_URL,
  SECRET_ACCESS_KEY,
};
