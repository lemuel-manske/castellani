# Search and Index

TypeScript service that indexes captured snapshots into OpenSearch and serves the unified `GET /search` API ([ADR-0007](../../docs/adr/0007-opensearch-retrieval.md), [ADR-0019](../../docs/adr/0019-incremental-indexing-completion.md), [ADR-0029](../../docs/adr/0029-unified-search-replay.md)). Clients reach it through the Gateway.

## Behavior

**Indexing.** Consumes `PageCaptured` v1 events, validated against [`contracts/messages`](../../contracts/messages/README.md). For each event it reads the referenced WARC artifacts from S3 (verifying size and SHA-256), finds the successful HTML `response` record for the page (final URL first), extracts title and visible text, and writes one OpenSearch document per snapshot.

Processing is keyed by `snapshotId`, not by message:

- The `search_index_ledger` DynamoDB table holds one item per snapshot. A worker claims it with a conditional write and a lease, and records a terminal outcome: `INDEXED`, `UNSUPPORTED` (no indexable HTML), or `FAILED` (document error after `SEARCH_MAX_DOCUMENT_ATTEMPTS`).
- The OpenSearch document ID is the snapshot ID, so a crash between the index write and the ledger update is repaired by indexing again; duplicates and redeliveries never add results.
- S3 or OpenSearch outages release the claim back to `PENDING` and are retried. They never mark a snapshot as failed.

**Messaging.** The `castellani.search` queue is bound to `castellani.events` for `PageCaptured`. Retries go through `castellani.search.retry` (TTL `SEARCH_RETRY_DELAY_MS`) and return only to this queue. Messages that violate the contract, are not JSON, or exhaust `SEARCH_MAX_DELIVERY_ATTEMPTS` go to `castellani.search.dead`.

**Search.** `GET /search` implements the OpenAPI contract: `q`, the optional `collectionId`, `archiveId`, `snapshotId`, `capturedFrom` and `capturedTo` filters, `limit` (1–100, default 25), and an opaque `cursor` bound to the query it came from. Snippets are plain text. Errors are RFC 9457 problems; an OpenSearch outage returns `503`.

**Health.** `/health/live` reports that the process is up. `/health/ready` reports that the index exists and the broker consumer is connected.

## Not implemented yet

- **Publication visibility.** Every indexed snapshot is searchable. ADR-0019/0029 require results to stay hidden until the archive's `ArchivePublicationDecided` and Capture's `ArchivePublished` agree, and compensated runs must never appear. Until that lands, this service must not be treated as contract-complete.
- `CrawlCompleted` manifest reconciliation, `SearchIndexingCompleted`, `SearchReady` and `SearchCompensated`.
- `collectionId` is accepted as a filter, but `PageCaptured` carries no collection, so it matches nothing yet.

## Configuration

| Variable                       | Default               | Purpose                                           |
| ------------------------------ | --------------------- | ------------------------------------------------- |
| `SEARCH_ADDR`                  | `:8082`               | Listen address                                    |
| `SEARCH_OPENSEARCH_URL`        | required              | OpenSearch data plane URL                         |
| `SEARCH_OPENSEARCH_INDEX`      | `snapshots-v1`        | Index name                                        |
| `SEARCH_RABBITMQ_URL`          | required              | AMQP URL                                          |
| `SEARCH_RABBITMQ_EXCHANGE`     | `castellani.events`   | Event exchange                                    |
| `SEARCH_AWS_REGION`            | `us-east-1`           | AWS region                                        |
| `SEARCH_AWS_ENDPOINT`          | unset                 | MiniStack endpoint for S3 and DynamoDB            |
| `SEARCH_LEDGER_TABLE`          | `search_index_ledger` | Ledger table                                      |
| `SEARCH_CLAIM_LEASE_MS`        | `120000`              | Snapshot claim lease                              |
| `SEARCH_MAX_DOCUMENT_ATTEMPTS` | `3`                   | Attempts before a document error becomes `FAILED` |
| `SEARCH_MAX_ARTIFACT_BYTES`    | `67108864`            | Larger artifacts are `UNSUPPORTED`                |
| `SEARCH_MAX_DELIVERY_ATTEMPTS` | `5`                   | Broker deliveries before dead-lettering           |
| `SEARCH_RETRY_DELAY_MS`        | `5000`                | Delay before a retried delivery                   |
| `SEARCH_RABBITMQ_PREFETCH`     | `4`                   | Concurrent deliveries                             |

In Compose, `SEARCH_OPENSEARCH_URL` points at MiniStack's data-plane container, whose name is derived from account and region (see the `opensearch_dataplane_url` Terraform output).

## Development

Node 24.16.0 and plain npm with the committed lockfile (ADR-0024).

```sh
make install          # npm ci
make check            # prettier, tsc, eslint
make test             # unit and behavior tests
make test-integration # against the running Compose stack
```

The integration tests expect the Compose stack and run from a container on its network:

```sh
docker compose up -d --build
docker run --rm --network castellani_default -v "$PWD/../..:/srv" -w /srv/services/search \
  node:24.16.0-alpine3.22 sh -c "npm ci && npm run test:integration"
```
