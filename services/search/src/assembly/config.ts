interface SearchSettingsOptions {
  awsRegion?: string;
  dynamodbEndpointUrl?: string;
  s3EndpointUrl?: string;
  rabbitmqUrl?: string;
  opensearchUrl?: string;
  artifactBucket?: string;
  indexingLedgerTableName?: string;
  searchIndexName?: string;
  indexingLeaseDurationSeconds?: number;
  indexingMaxAttempts?: number;
  reconnectDelayMilliseconds?: number;
}

function positiveInteger(name: string, value: string | undefined, fallback: number): number {
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

  constructor(options: SearchSettingsOptions = {}) {
    this.awsRegion = options.awsRegion ?? "us-east-1";
    this.dynamodbEndpointUrl = options.dynamodbEndpointUrl;
    this.s3EndpointUrl = options.s3EndpointUrl;
    this.rabbitmqUrl =
      options.rabbitmqUrl ??
      "amqp://castellani:local-development-only@localhost:5672/";
    this.opensearchUrl = options.opensearchUrl ?? "http://localhost:9200";
    this.artifactBucket = options.artifactBucket ?? "castellani-archive-artifacts";
    this.indexingLedgerTableName =
      options.indexingLedgerTableName ?? "search_indexing_ledger";
    this.searchIndexName = options.searchIndexName ?? "archive-pages-v1";
    this.indexingLeaseDurationSeconds = options.indexingLeaseDurationSeconds ?? 120;
    this.indexingMaxAttempts = options.indexingMaxAttempts ?? 5;
    this.reconnectDelayMilliseconds = options.reconnectDelayMilliseconds ?? 1000;

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
      awsRegion: env.SEARCH_AWS_REGION ?? "us-east-1",
      dynamodbEndpointUrl: env.SEARCH_DYNAMODB_ENDPOINT_URL,
      s3EndpointUrl: env.SEARCH_S3_ENDPOINT_URL,
      rabbitmqUrl:
        env.SEARCH_RABBITMQ_URL ??
        "amqp://castellani:local-development-only@localhost:5672/",
      opensearchUrl: env.SEARCH_OPENSEARCH_URL ?? "http://localhost:9200",
      artifactBucket:
        env.SEARCH_ARTIFACT_BUCKET ?? "castellani-archive-artifacts",
      indexingLedgerTableName:
        env.SEARCH_INDEXING_LEDGER_TABLE ?? "search_indexing_ledger",
      searchIndexName: env.SEARCH_INDEX_NAME ?? "archive-pages-v1",
      indexingLeaseDurationSeconds: positiveInteger(
        "SEARCH_INDEXING_LEASE_DURATION_SECONDS",
        env.SEARCH_INDEXING_LEASE_DURATION_SECONDS,
        120,
      ),
      indexingMaxAttempts: positiveInteger(
        "SEARCH_INDEXING_MAX_ATTEMPTS",
        env.SEARCH_INDEXING_MAX_ATTEMPTS,
        5,
      ),
      reconnectDelayMilliseconds: positiveInteger(
        "SEARCH_RECONNECT_DELAY_MILLISECONDS",
        env.SEARCH_RECONNECT_DELAY_MILLISECONDS,
        1000,
      ),
    });
  }
}

export { SearchSettings };
