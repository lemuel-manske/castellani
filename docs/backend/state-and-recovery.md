# Durable state, keys, and recovery

The following tables are **service owned**. Table names are proposed canonical deployment names, with a configurable namespace prefix. Items are versioned where updates race. DynamoDB transactions may involve only a single service's tables. Provisioning belongs to Terraform; the API and broker schemas do not expose table layouts.

## Coordinator (Go)

| Table | Key | Records / access |
|---|---|---|
| `coordinator_archive_runs` | PK `archiveId` | Created/status/decision/revision, seed and immutable request hash, terminal crawl report, WACZ preparation digest, Capture publication acknowledgment, aggregate error counts, public operation status |
| `coordinator_submission_keys` | PK `idempotencyKey` | Canonical request digest, `archiveId`, immutable recorded 202 response, created/expiry; TTL is cleanup only |
| `coordinator_saga_steps` | PK `archiveId`, SK `step` | State, retries, acknowledgment time, next attempt, decision revision |
| `coordinator_outbox` / `coordinator_inbox` | PK `messageId` | Envelope, destination, state, retry/lease; conditional dedup |

A `POST /archives` is one `TransactWriteItems`: conditionally create submission key; create `ArchiveRuns` with `ACCEPTED, decision=NONE, revision=0`; insert `StartCrawl` outbox message. Existing key with equal canonical request digest returns the same archive reference; mismatched digest returns 409. Concurrent same-key requests resolve via conditional-write conflict and a consistent read of the committed key, **not** a second run. To avoid uncertain admission due to expired keys, 24-hour retention is a **minimum guarantee**, not a promise about keys after expiration. An idempotency key is scoped to one deployment.

The publication decision is one conditional transaction: read the run's expected version and require `decision=NONE`, `crawlTerminal=true`, `seedSucceeded=true`, and `preparedPackageDigest` present; conditionally set `decision=PUBLISH`, increment `decisionVersion`; insert the stable `ArchivePublicationDecided` event in the outbox. A racing compensation transaction also requires `decision=NONE`; only one wins. Rejected attempts re-read the winner. `COMPLETED` requires the matching `ArchivePublished` acknowledgment and does not require `SearchReady`. A publish-decision run cannot revert to `COMPENSATING`. A compensate-decision run is `COMPENSATING` until Capture and Search cleanup acknowledgements are durable; only then `COMPENSATED`.

## Capture (Python)

| Table | Key | Records / access |
|---|---|---|
| `capture_runs` | PK `archiveId` | Seed, immutable normalizer/config revision, allowed scope, `maxPages`, page count, outstanding page/discovery/reevaluation count, admission status, crawl generation, manifest reference, prepared package reference, publication decision projection |
| `capture_frontier` | PK `archiveId`, SK `urlKey` | Normalized navigation identity, original URL, hash route, minDepth, outgoing-edge artifact reference, task state, attempt ID, leaseUntil, fence, capture outcome |
| `capture_snapshots` | PK `snapshotId` | Immutable successful capture metadata, run/urlKey, timestamp, redirect trail, attempt-scoped authorized WARC refs, content type and checksum; GSI by archive+capture time for listing |
| `capture_packages` | PK `archiveId` | WACZ immutable object key/version/checksum, manifest digest, validation evidence, `PREPARED/PUBLISHED`, decisionVersion and publication ack |
| `capture_auth_sessions` | PK `sessionId` | Login lifecycle, manager epoch, expiry, run, finalized generation reference, request idempotence revision |
| `capture_auth_session_requests` | PK `idempotencyKey` | Canonical request fingerprint, session ID, recorded creation response, expiry |
| `capture_auth_generations` | PK `archiveId`, SK `generation` | Immutable encrypted S3 state reference, creation, authorizing login, status |
| `capture_browser_slots` | PK `slotId` | 0..N-1 slot identifiers, owner attempt, leaseUntil, fence; independent conditional acquisition |
| `capture_outbox` / `capture_inbox` | PK `messageId` | Locally owned durable message delivery records |

Use a deterministic hash for `urlKey` derived from the **versioned** normalized navigation identity, and verify the stored normalized identity before treating a matching hash as a duplicate. Hash routes remain distinct navigation keys even when HTTP fetch identities are shared.

**Frontier admission transaction:** require run `OPEN`, available `maxPages` capacity, and previously unseen URL identity; conditionally create task, increment admitted/outstanding count, and create `CapturePage` outbox record. A duplicate must not consume capacity. If a shorter route is later discovered, conditionally decrease `minDepth` and durably schedule descendant reevaluation without recapturing a committed snapshot. Discoveries must not produce task admission after the terminal closure decision.

**Parent completion / large link sets:** do not put an arbitrary link set into one DynamoDB transaction (transaction item and size limits apply). Persist a discovery batch/edge reference, account its outstanding unit, admit candidates in bounded transactions, then conditionally mark the batch finished. Only after all discovery batches and depth reevaluations for the parent are accounted for may its page work become terminal. The closure transaction requires `outstandingPage=outstandingDiscovery=outstandingReevaluation=0`, `admission=OPEN`, and an expected revision, then atomically sets `admission=CLOSED`; **this condition must exclude producers that could later create work**. A retry or late worker cannot reopen a closed run.

**Task attempt:** acquiring/renewing a task conditionally sets `attemptId`, lease and monotonically increasing `fence`. Completion requires `attemptId`, current fence, unexpired lease or explicit permitted recovery policy, and active run authorization. Stage WARC under attempt-scoped immutable keys; flush, checksum, and validate before the conditional commit. Snapshot ID and `PageCaptured` outbox insertion accompany the authoritative successful task completion in the same transaction. Failed/stale attempts leave only reclaimable staged artifacts, never public snapshots.

**Capacity:** initialize N identifiable slot rows (10 in F5). A logical acquire scans/retries conditional slot claims until it either acquires a free slot or establishes the pool is exhausted; transient DynamoDB write conflicts are **not** reported as capacity exhaustion. Each successful claim records attempt identity, lease, and monotonically increasing fence; renew/release verify all three. For F5, 100 contenders each perform one *logical, nonwaiting* acquire operation, resolving internal transaction conflicts while ten successful reservations are held through the measurement; exactly 10 succeed and 90 observe full capacity. Normal page execution may wait/retry for capacity. A fenced stale holder cannot commit capture even if its process continues. A hot-slot or bounded-contention implementation that spuriously returns fewer than 10 successes fails the F5 acceptance test.

**Authentication:** creating a session atomically records its `Idempotency-Key` mapping and session state; retried same-key/same-body requests recover the original session, not another Chromium process. Finishing an active login is a conditional single transition `ACTIVE -> FINALIZING -> COMPLETED`, with a durable operation identity. The final encrypted profile write and generation metadata must be crash-reconciled; retrying the same PUT returns the existing result. An expired/failed session cannot be completed, and a new session cannot reuse an old generation ID. Never share mutable browser profile directories across workers.

## Search & Index (TypeScript)

| Table | Key | Records / access |
|---|---|---|
| `search_indexing_ledger` | PK `archiveId`, SK `snapshotId` | Stable OpenSearch document ID, artifact ref, lease/retry, terminal result or recoverable failure |
| `search_publications` | PK `archiveId` | Decision version, publication authorization received, `ArchivePublished` received, manifest reference/digest, indexed counts and visibility/repair status |
| `search_outbox` / `search_inbox` | PK `messageId` | Stable dedup/retry state |

OpenSearch documents use deterministic IDs from `snapshotId`. They are initially staged/non-queryable by public search. External OpenSearch writes and ledger commits require reconciliation; neither DynamoDB alone nor OpenSearch alone proves the other succeeded. `CrawlCompleted` provides an immutable manifest of every expected snapshot; the ledger reconciles omitted/duplicated/out-of-order `PageCaptured` messages from its artifact references. Independently store `publicationDecided` and `replayPublished` facts; make documents eligible only after **both** are true and the decision is `PUBLISH`. An indexing outage does not turn an archive into an error outcome.

## General recovery invariants

- Outbox: write in the same transaction as originating durable state; dispatcher uses publisher confirms, stable `messageId`, and conditional claims. Unroutable messages are not published.
- Inbox: duplicate `messageId` is a no-op **only after** the relevant durable effect is accounted for. A stored `RECEIVED`/claimed state may not cause lost external work. Business identities also prevent effects duplicated under distinct message IDs.
- RabbitMQ deliveries can be duplicated, late, or out of order; no service relies on queue emptiness, consumer singleton assumptions, or message order to conclude a run.
- Periodic reconcilers resume unconfirmed SAGA steps, stuck outbox records, expired frontier tasks/leases, incomplete discovery, staged WARC/WACZ uploads, incomplete login finalization, and Search ledger/OpenSearch divergence.
- Cleanup of expired DynamoDB items, leaked attempt artifacts, and protected profiles must be policy-driven, bounded, and never delete durable references needed for a committed archive. DynamoDB TTL is not a reliable real-time scheduler.
- No DynamoDB, S3, or OpenSearch transaction spans service owners. State changes and side effects must converge with stable IDs, conditional updates, and retry/reconciliation, never through imagined atomic cross-service commits.
