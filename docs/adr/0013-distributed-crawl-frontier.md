# ADR-0013: DynamoDB-backed distributed crawl frontier

- Status: Accepted
- Date: 2026-11-18

## Context

An archive run begins with a seed URL and discovers additional pages while crawling. The complete set of URLs is not known in advance. Multiple replicas of the Python Capture service must capture pages concurrently, admit newly discovered work, avoid duplicate logical tasks, enforce crawl limits, and determine when the crawl has finished.

An in-memory URL queue cannot coordinate replicas or survive their termination. RabbitMQ can distribute deliveries but does not, by itself, provide authoritative crawl-wide URL admission, deduplication, limits, or completion state. A designated Python scheduler would introduce an unnecessary process-level coordination point.

## Decision

The Python Capture service owns a distributed crawl frontier. The frontier is a logical component implemented by Python code operating on service-owned, durable DynamoDB state; it is not a separate microservice, leader process, or queue.

- Each Python replica may consume page-capture tasks, discover links, and attempt to admit new URLs into the frontier.
- DynamoDB is authoritative for admitted URLs, page-task state, execution ownership, and crawl progress. Replicas coordinate using atomic conditional writes or transactions, not direct replica-to-replica communication.
- RabbitMQ distributes pending capture tasks to competing Python consumers. The broker is a delivery mechanism, not the source of truth for which pages exist or have finished.
- The frontier grows as pages are captured. Newly admitted tasks are durably recorded along with an intention to publish their capture commands, so a process failure between state persistence and publication cannot silently lose work.
- Admission is scoped to an archive crawl: one logical page has at most one admitted task within that crawl. A new archive run can capture the page again as a new historical version. Admission must enforce configured crawl limits atomically even when replicas discover links concurrently.
- Traversal is opportunistic and concurrent. Eligible discovered pages may be scheduled immediately; workers do not wait for all pages at a shallower depth to finish.
- A page task may reach a terminal state only once its capture outcome and discovery/admission work have been durably accounted for. New child tasks must be durably admitted before the parent becomes terminal.
- Crawl termination is derived from authoritative, durable accounting of admitted and terminal tasks, not RabbitMQ queue emptiness. The terminal decision must exclude subsequent admission of new work.
- Capture and indexing progress independently: a durably captured page may be announced for indexing before the overall crawl terminates. Go observes the aggregate crawl outcome without owning individual page scheduling.

## Consequences

Any Python replica can contribute work without a dedicated scheduler, and a crashed replica does not erase frontier state. Atomic admission prevents duplicate logical tasks and exceeding crawl limits. Shared DynamoDB state introduces write contention, particularly around crawl-wide limits and completion accounting; this is an accepted trade-off for the expected workload.

Opportunistic traversal does not guarantee that the first discovered depth of a page is its shortest link distance. The frontier must not assume discovery order establishes minimum depth. The policy and mechanism for handling later, shorter paths will be specified with depth-limit semantics.

A terminal crawl is not necessarily a successful crawl: failed or skipped page tasks may be terminal, while acceptance of partial results is governed by a separate policy.

This ADR does not define DynamoDB keys, URL normalization and page equivalence, precise depth-correction rules, execution leases and fencing, retries, outbox mechanics, per-page failure policy, or the final snapshot commit protocol. These require separate decisions.
