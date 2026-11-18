# Architecture Decision Records

Architectural decisions are recorded here in numbered Markdown files.

Each ADR follows [template.md](template.md) and records one decision, its context, and its consequences. Decisions should be narrow enough to revisit independently.

Statuses: Proposed, Accepted, Superseded, Rejected. An accepted ADR documents a decision, not a claim that its implementation is complete.

## Accepted decisions

- [0001 — Single-tenant, self-hosted deployment](0001-single-tenant-deployment.md)
- [0002 — Service boundaries and implementation languages](0002-service-boundaries.md)
- [0003 — RabbitMQ for asynchronous messaging](0003-rabbitmq-messaging.md)
- [0004 — MiniStack for local AWS-compatible infrastructure](0004-ministack-infrastructure.md)
- [0005 — DynamoDB tables owned by individual services](0005-dynamodb-ownership.md)
- [0006 — S3 for archive artifacts](0006-s3-artifact-storage.md)
- [0007 — OpenSearch for full-text retrieval](0007-opensearch-retrieval.md)
- [0008 — Monorepo organization and service independence](0008-monorepo-organization.md)
- [0009 — Go for cross-service integration and end-to-end tests](0009-cross-service-testing.md)
- [0010 — Asynchronous HTTP API with durable admission](0010-asynchronous-http-api.md)
- [0011 — Core domain model and archival semantics](0011-core-domain-model.md)
- [0012 — Explicit, language-neutral service contracts](0012-language-neutral-contracts.md)
- [0013 — DynamoDB-backed distributed crawl frontier](0013-distributed-crawl-frontier.md)
- [0014 — Archive lifecycle and orchestrated SAGA](0014-archive-lifecycle-saga.md)
- [0015 — Interactive authentication and resumable capture](0015-interactive-authenticated-capture.md)
- [0016 — Containerized deployment and horizontal scaling](0016-containerized-deployment-scaling.md)

See [testing conventions](../testing.md) for behavioral test-writing rules.

More involved decisions, including URL identity and normalization, exact crawl depth semantics, concurrency limits, detailed SAGA protocols, and delivery guarantees, will be documented separately.
