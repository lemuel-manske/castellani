# ADR-0007: OpenSearch for full-text retrieval

- Status: Accepted
- Date: 2026-11-18

## Context

The primary deliverable is preserved, replayable historical content; a complementary derived capability is full-text search across archived snapshots. DynamoDB can store metadata but is not intended to provide the full-text retrieval capabilities needed for that workload.

## Decision

Use the AWS OpenSearch Service-compatible client interface for the Search and Index service's search index. Locally, OpenSearch runs in its own standalone `opensearchproject/opensearch` container started by Compose, separate from MiniStack: MiniStack provides the AWS-compatible DynamoDB and S3 endpoints, while OpenSearch is a real self-hosted instance rather than an emulated domain. This was chosen deliberately to exercise production-like OpenSearch behavior in tests without depending on MiniStack's OpenSearch emulation. The endpoint is supplied through configuration, so a managed AWS OpenSearch Service endpoint can be substituted without changing Search. The TypeScript service will own indexing and query behavior. OpenSearch stores a derived, searchable representation; it is not the authoritative store for raw captured artifacts.

## Consequences

Full-text search can be developed separately from archive artifact storage and workflow state. Search projections must be rebuilt or repaired when indexing fails. The local stack runs one additional container and does not manage OpenSearch through Terraform; index setup and the OpenSearch data plane are exercised directly. Search depends on that container being healthy, but archive replay does not depend on search availability. Unified query ownership and result scope are addressed in ADR-0029; asynchronous indexing and repair are addressed in ADR-0019. Exact index mappings, diff algorithms, and query ranking remain implementation decisions.
