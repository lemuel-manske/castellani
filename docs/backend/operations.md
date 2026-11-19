# Operational defaults and verification

These are configurable initial defaults, not claims of production-grade availability. Tests must verify them under injected latency and outage conditions.

| Setting | Initial value | Constraint |
|---|---|---|
| Capture execution lease | 120 seconds | Renewed with fencing; slow work may extend, stale workers cannot commit |
| Worker heartbeat interval | 20 seconds | Missed heartbeat does not by itself grant another worker write authority |
| Interactive login session TTL | 15 minutes | Manager expires idle sessions, can extend an active session explicitly |
| Submission idempotency key retention | At least 24 hours | Service returns same archive for same-key same-payload retries during retention |
| Browser slot capacity | 10 | F5 holds successful leases through the measurement |
| Transient failure retry | Exponential backoff with jitter, bounded per operation | Reconciliation persists independently of a single retry budget |
| RabbitMQ recovery | Automatic reconnect | Publisher confirms, durable queues, outbox re-dispatch |
| Coordinator reconciliation interval | 30 seconds | Reissue stalled publish/compensation decisions after the stalled-workflow age |
| Stalled workflow age | 2 minutes | Recovery command and cooldown are committed atomically |
| Reconciliation frequency | Periodic plus event-triggered | Work cannot depend on receipt of the first notification |
| DLQ | Bounded poison-message retries | A DLQ event is not a terminal business-work outcome |

## API semantics

- Public API is defined in `contracts/openapi/api.yaml`; any server-side internal HTTP endpoints must be documented when introduced, but are not a separate public API.
- The `Idempotency-Key` header is required for `POST /archives`. The same key plus semantically identical canonical request creates one run. Same key with changed canonical request returns 409; missing key returns 400.
- An accepted archive returns 202, `archiveId`, and a status URL. Retry of an already accepted request returns the same 202 representation during key retention.
- `POST /sessions` requires a session-creation `Idempotency-Key`, with the same request-digest/conflict semantics as archive admission; the Capture login manager must not start a duplicate browser on HTTP retries.
- `PUT /sessions/{sessionId}` performs an idempotent desired-state update, initially `COMPLETED` or `CANCELLED`. Completing the same session more than once returns its prior finalized result; terminally failed/expired sessions cannot be resurrected.
- Public errors use `application/problem+json` (RFC 9457); validation, auth, conflict, not-found and dependency outages must have distinguishable status/error types.
- Search accepts optional filters `collectionId`, `archiveId`, `snapshotId`, `capturedFrom`, and `capturedTo`; all scope forms use the same response contract, ordering and snippet behavior.
- Pagination uses a bounded `limit` and opaque `cursor`; cursors are not authorization tokens.
- Search result visibility requires Capture's replay publication acknowledgment, never mere index existence. Search outage must not disable replay retrieval.
- WACZ retrieval enforces the same privacy policy on full-object and partial-byte requests; use HEAD, GET, valid range semantics, and deny staged content.

## Testing and evidence

Use the Go system integration harness from ADR-0009, independent service unit tests, and the F1–F8 suite from ADR-0018.

1. Two simultaneous `POST /archives` calls with one idempotency key produce one run and one start command; mismatch produces 409.
2. Capture frontier duplicate discoveries and concurrent `maxPages` admissions never overcount or drop accepted work.
3. Delayed minimum-depth correction can admit new descendants but never reopen a durably closed crawl.
4. Kill worker after WARC upload but before DynamoDB commit; stale attempt cannot publish its artifacts.
5. Commit SAGA publication and kill coordinator before broker publish; archive converges after outbox recovery.
6. Reverse delivery order of `ArchivePublished` and `ArchivePublicationDecided`; Search must not reveal results early.
7. Force Search outage before and after WACZ publication; replay continues and archive outcome stays unchanged.
8. Publish and then deliver a stale compensation command; public WACZ remains intact.
9. Verify 100 held nonblocking requests acquire exactly 10 distinct browser slots.
10. Repeat `PUT /sessions/{sessionId}` after lost HTTP response; no additional auth generation.
11. Exercise WACZ `HEAD`, satisfiable/unsatisfiable `Range`, aborts, and private/unpublished access.
12. Confirm credentials never appear in message envelopes or logs; authenticated WARC and protected profiles require explicit authorization for access.

Implementation should validate MiniStack's DynamoDB transactional condition behavior, OpenSearch indexing/search visibility, Terraform resources, and S3 byte-range semantics against actual running services before treating provider emulation as complete.
\n
