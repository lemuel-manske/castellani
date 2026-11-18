# ADR-0007: OpenSearch for full-text retrieval

- Status: Accepted
- Date: 2026-11-18

## Context

The primary deliverable is preserved, replayable historical content; a complementary derived capability is full-text search across archived snapshots. DynamoDB can store metadata but is not intended to provide the full-text retrieval capabilities needed for that workload.

## Decision

Use the AWS OpenSearch Service-compatible interface through MiniStack for the Search and Index service's search index. The TypeScript service will own indexing and query behavior. OpenSearch stores a derived, searchable representation; it is not the authoritative store for raw captured artifacts.

## Consequences

Full-text search can be developed separately from archive artifact storage and workflow state. Search projections must be rebuilt or repaired when indexing fails. A working OpenSearch data plane, not just successful domain-creation API calls, must be verified in the local environment. Unified query ownership and result scope are addressed in ADR-0029; asynchronous indexing and repair are addressed in ADR-0019. Exact index mappings, diff algorithms, and query ranking remain implementation decisions.
