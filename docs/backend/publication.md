# Publication, replay, and compensation protocol

This protocol implements ADR-0014/0027/0029. The durable Coordinator decision is authoritative; Capture and Search own their own durable projections and use idempotent, monotonic transitions. Publication is not a cross-service transaction.

## State vocabulary

- Coordinator: `ACCEPTED -> RUNNING -> FINALIZING -> COMPLETED|COMPLETED_WITH_ERRORS` on the publish path, or `COMPENSATING -> COMPENSATED` on the prepublication-abort path. `decision` is separately `NONE|PUBLISH|COMPENSATE`.
- Capture package: `ASSEMBLING -> PREPARED -> PUBLISHED`, or `PREPARED -> DISCARDED` after a valid compensation decision. Publication cannot revert to discard.
- Search: `STAGING -> AUTHORIZED -> SEARCHABLE`, with independent per-snapshot `PENDING|INDEXED|UNSUPPORTED|FAILED` ledger outcomes. `SEARCHABLE` requires both committed publication decision and replay activation facts.

A business key `archiveId`, a monotonic `decisionVersion`, and immutable `packageDigest` identify the authorized package. All handlers validate these values against locally stored facts. A message without a compatible durable state is not permission to transition; it is retried or quarantined for reconciliation.

## Publish path

1. Capture reaches durably closed crawl frontier, publishes immutable final manifest (`CrawlCompleted`), assembles package from authorized attempt-scoped WARC, and writes a **private immutable WACZ** to S3. The package is addressable by immutable object version/digest and may be downloaded only through internal privileged operations at this stage.
2. Capture validates archive format, recorded snapshot membership, required indexes, checksum, and a replay smoke check. In a service-owned transaction, persist package `PREPARED` and corresponding `ArchivePrepared` outbox event.
3. Coordinator handles `ArchivePrepared` idempotently. It checks terminal crawl, mandatory seed success, validated matching package digest, and absence of a decision. One conditional transaction records `decision=PUBLISH`, advances `decisionVersion`, and emits `ArchivePublicationDecided`. A racing compensation decision loses its conditional check.
4. Capture consumes the decision, verifies `archiveId`, `decisionVersion`, and `packageDigest`, and durably stores the authorization. In a conditional transaction, it marks the package `PUBLISHED` and inserts `ArchivePublished` outbox event. **Do not move, copy, or make the S3 bucket/object public.** The Capture retrieval handler checks `PUBLISHED` and the immutable object metadata before serving bytes.
5. Coordinator handles `ArchivePublished` only for its matching `PUBLISH` decision and package digest, then marks `COMPLETED` or `COMPLETED_WITH_ERRORS` based on archival errors. Search/index failures never alter this outcome.
6. Search consumes `ArchivePublicationDecided` and `ArchivePublished` in either order, storing independent facts. It exposes only indexed snapshots belonging to the manifest and the exact published package after both facts match and local visibility activation succeeds; it may become searchable after replay is ready and may continue repairing missing documents. `SearchReady` is a separate projection status.

**No distributed instantaneous flip:** at every externally observable point, a public WACZ byte-range read and a search result must be authorized by the owning service's durable state. The archive may be replayable before it becomes searchable; it must not be searchable before replay activation.

## Compensation path

Only before the irreversible publication decision can Coordinator commit `decision=COMPENSATE` and publish `ArchiveCompensationDecided`. Capture and Search conditionally fence new work, prevent public visibility, clean their own staged WARC/WACZ and derived index artifacts, retain diagnostics and decision projections, and emit `ArchiveCompensated` and `SearchCompensated` respectively. Coordinator marks `COMPENSATED` only when all required acknowledgements are durable. After a `PUBLISH` decision compensation is forbidden; retry and reconciliation are required even after long outages.

A stale cleanup event must not delete an authorized published package or disable search. A late capture result must not amend an immutable manifest or resurrect a compensated run.

## Private replay delivery

`GET|HEAD /archives/{archiveId}/wacz` are proxied by Gateway to Capture. Capture authorizes the request, checks `PUBLISHED`, resolves its immutable WACZ reference, and proxies S3 bytes without exposing S3 credentials. Support `Accept-Ranges: bytes`, `Range`, `206 Partial Content`, `Content-Range`, `416 Range Not Satisfiable`, stable `ETag` and `If-Range` where applicable, bounded streaming, and `HEAD` without content. Do not rely on presigned public URLs as the primary security boundary. ReplayWeb.page is self-hosted under an origin isolated from application credentials; exact UI embedding remains deferred. Snapshot replay resolution uses immutable original URL/capture timestamp recorded for that snapshot.

## Failure matrix

| Crash or reordered delivery | Required convergence |
|---|---|
| S3 upload succeeds before Capture metadata commit | Attempt-scoped object reconciled by digest/attempt ID; retry validation and commit or safely collect orphan |
| `ArchivePrepared` or `ArchivePublished` outbox event is lost in transit | Transactional outbox republishes **same** `messageId`; inbox dedup handles repeat |
| Coordinator commits `PUBLISH` while broker is down | Decision remains authoritative; outbox dispatch resumes after reconnect |
| Capture publishes replay then crashes before Coordinator learns | Package remains `PUBLISHED`; event redelivered or reconstructed; Coordinator completes |
| Search receives `ArchivePublished` before `ArchivePublicationDecided` | Persist early fact; do not expose until both matching facts exist |
| Indexer is down indefinitely | Archive still reaches completed/replay-ready; search explicitly reports degraded/lagging |
| Old compensation or worker result arrives after `PUBLISH` | Reject stale/conflicting decision or fence; no deletion or artifact overwrite |
| Prepublication compensation commits while Capture is still preparing | Fence attempts; preparation result cannot authorize publication; staged package is cleaned or recorded for cleanup |
| Replay request during preparing/pending | Deny access; do not leak existence of private staged artifacts |

## Verification scenarios

Tests must inject crashes after each S3 write, each DynamoDB commit, and before/after each broker acknowledgment, plus reverse the delivery order of publication messages. Assert no `COMPENSATED` archive becomes replayable/searchable, no `PUBLISHED` package gets rolled back, no search link points to a not-yet-replayable archive, and already published replay continues through an Indexer outage. The system can still report an internal reconciliation state when participants have not yet converged; a timeout is never equivalent to successful compensation.
