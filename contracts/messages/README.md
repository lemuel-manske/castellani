# RabbitMQ message catalog (v1)

All broker messages validate against `envelope.v1.schema.json` and their more specific `*.v1.schema.json` payload schema. This is a **logical** routing catalog; broker declaration/configuration will assign durable exchanges, bindings, queues, backoff and DLQ names. Producers write the envelope to a service-owned transactional outbox before publishing. A consumer acknowledges only when its recoverable business obligation is durable.

| Type | Producer | Consumers | Meaning and deduplication identity |
|---|---|---|---|
| `StartCrawl` | Coordinator | Capture | Start admitted run; dedup on `archiveId` |
| `CapturePage` | Capture frontier | Competing Capture workers | Notify work available; dedup `archiveId + urlKey`, acquire lease/fence in DynamoDB before work |
| `PageCaptured` | Capture | Search & Index | One immutable `snapshotId`; reconcile external indexing by snapshot ID |
| `CrawlCompleted` | Capture | Coordinator, Search & Index | Immutable manifest reference+digest; arrival does not imply Indexer has finished |
| `ArchivePrepared` | Capture | Coordinator | Validated private WACZ package reference+digest; not authorization to replay |
| `ArchivePublicationDecided` | Coordinator | Capture, Search & Index | Durable irreversible publish decision identified by `archiveId + decisionVersion`; only Coordinator produces it |
| `ArchivePublished` | Capture | Coordinator, Search & Index | Replay activated for exact `archiveId + decisionVersion + packageDigest` |
| `ArchiveCompensationDecided` | Coordinator | Capture, Search & Index | Durable irreversible prepublication abort; only Coordinator produces it |
| `ArchiveCompensated` | Capture | Coordinator | Capture-owned staged artifacts cleaned and task admission fenced |
| `SearchCompensated` | Search & Index | Coordinator | Derived indexed/staged results cleaned or made permanently inaccessible |
| `SearchIndexingCompleted` | Search & Index | Coordinator | All expected manifest snapshots accounted for; **not** an archive completion gate |
| `SearchReady` | Search & Index | Coordinator | Search projection activation complete; does not change archival outcome |

## Semantic conventions

- Commands are requests to perform work (`StartCrawl`, `CapturePage`); events report committed facts (the rest).
- `messageId` identifies a **logical emission**, not `archiveId`, `snapshotId`, task, or attempt. Retrying the same outbox emission preserves its original `messageId`. Distinct logical emissions have distinct message IDs even if they refer to the same run.
- `correlationId` is `archiveId` for all run-scoped events. No cross-service raw credential or browser state data travels in payloads.
- Version is a major schema contract number. Producers must not change v1 payload semantics incompatibly. Add optional compatible fields or emit a new explicit version; consumers must reject or DLQ unsupported versions without losing business recovery accounting.
- A `CrawlCompleted` event gives the Indexer a recovery source: immutable manifest entries, not another service's DynamoDB records. The manifest digest must remain consistent for a run.
- A durable `ArchivePublicationDecided` event proves Coordinator's decision *only once* a participant reconciles it with valid local run and package facts. Capture must persist the accepted decision, fence stale operations, and check local `PUBLISHED` on every replay read.
- Search stores publish decision and replay publication as **independent** facts. It can see either first. It must not expose search results unless both refer to the same authorized run/package. `SearchReady` means eventual projection readiness, not a prerequisite for `COMPLETED`.
- The Coordinator correlates compensation acknowledgments by decision version, not by delivery order. Publication and compensation events are mutually exclusive for a run.

## Delivery topology

Use one queue per logical consumer/consumer group where events require fan-out, and a competing consumer queue for Capture page tasks. In particular, `CrawlCompleted` and `ArchivePublished` must reach **both** Coordinator and Search using independently durable queues. A shared queue would split events between consumers and is incorrect. `ArchivePublicationDecided` and `ArchiveCompensationDecided` likewise fan out to Capture and Search. Queues are durable, messages persistent, manual-acknowledged; publisher confirms plus unroutable-message detection are required.

Retries use bounded attempts and backoff, with failed poison messages routed to a DLQ. A transport DLQ does not by itself close a page task or compensate a SAGA; owner reconcilers must account for the outstanding work. Exchange/queue names, TTL defaults, and replay tooling remain broker bootstrap details.

## Manifest and compatibility

Final capture-set manifest uses `../archive-manifest.v1.schema.json`. Its `snapshots` array enumerates the **authorized successful** snapshots only; `failedPages` reports failed logical navigations. A manifest is immutable once emitted. WACZ contents are selected from the same committed manifest, and package digest identifies the prepared immutable artifact. Artifact refs are readable through authorized service-to-service S3 access without granting read access to Capture-private DynamoDB tables.
