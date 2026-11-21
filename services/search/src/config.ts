export type Config = {
  host: string;
  port: number;
  shutdownTimeoutMs: number;

  awsRegion: string;
  awsEndpoint: string | undefined;

  ledgerTable: string;
  publicationsTable: string;
  outboxTable: string;
  inboxTable: string;
  inboxRetentionMs: number;
  claimLeaseMs: number;
  reconcileIntervalMs: number;
  outboxIntervalMs: number;
  maxDocumentAttempts: number;
  maxArtifactBytes: number;

  openSearchUrl: string;
  openSearchIndex: string;

  rabbitUrl: string;
  rabbitExchange: string;
  rabbitPrefetch: number;
  maxDeliveryAttempts: number;
  retryDelayMs: number;
};

type Environment = Record<string, string | undefined>;

export class ConfigError extends Error {}

export function loadConfig(env: Environment): Config {
  const listen = parseAddress(env.SEARCH_ADDR ?? ":8082");

  return {
    host: listen.host,
    port: listen.port,
    shutdownTimeoutMs: duration(env, "SEARCH_SHUTDOWN_TIMEOUT_MS", 10_000),

    awsRegion: env.SEARCH_AWS_REGION ?? "us-east-1",
    awsEndpoint: optional(env.SEARCH_AWS_ENDPOINT),

    ledgerTable: env.SEARCH_LEDGER_TABLE ?? "search_indexing_ledger",
    publicationsTable: env.SEARCH_PUBLICATIONS_TABLE ?? "search_publications",
    outboxTable: env.SEARCH_OUTBOX_TABLE ?? "search_outbox",
    inboxTable: env.SEARCH_INBOX_TABLE ?? "search_inbox",
    inboxRetentionMs: duration(env, "SEARCH_INBOX_RETENTION_MS", 7 * 24 * 60 * 60 * 1_000),
    claimLeaseMs: duration(env, "SEARCH_CLAIM_LEASE_MS", 120_000),
    reconcileIntervalMs: duration(env, "SEARCH_RECONCILE_INTERVAL_MS", 30_000),
    outboxIntervalMs: duration(env, "SEARCH_OUTBOX_INTERVAL_MS", 5_000),
    maxDocumentAttempts: integer(env, "SEARCH_MAX_DOCUMENT_ATTEMPTS", 3),
    maxArtifactBytes: integer(env, "SEARCH_MAX_ARTIFACT_BYTES", 64 * 1024 * 1024),

    openSearchUrl: required(env, "SEARCH_OPENSEARCH_URL"),
    openSearchIndex: env.SEARCH_OPENSEARCH_INDEX ?? "snapshots-v1",

    rabbitUrl: required(env, "SEARCH_RABBITMQ_URL"),
    rabbitExchange: env.SEARCH_RABBITMQ_EXCHANGE ?? "castellani.events",
    rabbitPrefetch: integer(env, "SEARCH_RABBITMQ_PREFETCH", 4),
    maxDeliveryAttempts: integer(env, "SEARCH_MAX_DELIVERY_ATTEMPTS", 5),
    retryDelayMs: duration(env, "SEARCH_RETRY_DELAY_MS", 5_000),
  };
}

function parseAddress(value: string): { host: string; port: number } {
  const separator = value.lastIndexOf(":");

  if (separator < 0) {
    throw new ConfigError(`SEARCH_ADDR must be host:port or :port, got ${value}`);
  }

  const host = value.slice(0, separator) || "0.0.0.0";
  const port = Number(value.slice(separator + 1));

  if (!Number.isInteger(port) || port < 1 || port > 65_535) {
    throw new ConfigError(`SEARCH_ADDR has an invalid port: ${value}`);
  }

  return { host, port };
}

function required(env: Environment, name: string): string {
  const value = optional(env[name]);

  if (value === undefined) {
    throw new ConfigError(`${name} is required`);
  }

  return value;
}

function optional(value: string | undefined): string | undefined {
  const trimmed = value?.trim();

  return trimmed ? trimmed : undefined;
}

function integer(env: Environment, name: string, fallback: number): number {
  const raw = optional(env[name]);

  if (raw === undefined) {
    return fallback;
  }

  const value = Number(raw);

  if (!Number.isSafeInteger(value) || value < 1) {
    throw new ConfigError(`${name} must be a positive integer, got ${raw}`);
  }

  return value;
}

function duration(env: Environment, name: string, fallback: number): number {
  return integer(env, name, fallback);
}
