interface SearchSettingsOptions {
  awsRegion: string;
  dynamodbEndpointUrl: string;
  s3EndpointUrl: string;
  rabbitmqUrl: string;
  opensearchUrl: string;
  artifactBucket: string;
  indexingLedgerTableName: string;
  searchIndexName: string;
  indexingLeaseDurationSeconds?: number;
  indexingMaxAttempts?: number;
  reconnectDelayMilliseconds?: number;
}

const DEFAULT_INDEXING_LEASE_DURATION_SECONDS = 120;
const DEFAULT_INDEXING_MAX_ATTEMPTS = 5;
const DEFAULT_RECONNECT_DELAY_MILLISECONDS = 1000;

function positiveInteger(
  name: string,
  value: string | undefined,
  fallback: number,
): number {
  const parsed = value === undefined ? fallback : Number(value);

  if (!Number.isSafeInteger(parsed) || parsed <= 0) {
    throw new Error(`${name} must be a positive integer`);
  }

  return parsed;
}

/** Runtime configuration for one Search service process. */
class SearchSettings {
  readonly awsRegion: string;
  readonly dynamodbEndpointUrl: string | undefined;
  readonly s3EndpointUrl: string | undefined;
  readonly rabbitmqUrl: string;
  readonly opensearchUrl: string;
  readonly artifactBucket: string;
  readonly indexingLedgerTableName: string;
  readonly searchIndexName: string;
  readonly indexingLeaseDurationSeconds: number;
  readonly indexingMaxAttempts: number;
  readonly reconnectDelayMilliseconds: number;

  constructor(options: SearchSettingsOptions) {
    this.awsRegion = options.awsRegion ?? "us-east-1";

    this.dynamodbEndpointUrl = options.dynamodbEndpointUrl;
    this.s3EndpointUrl = options.s3EndpointUrl;
    this.rabbitmqUrl = options.rabbitmqUrl;
    this.opensearchUrl = options.opensearchUrl;

    this.artifactBucket = options.artifactBucket;

    this.indexingLedgerTableName = options.indexingLedgerTableName;

    this.searchIndexName = options.searchIndexName;

    this.indexingLeaseDurationSeconds =
      options.indexingLeaseDurationSeconds ??
      DEFAULT_INDEXING_LEASE_DURATION_SECONDS;
    this.indexingMaxAttempts =
      options.indexingMaxAttempts ?? DEFAULT_INDEXING_MAX_ATTEMPTS;
    this.reconnectDelayMilliseconds =
      options.reconnectDelayMilliseconds ??
      DEFAULT_RECONNECT_DELAY_MILLISECONDS;

    if (
      !this.awsRegion.trim() ||
      !this.rabbitmqUrl.trim() ||
      !this.opensearchUrl.trim() ||
      !this.artifactBucket.trim() ||
      !this.indexingLedgerTableName.trim() ||
      !this.searchIndexName.trim()
    ) {
      throw new Error("Search settings must not contain empty required values");
    }

    for (const [name, value] of [
      ["indexingLeaseDurationSeconds", this.indexingLeaseDurationSeconds],
      ["indexingMaxAttempts", this.indexingMaxAttempts],
      ["reconnectDelayMilliseconds", this.reconnectDelayMilliseconds],
    ] as const) {
      if (!Number.isSafeInteger(value) || value <= 0) {
        throw new Error(`${name} must be a positive integer`);
      }
    }
  }

  static fromEnvironment(env: NodeJS.ProcessEnv = process.env): SearchSettings {
    return new SearchSettings({
      awsRegion: env.SEARCH_AWS_REGION,

      dynamodbEndpointUrl: env.SEARCH_DYNAMODB_ENDPOINT_URL,
      s3EndpointUrl: env.SEARCH_S3_ENDPOINT_URL,
      rabbitmqUrl: env.SEARCH_RABBITMQ_URL,
      opensearchUrl: env.SEARCH_OPENSEARCH_URL,

      artifactBucket: env.SEARCH_ARTIFACT_BUCKET,

      indexingLedgerTableName: env.SEARCH_INDEXING_LEDGER_TABLE,

      searchIndexName: env.SEARCH_INDEX_NAME,

      indexingLeaseDurationSeconds: positiveInteger(
        "SEARCH_INDEXING_LEASE_DURATION_SECONDS",
        env.SEARCH_INDEXING_LEASE_DURATION_SECONDS,
        DEFAULT_INDEXING_LEASE_DURATION_SECONDS,
      ),
      indexingMaxAttempts: positiveInteger(
        "SEARCH_INDEXING_MAX_ATTEMPTS",
        env.SEARCH_INDEXING_MAX_ATTEMPTS,
        DEFAULT_INDEXING_MAX_ATTEMPTS,
      ),
      reconnectDelayMilliseconds: positiveInteger(
        "SEARCH_RECONNECT_DELAY_MILLISECONDS",
        env.SEARCH_RECONNECT_DELAY_MILLISECONDS,
        DEFAULT_RECONNECT_DELAY_MILLISECONDS,
      ),
    });
  }
}

export { SearchSettings };
