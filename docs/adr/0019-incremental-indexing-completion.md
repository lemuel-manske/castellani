# ADR-0019: Incremental indexing and completion coordination

- Status: Accepted
- Date: 2026-11-18

## Context

A crawl discovers and captures pages over time, potentially across multiple Python replicas. Waiting until the crawl finishes before indexing would leave the TypeScript Search & Index service idle and unnecessarily delay preparation of searchable content.

Page-capture events are delivered at least once, may be duplicated, and may be processed out of order relative to crawl-completion events. A completed crawl therefore does not establish that all captured pages have been indexed. The Go Coordinator may observe aggregate indexing progress without taking ownership of individual indexing tasks; indexing completion no longer gates archival publication. Captured evidence must survive indexing failures, and staged index documents must not become publicly searchable before the archive is committed.

## Decision

### Incremental processing and ownership

The Python Capture service durably stores each captured artifact in S3 and records a `PageCaptured` event for reliable publication as soon as that capture is committed. The event carries the archive/run ID, page and snapshot identities, capture metadata, and an artifact reference—not the captured content itself. The existing language-neutral message envelope applies.

RabbitMQ routes `PageCaptured` events to TypeScript Search & Index consumers, which retrieve the immutable artifacts, extract supported searchable content, prepare OpenSearch documents, and durably account for indexing outcomes in a TypeScript-owned DynamoDB ledger. Python continues capturing pages independently. Access to an S3 artifact by reference does not authorize reading the Capture service's private DynamoDB tables.

The Indexer owns all per-snapshot indexing details. The Coordinator observes only aggregate crawl and indexing outcomes; it does not track or count page-level indexing attempts. Search indexing progresses independently of archive publication under ADR-0027.

### Manifest-backed completion and reconciliation

When the Python frontier reaches durable crawl termination, it produces an immutable final manifest of the successfully captured snapshots expected by the Indexer, including sufficient artifact references for recovery. The manifest is stored in S3; `CrawlCompleted` carries a reference to it and is delivered to both the Coordinator and the Indexer as needed.

The Indexer reconciles its durable ledger against the manifest. It must account for every distinct expected snapshot even if `CrawlCompleted` arrives before some `PageCaptured` events. Missing ledger entries become recoverable indexing work using the manifest's artifact references; correctness does not depend on global RabbitMQ message ordering or perfect event delivery.

The Indexer emits a durable aggregate completion outcome only when every expected snapshot has a terminal indexing result: indexed successfully, terminal indexing failure, or intentionally not indexable under the supported content policy. Duplicate events or reconciliation passes must not inflate counts or create additional logical indexing results. The Indexer reports aggregate completion independently of the archive's publication decision. The Coordinator does **not** wait for aggregate indexing completion before publishing a validated WACZ under ADR-0027.

### Idempotency and failure isolation

Indexing is keyed by snapshot identity rather than message identity alone. Two deliveries of the same `messageId` must not produce duplicate effects, and independently triggered reconciliation of the same `snapshotId` must not produce duplicate search documents. Use stable, deterministic OpenSearch document identity per snapshot, with durable claim/result accounting and recovery when an OpenSearch write succeeds but a corresponding DynamoDB update does not. DynamoDB and OpenSearch do not share an atomic transaction; end-to-end exactly-once execution is not assumed.

Transient indexing failures use bounded, configurable execution retries and durable reconciliation. A temporarily unavailable OpenSearch service is a recoverable condition, not automatically a terminal document failure. Once a document-specific attempt policy is exhausted or its content is conclusively unsupported, the snapshot may reach a recorded terminal indexing outcome; neither pending indexing nor a terminal failure blocks archive publication. A terminal indexing failure does not delete or invalidate a successfully captured snapshot. The client must be able to inspect the failure reason separately from capture failures.

### Publication and subsequent repair

Index documents are prepared incrementally but remain excluded from public search until the Coordinator's durable publication decision. The Indexer activates search visibility independently and may do so after archival replay is already available under ADR-0027. Document existence in OpenSearch alone is not sufficient proof of public visibility. Search activation acknowledgements must satisfy the agreed searchable-visibility guarantee, including any necessary index-refresh or query-consistency handling.

After an archive is committed, failed or outdated search projections may be repaired by reindexing existing immutable snapshots without recapturing the source page or creating a new historical snapshot. Repair must respect the run's publication authorization and cannot expose results from an aborted or compensated run. The detailed mechanism for updating client-facing indexing status after repair is specified separately.

## Consequences

Indexing progresses concurrently with crawling and can continue after archive publication. The final manifest provides both an indexing completion boundary and a way to reconcile missing events. The Indexer retains ownership of fine-grained state; the Coordinator receives an aggregate signal sufficient for the SAGA.

The design requires manifest retention, an idempotent indexing ledger, a reconciliation process, stable search document identity, and an explicit publication-visibility boundary. It also adds S3 reads and DynamoDB writes to the indexing path. Since OpenSearch writes are not atomic with DynamoDB ledger updates, crash recovery must reconcile their outcomes.

This ADR does not define extraction algorithms, exact OpenSearch mappings, schema payloads, retry durations, manifest serialization format, indexing-repair endpoints, or the detailed cross-service publication protocol.
