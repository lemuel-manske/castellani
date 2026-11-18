# ADR-0018: Fault injection and failure verification

- Status: Accepted
- Date: 2026-11-18

## Context

The distributed archive must prove correct behavior under service crashes, duplicate and malformed messages, dependency outages, concurrent access to scarce resources, delayed results, and horizontal scaling. The assignment requires configurable simulated dependency latency and failure rates and a live demonstration of its F1–F8 failure scenarios. These behaviors cannot be established merely by showing that containers restart or that logs contain errors.

The system uses at-least-once messaging, durable per-service state, an orchestrated SAGA, and a distributed crawl frontier. Failures can occur between state writes and message publication, after work is performed but before acknowledgement, or after a SAGA decides to compensate. Tests must inspect durable effects and client-visible outcomes, not assume correctness from delivery order or the absence of exceptions.

## Decision

Provide a reproducible failure-testing facility consisting of configurable fault injection, versioned scenario scripts, and automated correctness assertions. It is available in local/test deployments and disabled by default in normal operation.

### Fault injection

Expose environment-configurable latency and failure rates at explicitly named dependency or workflow boundaries. Fault points must include relevant capture, indexing, and messaging operations, and support deterministic scenarios for a selected archive, task, or message where needed. Each injected fault is recorded in structured logs with its point and correlation identity.

Fault injection must not require editing source code, compromise another service's private database, or create hidden backdoors in production paths. Deployment configuration controls which fault points are enabled. Random failures can exercise resilience, but scripted tests use fixed behavior or seeded randomness for reproducibility. Timeouts, retry budgets, and failure classification must remain explicit; a simulated transient outage must not silently turn into an unrecoverable page failure.

### Required failure scenarios

Provide scripts or test fixtures that execute and verify the assignment's failure scenarios against the running stack:

- **F1 — Compensation:** Force a genuinely run-wide, pre-publication failure after partial side effects exist. Verify the SAGA passes through `COMPENSATING`, that staged artifacts and index documents are removed or inaccessible, that failure metadata remains, and that it reaches `COMPENSATED` only after cleanup confirmations. An ordinary secondary-page failure must instead remain isolated under ADR-0014.
- **F2 — Consumer crash:** Kill a Capture consumer during a task. Verify eventual redelivery or recovery by another replica or after restart, with one logical committed capture outcome.
- **F3 — Duplicate delivery:** Republish one logical message with the same `messageId` five times. Verify that deduplication and the durable effect are committed atomically, resulting in one effect.
- **F4 — Poison message:** Deliver an invalid or unsupported message. Verify bounded failure handling and dead-letter routing, and that valid messages continue processing. Invalid non-retryable payloads need not be retried pointlessly.
- **F5 — Scarce-resource race:** Start 100 concurrent contenders for a domain-defined capacity of 10. Verify exactly 10 reservations succeed and 90 are rejected or compensated, with no double allocation. The domain resource and reservation protocol require a separate decision; this ADR does not invent them.
- **F6 — Broker outage:** Stop RabbitMQ temporarily (the assignment demonstrates approximately 30 seconds). Verify applications reconnect without manual restarts, durable outgoing work eventually drains after recovery, and no committed work is silently lost.
- **F7 — Late result:** Inject dependency latency beyond an execution timeout or lease expiry. Verify that stale results cannot reverse a compensation decision or overwrite a newer authorized outcome and that any late side effects are reconciled or compensated as required.
- **F8 — Horizontal scaling:** Run three competing consumer replicas on the same queue. Verify observable task distribution and unique committed effects, independently of optional automatic scaling.

Scenarios must be repeatable without assuming that one replica always receives a particular RabbitMQ delivery. Injected container crashes and broker outages are orchestration actions executed by versioned scripts rather than application business logic.

### Assertions and evidence

Each scenario defines setup, fault trigger, expected state transitions, bounded recovery condition, and cleanup. Tests assert both client-facing outcomes and the authoritative durable state owned by the relevant services. Examples include SAGA and compensation records, frontier task uniqueness, processed-message deduplication, S3 artifact existence or deletion, OpenSearch visibility, outbox backlog, and dead-letter queue contents.

Avoid unbounded sleeps and timing-dependent assertions; wait for observable conditions with deadlines. Do not infer that an empty RabbitMQ queue proves crawl completion. The testing conventions in `docs/testing.md` apply to cross-service integration and end-to-end tests.

Services emit structured logs with service and replica identities plus applicable `correlationId`, `messageId`, archive/run ID, task ID, and attempt ID. Expose enough queue, outbox, crawl, SAGA, retry, and compensation metrics to explain recovery. Sensitive authentication material must remain excluded from logs, metrics, and test evidence.

Scenario entry points and expected outcomes are documented so an operator can invoke a selected failure during the live demonstration and identify the relevant logs and state assertions. Infrastructure preparation and test fixtures must be recreated from versioned code rather than manual console changes.

## Consequences

Fault tolerance becomes a verifiable system property rather than an informal implementation intention. Deliberately causing failures exercises eventual recovery paths and clarifies the difference between an acceptable page-level error, a run-wide SAGA rollback, and infrastructure interruption.

The test facility increases implementation and maintenance work and may need privileged local control to stop containers or brokers. That privilege belongs to explicitly invoked test scripts, not normal application services. Exact fault-point names, scripts, dashboards, metrics libraries, timing defaults, and a domain-specific F5 reservation design are deferred to implementation or their own ADRs.
