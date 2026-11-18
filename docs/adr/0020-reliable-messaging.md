# ADR-0020: Reliable messaging and idempotent processing

- Status: Accepted
- Date: 2026-11-18

## Context

RabbitMQ delivers asynchronous commands and events across the independently deployed services. A producer can commit a database change and crash before publishing its corresponding message; a consumer can commit an effect and crash before acknowledging delivery. Network outages can also make publication outcomes uncertain. The assignment requires at-least-once delivery, atomic registration of processed message identities with their corresponding database effects, bounded poison-message handling, and recovery after broker outages.

RabbitMQ and DynamoDB cannot share one atomic transaction. Likewise, DynamoDB transactions do not atomically cover S3 uploads or OpenSearch writes. Exactly-once message execution cannot be assumed.

## Decision

### Durable publication through a transactional outbox

Each service that emits a message as a consequence of a durable state change records the outgoing logical message in a service-owned DynamoDB outbox in the **same transaction** as the state change. The outbox entry includes the established message envelope and its stable `messageId`.

One or more replica-safe dispatchers publish pending entries to RabbitMQ using persistent messages, durable routing infrastructure, and publisher confirms. An entry is marked published only after the broker confirms acceptance; if confirmation is lost or the dispatcher crashes, the **same logical message with the same `messageId`** may be republished. Outbox claiming and status changes must tolerate multiple dispatcher instances. Unroutable publication must not count as successful delivery; routing guarantees or mandatory-return handling must be verified.

State changes that admit frontier work, transition an archive SAGA, or report a captured page follow this rule. The initial synchronous HTTP admission defined by ADR-0010 still durably registers the run before responding `202`; subsequent asynchronous commands are published through its outbox.

### Durable consumption and idempotency

Consumers use explicit acknowledgements and at-least-once processing. For a message whose business effects reside in one service-owned DynamoDB transaction, insert its processed `messageId` conditionally in the **same transaction** as the relevant business-state changes and any resulting outbox messages. A repeated logical message must not apply its effects again; an already-processed delivery can be acknowledged.

The `messageId` deduplicates deliveries of the same logical message, but business operation identities (for example `archiveId`, `taskId`, or `snapshotId`) must also protect against semantically duplicate work initiated through distinct messages. Processing claims and state transitions must remain safe with concurrent consumer replicas.

For effects outside DynamoDB, such as S3 artifact storage and OpenSearch indexing, consumers use durable processing state, stable operation/artifact identities, idempotent writes where possible, and reconciliation after crashes. A processed-message entry must not be committed as evidence that an external effect succeeded before that effect is durably accounted for. Inbox state may distinguish accepted or in-progress work from fully processed work. A RabbitMQ acknowledgement is allowed only after responsibility for the work and required recovery information have been durably secured. These protocols must satisfy R1 without claiming cross-system exactly-once execution.

### Retries, dead letters, and recovery

Classify failures as transient, terminal business outcomes, or invalid/non-retryable messages. Retry transient delivery or processing failures with bounded attempts and delayed backoff; avoid infinite immediate requeue loops. Route exhausted or invalid poison messages to a dead-letter queue with sufficient non-secret diagnostic context. Malformed, non-retryable payloads may be dead-lettered without repeatedly executing them.

Dead-lettering is a transport outcome, **not** automatically a terminal capture/indexing or SAGA outcome. Services must durably account for unresolved operations and reconcile or notify their owning workflow instead of silently abandoning business work.

Clients and dispatchers automatically reconnect after RabbitMQ interruption without manual service restarts. During broker downtime, outbox records remain durable; after recovery they are published and eventually drained. Consumers tolerate redelivery and resume processing without duplicating committed effects. Message processing and retry policies must not depend on a fixed number of replicas or on a particular delivery order.

The common message envelope and language-neutral schemas remain those of ADR-0012. Queue/exchange topology, per-message retries, and compatibility/version handling are defined separately.

## Consequences

The system offers at-least-once asynchronous delivery with idempotent committed business effects, not exactly-once message execution. Messages may be published or consumed more than once; dispatcher and consumer crashes are handled by durable outbox/inbox state and recovery.

Each message-producing and message-consuming service needs additional DynamoDB records, conditional transactions, retry/reconciliation processes, and operational visibility into outbox backlog and DLQs. Transaction size limits and external side effects require deliberate boundaries. Detailed schemas, retention periods, timeout values, RabbitMQ topology, and individual reconciliation algorithms are deferred.
