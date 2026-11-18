# ADR-0003: RabbitMQ for asynchronous messaging

- Status: Accepted
- Date: 2026-11-18

## Context

The archive coordinates long-running captures and indexing across independently deployed services. It needs work queues where multiple Python replicas compete for page-capture tasks, and events that can be delivered to multiple interested services. Consumers must recover from crashes and temporary broker outages.

The assignment permits RabbitMQ, Kafka, or an AWS messaging service such as SQS/SNS. We do not currently need a retained, replayable event log or stream-processing features that would justify Kafka. SQS/SNS could satisfy the messaging requirements, but combining queues and event fan-out would require multiple AWS messaging primitives. RabbitMQ provides both patterns through exchanges and queues in one locally operated broker, independent of MiniStack's emulated AWS services.

## Decision

Use RabbitMQ, running in its own Docker container, for asynchronous communication between services.

RabbitMQ is chosen specifically for:

- Work distribution: a queue can deliver page-capture tasks to competing Python consumers, allowing replicas to scale without partitioning tasks manually.
- Event fan-out and routing: exchanges can route one published event to distinct queues owned by interested services. Each service receives its own copy without competing with the others.
- Failure handling: manual acknowledgements, publisher confirms, durable queues and messages, and dead-letter routing provide the building blocks for retries and recovery.
- Local operability: RabbitMQ is straightforward to run, inspect, stop, and restart in Docker Compose for the assignment's live failure scenarios.

Cross-service commands and events will use explicit JSON contracts stored under `contracts/`, with the required envelope: `messageId`, `correlationId`, `type`, `version`, `occurredAt`, and `payload`. No RPC framework will be introduced.

## Consequences

RabbitMQ is an additional broker to deploy and operate rather than an AWS-managed messaging service. Its queues are primarily for delivering work and notifications, not for long-term event retention or arbitrary replay as with an event log.

Publisher confirms and acknowledgements do not provide end-to-end exactly-once processing. Consumers must handle redelivery idempotently, and services must reliably publish events associated with committed state changes. Reconnection, retry policies, dead-letter handling, and exact exchange/queue topology will be specified and tested separately.
