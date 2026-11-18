# ADR-0021: Distributed concurrency control and browser capacity reservations

- Status: Accepted
- Date: 2026-11-18

## Context

Multiple Capture replicas concurrently discover and claim pages, and Coordinator replicas may observe conflicting or delayed SAGA events. RabbitMQ messages can be duplicated and work can outlive the worker's execution authorization. Process-local mutexes cannot enforce invariants across replicas.

Browser execution also consumes finite CPU and memory. The assignment requires a demonstrable scarce-resource race in which 100 simultaneous contenders compete for 10 units and exactly 10 reservations succeed. A per-container browser limit would not protect the deployment-wide capacity when Capture scales horizontally.

## Decision

### Atomic transitions and execution ownership

Use service-owned DynamoDB conditional writes and transactions as the authority for conflicting distributed state transitions. Frontier URL admission and crawl limits are governed by ADR-0013; Coordinator SAGA transitions and irrevocable publication/compensation decisions follow ADR-0014. No correctness invariant may rely solely on process-local locks, a singleton worker, or RabbitMQ's normal competing-consumer behavior.

Execution claims are temporary leases, not perpetual ownership. Acquiring or renewing a claim conditionally records its owner, expiry, and an incremented monotonic fencing generation. A competing replica may reclaim expired work according to the recovery policy. Every authoritative result commit must conditionally verify the current execution generation and permitted task/SAGA state; late attempts must not overwrite a newer authorized result or resurrect compensated work.

An `attemptId` identifies a concrete execution attempt; a fencing generation determines which attempt is still authorized. Checks against DynamoDB do not atomically fence independent S3/OpenSearch operations. External effects therefore use attempt-scoped or otherwise safely identifiable staging, idempotent writes, guarded publication, and cleanup/reconciliation when stale work arrives.

### Global browser execution capacity

The Python Capture service owns a **deployment-wide browser-execution reservation pool** whose capacity is configurable and set to **10 slots for the required F5 demonstration**. A reservation represents authorization to occupy one unit of concurrent browser-execution capacity; it is not a guarantee that capturing a page will succeed.

All Python replicas acquire reservations through atomic DynamoDB operations against shared service-owned capacity state. The allocation protocol must guarantee that active reservations never exceed the configured capacity, even under concurrent requests and crashes. Reservation identity, lease expiry, renewal, and conditional release prevent double allocation, unauthorized releases, and permanently leaked slots.

Normal page-capture tasks wait or reschedule when capacity is full; lack of an immediately available slot is not a terminal page failure. Workers must acquire capacity before starting an authorized browser execution and release it after completion, cancellation, or safe recovery. Reservations are distinct from page-task ownership: a task claim alone does not consume a browser slot, and a capacity lease does not authorize a stale task attempt to commit results.

For F5, expose a deterministic, nonblocking reservation contention scenario starting with an empty pool of ten slots. One hundred simultaneous contenders each attempt to acquire a slot once, without automatic retries before the measurement. Exactly ten acquisitions must succeed and ninety must fail to reserve; each successful reservation has a unique identity and the pool never exceeds ten active slots. Keep successful reservations held until all contenders finish so releases cannot permit additional successes during the same test. Ordinary crawls use waiting/retry semantics instead of failing ninety pages.

### Replica-independent correctness

The concurrency design must remain valid when Capture scales to three or more consumers and when multiple Coordinator instances execute. Repeated conditional operations and release requests must be idempotent. Expired leases must not be treated as proof that an old worker has stopped executing; stale execution fencing remains mandatory.

The reservation pool coordinates logical browser capacity across Capture replicas on the reference single-host deployment. It is not a host-level CPU or memory scheduler, and its capacity configuration must respect actual machine resources and target-site limits. A future multi-host deployment may need a more granular host-capacity model without changing the invariant that workers cannot exceed authorized capacity.

## Consequences

DynamoDB provides atomic coordination without a dedicated central Python scheduler or application-managed distributed lock service. This preserves replica independence but introduces contention on shared capacity records, lease management, and additional write costs. An implementation must avoid exceeding DynamoDB transaction/conditional-write limits while providing the capacity invariant.

Leases enable recovery after worker crashes; fencing prevents late attempts from corrupting committed state. Neither mechanism alone makes external S3/OpenSearch effects transactional, so staging and reconciliation are necessary.

This ADR defines the required invariants, not the exact DynamoDB keys, counter-versus-slot allocation algorithm, lease durations, heartbeats, fairness policy, retry delays, or browser-resource sizing. The atomic F5 protocol and stale-attempt behavior will be verified under ADR-0018.
