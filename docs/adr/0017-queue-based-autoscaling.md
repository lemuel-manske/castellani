# ADR-0017: Optional queue-based autoscaling of capture workers

- Status: Accepted
- Date: 2026-11-18

## Context

The Python Capture service performs page-level work through a RabbitMQ queue. ADR-0016 establishes manual horizontal scaling with Docker Compose and requires correctness across changing replica counts. A sustained backlog may justify adding workers, while idle replicas consume limited local CPU and memory, especially when running browser instances.

The assignment offers an optional bonus for automatically scaling consumers according to queue length. Docker Compose supports explicit replica counts but has no built-in queue-based autoscaler. Introducing Kubernetes solely for this behavior would add disproportionate operational complexity.

## Decision

Support an **optional, separately operated autoscaling controller** for Python Capture replicas. The default Docker Compose deployment must work without the controller; manual replica scaling remains supported and sufficient for ordinary operation. Autoscaling is an optimization, not a prerequisite for crawl progress, failover, or correctness.

The controller observes RabbitMQ capture queue metrics through its management interface. Ready-message backlog is its primary scale-out signal; unacknowledged deliveries, observed processing capacity, and worker health may inform scale-in decisions. Queue length is only a workload indicator, never an authoritative measure of frontier progress or completion: DynamoDB remains the crawl frontier's source of truth under ADR-0013.

The controller periodically computes a bounded desired replica count using configurable minimum and maximum limits. It increases replicas when backlog is sustained relative to available workers, and reduces replicas conservatively after sustained low demand. Scaling decisions require smoothing or hysteresis and cooldown periods to avoid rapid oscillation. The exact formula, sampling interval, and thresholds are implementation details.

The reference implementation may run as a separate host-side process invoking supported Docker Compose scaling operations. No application worker is given Docker daemon privileges. Any component that can control Docker must have its access scope and security implications documented; the Docker socket must not be mounted into arbitrary application services. The optional controller must not interfere with the default single-command deployment.

Scale-in uses the graceful worker shutdown contract of ADR-0016. Workers stop accepting new work and are given a bounded opportunity to finish; interrupted deliveries and expired execution claims remain recoverable through RabbitMQ and durable task state. Forced termination, duplicate deliveries, and stale attempts must not create duplicate committed captures. Scaling must not bypass website rate limits, per-run resource bounds, or host resource constraints.

The controller exposes its observed backlog, current and desired replica counts, scaling decisions, and reasons through logs or metrics. A demonstration must show that an induced backlog changes the replica count automatically, that tasks are distributed among replicas, and that completed capture effects remain unique. Manual F8 scale-out must continue to work when the controller is disabled.

## Consequences

Autoscaling can demonstrate adaptive resource allocation without coupling archive workflows to a container orchestrator. Its effects are constrained by a single Docker host, browser memory usage, website throughput, shared DynamoDB/RabbitMQ capacity, and the overhead of starting browser workers. Additional replicas do not guarantee proportional throughput.

The controller is an additional operational component with access to privileged deployment operations. It must remain optional and isolated from application data and SAGA decisions. Its absence, crash, or incorrect capacity estimate must not lose work or corrupt archive state.

This ADR does not prescribe a specific queue-depth formula, Docker API implementation, target throughput, cooldown duration, or resource budget. Fault injection and correctness verification are defined in ADR-0018.
