# ADR-0012: Explicit, language-neutral service contracts

- Status: Accepted
- Date: 2026-11-18

## Context

The system has Go, Python, and TypeScript services that must communicate without importing each other's implementation or domain models. Long-running captures and indexing require asynchronous work, while clients need synchronous status and search queries. The assignment requires explicit message contracts and a common message envelope.

## Decision

Define cross-service contracts in JSON Schema under `contracts/`, independently of any implementation language. Services may validate messages against these schemas but must not share private service models or implementation packages. Contracts describe observable communication, not internal storage layouts.

Use RabbitMQ for asynchronous commands and events, and HTTP for synchronous queries:

- A command requests an action from one logical service; an event reports a fact that has occurred and may have multiple independent consumers.
- Archive submission is asynchronous: the public API returns HTTP `202 Accepted` with an operation identifier, and clients query status separately.
- The gateway forwards status and search queries to the owning service over HTTP; it does not query another service's database.
- No RPC framework is introduced.

Every broker message uses this envelope:

- `messageId`: identifies one logical message for deduplication; redelivery or republication of that same message preserves its ID.
- `correlationId`: groups messages in the same distributed operation, independent of a specific message's identity.
- `type`: identifies the command or event contract.
- `version`: identifies its schema version.
- `occurredAt`: records when the logical message was produced.
- `payload`: holds the message-specific data.

Domain IDs (such as archive, page, snapshot, and attempt IDs) are distinct from the envelope's message identity. An archive ID may be used as a correlation ID when appropriate, but the fields have different meanings.

Page indexing is incremental: once a page is durably captured, its completion can be published for indexing without waiting for the entire crawl. The end of a crawl does not imply that every page has been indexed. Downstream indexing completion must therefore be established through durable accounting or explicit completion signals, not assumed from message arrival order. The indexer owns page-level indexing progress; the coordinator observes the aggregate outcome.

## Consequences

Consumers can evolve independently around explicit contracts, and one event can be routed to multiple interested services. HTTP queries introduce direct availability dependencies, so clients require bounded timeouts and defined failure responses.

Schema validation and version-aware consumption are required. The specific message catalog, payload definitions, compatibility policy, queue topology, indexing completion protocol, and compensation messages will be defined separately as their workflows are finalized. This decision does not imply global event ordering or exactly-once processing.
