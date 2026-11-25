# ADR-0016: Containerized deployment and horizontal scaling

- Status: Accepted
- Date: 2026-11-18

## Context

The distributed archive must start reproducibly on a developer's machine and demonstrate concurrent consumers, worker crashes, and dependency recovery. It uses four independently deployed application services, RabbitMQ, and AWS-compatible services provided locally by MiniStack. The assignment requires service Dockerfiles, health checks, scripted infrastructure provisioning, and a complete startup using Docker Compose.

The Python Capture service performs independently schedulable page-capture work, making it the primary candidate for horizontal scaling. Correctness must not depend on a fixed number of service replicas. Introducing a multi-host orchestrator solely for local demonstrations would add complexity without addressing the project's central distributed coordination problems.

## Decision

Use Docker Compose as the reference, single-host deployment for the entire application and its infrastructure. A single `docker compose up --build` must be sufficient to build and start the default stack, including idempotent, version-controlled provisioning of required broker topology and MiniStack resources. AWS resource topology is fixed in versioned Terraform; broker exchanges, queues, bindings, and DLQ arguments are fixed in [`infra/rabbitmq/definitions.json`](../../infra/rabbitmq/definitions.json). Services only reference provisioned broker names. Environment-specific endpoints, exposed ports, and credentials are supplied through configuration.

The deployment includes the Go Gateway, Go Archive Coordinator, Python Capture, TypeScript Search & Index, RabbitMQ, MiniStack (DynamoDB and S3), and a standalone OpenSearch container (ADR-0007). Application services have their own Dockerfiles and health endpoints. Required persistent infrastructure state must survive application container recreation; deployments must not depend on manually created queues, tables, buckets, or indexes.

Support manual horizontal scaling through Compose replica counts, especially for competing Python page-capture workers (for example, `docker compose up -d --scale capture-worker=3`). The separate interactive-login manager is initially a single Capture-owned deployment component under ADR-0028 and is **not** scaled with page workers. Scalable services must not depend on fixed container names, fixed per-replica host port mappings, process-local shared state, or stable replica identities. Additional replicas share the same contract and compete for work through RabbitMQ while coordinating durable state through their owning service's database.

The Gateway and Coordinator may start with one replica each, but their logic must remain correct if more replicas are deployed. In particular, Coordinator SAGA transitions and publication/compensation decisions must be protected by durable atomic state transitions rather than process-local locks. Increasing the number of replicas must not introduce duplicate committed effects.

Each service distinguishes process liveness from operational readiness where relevant, uses bounded connection attempts or reconnect loops for temporarily unavailable dependencies, and tolerates dependencies failing after successful startup. Compose startup ordering or health dependencies are convenience mechanisms, not substitutes for application-level recovery.

Workers support graceful termination: stop accepting new deliveries, allow bounded completion of in-flight work, and leave unfinished work recoverable through broker redelivery and durable execution state. An abrupt container kill must likewise not permanently orphan tasks. Services acknowledge messages only in accordance with their durable processing guarantees.

The deployment targets resilience to individual container or process failures on a single host. It does not claim resilience to failure of the Docker host, RabbitMQ node, or the single MiniStack instance.

## Consequences

Docker Compose provides a reproducible, inspectable environment for manual scale-out, crash demonstrations, and integration tests without requiring Kubernetes or a cloud container orchestrator. It is not a multi-host high-availability deployment, and scaling Python workers is bounded by local CPU, memory, browser processes, target-site limits, and shared infrastructure contention.

The system must recover from changing replica counts and temporary outages without manual application restarts. These are application guarantees that require idempotent consumers, durable work accounting, reconnect behavior, and execution recovery designed in their respective ADRs.

Automatic queue-based scaling is optional and is addressed in ADR-0017; Compose itself does not automatically scale consumers based on queue depth. Configurable fault injection, failure-scenario verification, and observability requirements belong in ADR-0018. This ADR does not define autoscaler policies, fault-injection mechanisms, exact Compose files, resource limits, or rollout strategies. Terraform-first infrastructure provisioning is defined in ADR-0024.
