# End-to-end happy-path scenario backlog

The scenarios below extend the cross-service suite under `tests/`. Status reflects `TRACKING.md`: **ready** has no listed implementation or contradiction blocker, **needs harness** has no functional blocker but requires infrastructure control the suite does not yet expose, **harness in place; test not added** means the suite already provides the control but no focused assertion exists, and **blocked** depends on a gap listed in `TRACKING.md` section 2 or 3.

Each scenario uses the shared, suite-owned stack, a unique `TestEnv` idempotency-key prefix, and automatic per-test cleanup. Assertions stay at documented API or message-contract boundaries.

Scenarios 1–8 have tests in `tests/tests/`, and compile-only checks pass. The last live run found three search-filter failures caused by expecting three indexed `fixture` pages; those tests now use single-page archives and inclusive/exclusive bounds. A live `make test` rerun is still pending.

## Already covered

- `TestArchiveLifecycle_CompletesSuccessfully` — admission returns `202`, polling reaches `COMPLETED` with three captured pages, no failures, `replay.status=READY`, and `GET /archives/{id}/wacz` returns a ZIP.
- `TestArchiveDelivery_ReturnsWACZByteRange` — `Range: bytes=0-3` returns `206` with the expected `Content-Range` and ZIP magic bytes.
- `TestArchiveSearch_FindsPublishedSnapshot` — an `archiveId`-scoped `/search` query returns the published snapshot.
- `TestArchivePages_PaginatesCapturedPages` — `/archives/{id}/pages` paginates with a cursor and each page resolves through `/snapshots/{snapshotId}`.
- `TestArchiveAdmission_RepeatedSubmissionReturnsOriginalArchive` — repeating an admission with the same idempotency key returns the original acceptance.
- `TestArchiveSubmission_*` — five request-validation negative cases.
- `TestArchive_Rearchiving_PreservesDistinctSnapshots` — two archives of the same seed URL have distinct archive/snapshot identities and remain retrievable and searchable.
- `TestArchiveSearch_*` — focused tests for result schema, unfiltered search, collection/snapshot/capture-time filters, and cursor pagination; `TestArchiveSearch_FindsPublishedSnapshot` covers the `archiveId` filter.
- `TestArchiveSearch_SnippetIsSafeHtml` — search snippets strip captured script and event-handler markup while retaining the matching text.

## Implemented scenarios

Scenarios 1–8 now have end-to-end tests in `tests/tests/`; no ready scenarios remain.

1. `TestArchive_DurableAdmission_IsImmediatelyReadable` (ADR-0010) — **test added**
   - Given a valid archive request and generated idempotency key.
   - When the client submits `POST /archives`.
   - Then the response is `202` with `Location`, `archiveId`, `statusUrl`, and `status=ACCEPTED`; an immediate `GET` on `statusUrl` returns `200` with the same `archiveId` and `replay.status=NOT_READY`.

2. `TestArchive_Polling_ShowsLifecycleProgression` (ADR-0010, ADR-0014) — **test added**
   - Given an admitted three-page archive.
   - When the client polls the status resource until it reaches a terminal state.
   - Then the observed statuses progress through `ACCEPTED`, `RUNNING`, `FINALIZING`, and `COMPLETED`; `capture.captured` increases monotonically; `decision=PUBLISH`; and `replay.status=READY`.

3. `TestArchive_CrawlLimit_AdmitsOnlyAllowedPages` (ADR-0013, ADR-0022) — **test added**
   - Given the three-page fixture site and a request with `maxPages=2`.
   - When the archive completes.
   - Then exactly two pages are captured, page URLs and snapshot IDs are unique, and status is `COMPLETED` rather than `COMPLETED_WITH_ERRORS`.

4. `TestArchive_Wacz_ContainsPublishedRecords` (ADR-0023, ADR-0026, ADR-0027) — **test added**
   - Given a completed three-page archive.
   - When the client downloads `GET /archives/{id}/wacz` and opens it as a ZIP.
   - Then the package contains `datapackage.json` and gzip-compressed WARC entries whose `WARC-Target-URI` headers match every captured page.

5. `TestArchive_Wacz_DeliveryMetadataIsStable` (ADR-0027) — **test added**
   - Given a completed archive.
   - When the client issues `HEAD` and repeated `GET` requests for the WACZ.
   - Then `HEAD` returns `Accept-Ranges: bytes`, `Content-Length`, and an `ETag`; repeated `GET` responses return identical bytes and the same `ETag`.

6. `TestArchive_Rearchiving_PreservesDistinctSnapshots` (ADR-0011, ADR-0023, ADR-0029) — **test added**
   - Given two separate archives created from the same seed URL in one test.
   - When both archives complete.
   - Then their `archiveId` and `snapshotId` values differ, their `capturedAt` values differ, their `url` values match, and both snapshots remain retrievable and searchable after the second run.

7. Search query scopes and pagination (ADR-0007, ADR-0029) — **test added as focused scenarios**
   - `TestArchiveSearch_ResultsUseDocumentedSchema` verifies the documented result fields.
   - `TestArchiveSearch_UnfilteredQueryFindsPublishedPage` verifies an unfiltered query.
   - `TestArchiveSearch_FiltersByCollection` verifies `collectionId`; `TestArchiveSearch_FindsPublishedSnapshot` verifies `archiveId`.
   - `TestArchiveSearch_FiltersBySnapshot` verifies `snapshotId`.
   - `TestArchiveSearch_FiltersByCapturedFrom` and `TestArchiveSearch_FiltersByCapturedTo` verify inclusive and exclusive capture-time bounds on one-page archives.
   - `TestArchiveSearch_PaginatesPublishedResults` verifies `limit` and a stable `nextCursor` across two one-page archives in one collection sharing a phrase.

8. `TestArchiveSearch_SnippetIsSafeHtml` (ADR-0029) — **test added**
   - Given a fixture page containing `<script>` and `<img onerror=...>` text plus the search phrase.
   - When the client searches for the phrase.
   - Then the result snippet contains no executable HTML while still matching the query.

## Needs harness or dedicated assertion

9. `TestArchive_CompetingConsumers_CaptureEachPageOnce` (ADR-0003, ADR-0016, ADR-0021) — **needs harness**
   - Given three `capture-worker` replicas consuming the same queue and a multi-page fixture.
   - When an archive completes.
   - Then each logical page has one frontier task and one snapshot, page URLs are unique, and capture counters match the fixture.

10. `TestArchive_DuplicateMessageId_HasOneEffect` (ADR-0018 F3, ADR-0020) — **needs harness**
    - Given a broker client able to republish a logical message with the same `messageId`.
    - When the same `StartCrawl` or `PageCaptured` message is delivered five times.
    - Then only one run, frontier task, or indexed document is committed, and counters are not inflated.

11. `TestArchive_GatewayRestart_PreservesRun` (ADR-0002, ADR-0005) — **needs harness**
    - Given a run in `RUNNING` state.
    - When the Gateway container is restarted.
    - Then status queries and `/search` continue to work and the run reaches the same terminal outcome without re-admission.

12. `TestInfrastructure_StackIsProvisionedOnce` (ADR-0004, ADR-0024) — **harness in place; test not added**
    - Given a fresh Compose stack.
    - When the suite finishes bootstrap.
    - Then all service health endpoints, RabbitMQ management topology from `infra/rabbitmq/definitions.json`, DynamoDB tables, S3 buckets, and the OpenSearch index are present, and a minimal archive run succeeds through them.
    - The shared `infra.Start` bootstrap now provisions Terraform once, resolves every service, and health-checks them; this scenario still needs a focused assertion test.

13. `TestArchive_OutboxDrainAfterDispatcherCrash` (ADR-0020, ADR-0018) — **needs harness**
    - Given a dispatcher stopped after an outbox row is committed but before publication.
    - When the dispatcher is restarted.
    - Then the pending row drains and exactly one logical effect is observable.

## Blocked by `TRACKING.md`

- `SearchIndexingCompleted`, `SearchReady`, publication-before-indexing, and out-of-order publication facts (ADR-0014, ADR-0019, ADR-0020, ADR-0027): blocked by section 2.
- Session lifecycle, `WAITING_FOR_AUTH`, renewal, authenticated capture, and profile protection (ADR-0015, ADR-0028): blocked by section 2; `capture-login` is deployed but is not resolved or health-checked by `infra.Start` yet.
- `allowedOrigins`, seed-origin and redirect scope, politeness/rate limiting, minimum-depth correction, and unsupported `normalizerVersion` (ADR-0022, ADR-0025): blocked by section 2.
- Fine-grained `COMPLETED_WITH_ERRORS` outcomes (ADR-0014, ADR-0022): partially blocked by section 2; generic capture failure accounting exists, but authenticated-blocked, unsupported-content, and partial-with-missing-dependencies reasons do not.
- ReplayWeb.page URL resolution, offline replay navigation, and snapshot navigation (ADR-0023, ADR-0027, ADR-0029): blocked by section 2. Gateway byte-range delivery is already covered; the gap is replay-engine consumption.
- F1–F8 fault scripts, metrics, queue-based autoscaling, DLQ business reconciliation, and container/broker-outage recovery (ADR-0017, ADR-0018, ADR-0020, ADR-0021): blocked by sections 2 and 3.
