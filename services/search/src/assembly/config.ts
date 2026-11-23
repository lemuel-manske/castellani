interface SearchSettingsOptions {
  awsRegion: string;
  awsAccessKeyId: string;
  awsSecretAccessKey: string;
  httpHost: string;
  httpPort: number;
  dynamodbEndpointUrl: string;
  s3EndpointUrl: string;
  rabbitmqUrl: string;
  opensearchUrl: string;
  indexingLeaseDurationSeconds?: number;
  indexingMaxAttempts?: number;
  reconnectDelayMilliseconds?: number;
}

const DEFAULT_HTTP_HOST = "0.0.0.0";
const DEFAULT_HTTP_PORT = 8082;

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

function required(name: string, value: string | undefined): string {
  if (!value?.trim()) {
    throw new Error(`${name} must not be empty`);
  }

  return value;
}

/** Runtime configuration for one Search service process. */
class SearchSettings {
  readonly awsRegion: string;
  readonly awsAccessKeyId: string;
  readonly awsSecretAccessKey: string;
  readonly httpHost: string;
  readonly httpPort: number;
  readonly dynamodbEndpointUrl: string;
  readonly s3EndpointUrl: string;
  readonly rabbitmqUrl: string;
  readonly opensearchUrl: string;
  readonly indexingLeaseDurationSeconds: number;
  readonly indexingMaxAttempts: number;
  readonly reconnectDelayMilliseconds: number;

  constructor(options: SearchSettingsOptions) {
    this.awsRegion = options.awsRegion;
    this.awsAccessKeyId = options.awsAccessKeyId;
    this.awsSecretAccessKey = options.awsSecretAccessKey;

    this.httpHost = options.httpHost;
    this.httpPort = options.httpPort;

    this.dynamodbEndpointUrl = options.dynamodbEndpointUrl;
    this.s3EndpointUrl = options.s3EndpointUrl;
    this.rabbitmqUrl = options.rabbitmqUrl;
    this.opensearchUrl = options.opensearchUrl;

    this.indexingLeaseDurationSeconds =
      options.indexingLeaseDurationSeconds ??
      DEFAULT_INDEXING_LEASE_DURATION_SECONDS;
    this.indexingMaxAttempts =
      options.indexingMaxAttempts ?? DEFAULT_INDEXING_MAX_ATTEMPTS;
    this.reconnectDelayMilliseconds =
      options.reconnectDelayMilliseconds ??
      DEFAULT_RECONNECT_DELAY_MILLISECONDS;
  }

  static fromEnvironment(env: NodeJS.ProcessEnv = process.env): SearchSettings {
    return new SearchSettings({
      awsRegion: required("SEARCH_AWS_REGION", env.SEARCH_AWS_REGION),
      awsAccessKeyId: required(
        "SEARCH_AWS_ACCESS_KEY_ID",
        env.SEARCH_AWS_ACCESS_KEY_ID,
      ),
      awsSecretAccessKey: required(
        "SEARCH_AWS_SECRET_ACCESS_KEY",
        env.SEARCH_AWS_SECRET_ACCESS_KEY,
      ),

      httpHost: env.SEARCH_HTTP_HOST?.trim() || DEFAULT_HTTP_HOST,
      httpPort: positiveInteger(
        "SEARCH_HTTP_PORT",
        env.SEARCH_HTTP_PORT,
        DEFAULT_HTTP_PORT,
      ),

      dynamodbEndpointUrl: required(
        "SEARCH_DYNAMODB_ENDPOINT_URL",
        env.SEARCH_DYNAMODB_ENDPOINT_URL,
      ),
      s3EndpointUrl: required(
        "SEARCH_S3_ENDPOINT_URL",
        env.SEARCH_S3_ENDPOINT_URL,
      ),
      rabbitmqUrl: required("SEARCH_RABBITMQ_URL", env.SEARCH_RABBITMQ_URL),
      opensearchUrl: required(
        "SEARCH_OPENSEARCH_URL",
        env.SEARCH_OPENSEARCH_URL,
      ),

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
