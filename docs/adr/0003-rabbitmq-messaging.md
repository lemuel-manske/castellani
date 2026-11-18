# ADR-0003: RabbitMQ for asynchronous messaging

- Status: Accepted
- Date: 2026-11-18

## Context

The assignment requires event-coordinated services, competing consumers, and recovery from broker outages. Long-running web captures should not hold open an HTTP request until processing finishes.

## Decision

Use RabbitMQ as the message broker, running as a dedicated container. Cross-service commands and events will use explicit JSON contracts, stored under `contracts/`, with the assignment's required common envelope: `messageId`, `correlationId`, `type`, `version`, `occurredAt`, and `payload`.

No RPC framework will be introduced. RabbitMQ will distribute capture work to competing consumers.

## Consequences

Messages may be delivered more than once, so consumers must be idempotent. Reconnection, durable publication, acknowledgements, retries, and dead-letter handling must be implemented and tested. Queue topology and exact delivery mechanisms will be specified in later ADRs; choosing RabbitMQ alone does not guarantee reliable delivery.
