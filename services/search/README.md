# Search and Index

TypeScript service that indexes captured snapshots into OpenSearch and serves the unified `GET /search` API ([ADR-0007](../../docs/adr/0007-opensearch-retrieval.md), [ADR-0019](../../docs/adr/0019-incremental-indexing-completion.md), [ADR-0029](../../docs/adr/0029-unified-search-replay.md)). Clients reach it through the Gateway.

## Behavior

**Indexing.** Consumes `PageCaptured` v1 events, validated against [`contracts/messages`](../../contracts/messages/README.md). For each event it reads the referenced WARC artifacts from S3 (verifying size and SHA-256), finds the successful HTML `response` record for the page (final URL first), extracts title and visible text, and writes one OpenSearch document per snapshot.

Processing is keyed by snapshot, not by message:

- The `search_indexing_ledger` DynamoDB table holds one item per snapshot, keyed by `archiveId` and `snapshotId`, with the snapshot's document ID and artifact references. A worker claims it with a conditional write and a lease, and records a terminal outcome: `INDEXED`, `UNSUPPORTED` (no indexable HTML), or `FAILED` (document error after `SEARCH_MAX_DOCUMENT_ATTEMPTS`).
- The OpenSearch document ID derives from the same key (`<archiveId>/<snapshotId>`), so a crash between the index write and the ledger update is repaired by indexing again; duplicates and redeliveries never add results, and a snapshot ID reused by another archive cannot overwrite its document.
- S3 or OpenSearch outages release the claim back to `PENDING` and are retried. They never mark a snapshot as failed.

**Publication visibility** ([ADR-0027](../../docs/adr/0027-archive-publication-replay.md), [publication](../../docs/backend/publication.md)). Documents are written hidden (`visible: false`) and `/search` only returns visible ones. Re-indexing is an upsert that never touches `visible`, so a late or stale worker cannot hide a revealed snapshot. The `search_publications` table records, per archive and independently of arrival order:

- the immutable final manifest from `CrawlCompleted`;
- the Coordinator's `ArchivePublicationDecided` (`decisionVersion`, `packageDigest`);
- Capture's `ArchivePublished` replay acknowledgment;
- an `ArchiveCompensationDecided`.

An archive is published for search only when the manifest is known, the decision and the acknowledgment carry the same version and package digest, and the run was not compensated. Even then, only **manifest snapshots** are revealed: a captured snapshot the manifest does not list, such as a fenced stale attempt, stays hidden. Each fact is written once with a conditional update, so a repeated event is idempotent. A contradicting event goes to the DLQ: a different manifest or decision, compensation after a publish decision, or publication after compensation.

**Manifest reconciliation** ([ADR-0019](../../docs/adr/0019-incremental-indexing-completion.md)). `CrawlCompleted` reads the manifest from S3, verifies its SHA-256 and schema, records it, and requests reconciliation. Every recorded fact also requests it. A request is a durable flag on a sparse GSI (`reconcile-pending-index`), served promptly in-process and by a periodic pass (`SEARCH_RECONCILE_INTERVAL_MS`) that survives restarts. A pass:

1. indexes every manifest snapshot without a terminal ledger outcome from the manifest's own artifact references, recovering lost `PageCaptured` events;
2. when the archive is published, reveals its indexed manifest snapshots;
3. once every manifest snapshot is terminal, emits `SearchIndexingCompleted` (`expected`, `indexed`, `failed`, `unsupported`); once that holds and the archive is published, emits `SearchReady`.

Both events have deterministic message IDs (`SearchIndexingCompleted:<archiveId>:<manifestDigest>`, `SearchReady:<archiveId>:<decisionVersion>`). Each report is recorded in `search_publications`, with the indexed counts, and written to the outbox in the same transaction. A pass with snapshots still in flight leaves the request pending. A request is cleared only if no new request arrived meanwhile, so a concurrent one is never lost.

**Compensation.** `ArchiveCompensationDecided` deletes the archive's documents, makes later `PageCaptured` events for it terminal (`DISCARDED`) without indexing, and then, in one transaction, records that the cleanup finished and enqueues `SearchCompensated` with the deterministic message ID `SearchCompensated:<archiveId>:<decisionVersion>`. A crash before that transaction re-runs the idempotent cleanup on redelivery; a repeated command enqueues nothing new. A compensated archive reports neither indexing completion nor readiness.

**Outbox and inbox** ([state-and-recovery](../../docs/backend/state-and-recovery.md#general-recovery-invariants)). Every emitted event goes through `search_outbox`, keyed by `messageId` and written in the same transaction as the state it reports. A dispatcher, woken on enqueue and by a periodic pass (`SEARCH_OUTBOX_INTERVAL_MS`), claims each pending record with a lease, publishes it with confirms and its stable `messageId`, and marks it `SENT` only after the confirm. A failed or unroutable publication stays pending and is retried with backoff. `search_inbox` records each consumed `messageId` after its handler finished, so a duplicate delivery is a no-op only once its effect is durable; rejected messages are not recorded. Records expire through DynamoDB TTL after `SEARCH_INBOX_RETENTION_MS`; TTL is cleanup only, and a message redelivered after its record is gone is reprocessed by the idempotent handlers.

**Messaging.** The `castellani.search` queue is bound to `castellani.events` for `PageCaptured`, `CrawlCompleted`, `ArchivePublicationDecided`, `ArchivePublished` and `ArchiveCompensationDecided`. Retries go through `castellani.search.retry` (TTL `SEARCH_RETRY_DELAY_MS`) and return only to this queue. Messages that violate the contract, are not JSON, contradict recorded facts, or exhaust `SEARCH_MAX_DELIVERY_ATTEMPTS` go to `castellani.search.dead`. Emitted events are `mandatory`: if no queue is bound, the broker returns the event and the publication fails, so the outbox record stays pending instead of being counted as delivered.

**Search.** `GET /search` implements the OpenAPI contract: `q`, the optional `collectionId`, `archiveId`, `snapshotId`, `capturedFrom` and `capturedTo` filters, `limit` (1–100, default 25), and an opaque `cursor` bound to the query it came from. Snippets are plain text. Errors are RFC 9457 problems; an OpenSearch outage returns `503`.

**Health.** `/health/live` reports that the process is up. `/health/ready` reports that the index exists and the broker consumer is connected.

## Known gaps

- `collectionId` is accepted as a filter, but `PageCaptured` carries no collection, so it matches nothing yet.
- MiniStack does not finish adding a GSI to an existing table. Adding one later needs the table recreated with `terraform apply -replace=<resource>`, or `docker compose down -v`.

## Configuration

| Variable                       | Default                  | Purpose                                           |
| ------------------------------ | ------------------------ | ------------------------------------------------- |
| `SEARCH_ADDR`                  | `:8082`                  | Listen address                                    |
| `SEARCH_OPENSEARCH_URL`        | required                 | OpenSearch data plane URL                         |
| `SEARCH_OPENSEARCH_INDEX`      | `snapshots-v1`           | Index name                                        |
| `SEARCH_RABBITMQ_URL`          | required                 | AMQP URL                                          |
| `SEARCH_RABBITMQ_EXCHANGE`     | `castellani.events`      | Event exchange                                    |
| `SEARCH_AWS_REGION`            | `us-east-1`              | AWS region                                        |
| `SEARCH_AWS_ENDPOINT`          | unset                    | MiniStack endpoint for S3 and DynamoDB            |
| `SEARCH_LEDGER_TABLE`          | `search_indexing_ledger` | Ledger table                                      |
| `SEARCH_PUBLICATIONS_TABLE`    | `search_publications`    | Per-archive publication record                    |
| `SEARCH_OUTBOX_TABLE`          | `search_outbox`          | Emitted events                                    |
| `SEARCH_INBOX_TABLE`           | `search_inbox`           | Consumed message IDs                              |
| `SEARCH_INBOX_RETENTION_MS`    | `604800000`              | Inbox record lifetime (TTL cleanup)               |
| `SEARCH_CLAIM_LEASE_MS`        | `120000`                 | Snapshot claim lease                              |
| `SEARCH_RECONCILE_INTERVAL_MS` | `30000`                  | Periodic reconciliation pass                      |
| `SEARCH_OUTBOX_INTERVAL_MS`    | `5000`                   | Periodic outbox dispatch pass                     |
| `SEARCH_MAX_DOCUMENT_ATTEMPTS` | `3`                      | Attempts before a document error becomes `FAILED` |
| `SEARCH_MAX_ARTIFACT_BYTES`    | `67108864`               | Larger artifacts are `UNSUPPORTED`                |
| `SEARCH_MAX_DELIVERY_ATTEMPTS` | `5`                      | Broker deliveries before dead-lettering           |
| `SEARCH_RETRY_DELAY_MS`        | `5000`                   | Delay before a retried delivery                   |
| `SEARCH_RABBITMQ_PREFETCH`     | `4`                      | Concurrent deliveries                             |

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
