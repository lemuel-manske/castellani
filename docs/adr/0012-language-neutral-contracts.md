# ADR-0012: Explicit, language-neutral service contracts

- Status: Accepted
- Date: 2026-11-18

## Context

The system has Go, Python, and TypeScript services that must communicate without importing each other's implementation or domain models. Long-running captures and indexing require asynchronous work, while clients need synchronous admission, status, and search operations. The assignment requires explicit message contracts and a common message envelope.

## Decision

Define cross-service contracts in JSON Schema under `contracts/`, independently of any implementation language. Services validate inbound broker messages against these schemas at runtime and must not share private service models, generated validators, or implementation packages. Contracts describe observable communication, not internal storage layouts.

Use RabbitMQ for asynchronous commands and events, and HTTP for synchronous operations:

- A command requests an action from one logical service; an event reports a fact that has occurred and may have multiple independent consumers.
- Archive admission is a synchronous HTTP call from the Gateway to the Coordinator. The Coordinator durably registers the operation before the Gateway returns `202 Accepted` to the client, as specified in [ADR-0010](0010-asynchronous-http-api.md). Subsequent crawl and indexing work is asynchronous.
- The Gateway forwards status and search queries to the owning service over HTTP; it does not query another service's database.
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

Consumers can evolve independently around explicit contracts, and one event can be routed to multiple interested services. HTTP admission and queries introduce direct availability dependencies, so clients require bounded timeouts and defined failure responses.

Schema validation and version-aware consumption are required. The versioned message catalog, payload schemas, fan-out routing, and compatibility rules are specified in [message contracts](../../contracts/messages/README.md); public HTTP operations are specified in [OpenAPI 3.1](../../contracts/openapi/api.yaml). The detailed implementation of RabbitMQ queues, retry scheduling, and dead-letter transport remains deployment configuration. This decision does not imply global event ordering or exactly-once processing.
