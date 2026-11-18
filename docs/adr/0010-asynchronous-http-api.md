# ADR-0010: Asynchronous HTTP API with durable admission

- Status: Accepted
- Date: 2026-11-18

## Context

Archiving a website may take substantial time. HTTP clients need prompt acknowledgement and a reliable way to check progress without waiting for crawling and indexing to finish.

If the gateway were to respond after publishing a message but before the coordinator registered the operation, an immediate status query could report an unknown archive despite the accepted request. Adding temporary gateway storage to close this gap would split ownership of archive admission between two services.

## Decision

The API Gateway synchronously forwards archive submission to the Archive Coordinator over HTTP. The Coordinator durably registers the operation in its own database before acknowledging admission. Only then does the Gateway return HTTP `202 Accepted` with a public archive operation identifier and a status resource reference.

Acceptance means that the operation is registered for asynchronous execution, not that crawling or indexing has begun or completed. The Coordinator is responsible for initiating downstream work reliably after registration; the exact publication mechanism is documented separately.

Clients query operation status through HTTP. The Gateway forwards status queries to the Coordinator rather than reading its database. Search queries likewise use HTTP to reach the owning service. HTTP polling is the initial progress mechanism; Server-Sent Events may be added later without replacing the authoritative status endpoint.

The Gateway remains stateless. An admission failure must not be reported as successful acceptance. Public HTTP operations are specified in [OpenAPI 3.1](../../contracts/openapi/api.yaml). The client must supply an `Idempotency-Key` on `POST /archives`; the Coordinator durably maps a key and canonical request fingerprint to one accepted run. The same key with an identical request returns the same accepted archive; the same key with a different request fails with HTTP `409`. Keys are retained for at least 24 hours. Public errors follow RFC 9457 Problem Details, and collection/run status distinguishes archive completion from search readiness.

## Consequences

A successfully accepted archive has an authoritative durable record, so immediate status queries do not depend on whether RabbitMQ has delivered an admission message. The submission path now depends synchronously on Coordinator availability and database access; it needs bounded timeouts and clear failure responses. Network failures after registration but before the client receives a response may leave an uncertain outcome, which submission idempotency must address in a later design.

The longer-running workflow remains asynchronous and message-driven. This deliberate HTTP admission boundary does not introduce an RPC framework, a Gateway database, or a requirement for a singleton Coordinator.
