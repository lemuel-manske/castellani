# ADR-0002: Service boundaries and implementation languages

- Status: Accepted
- Date: 2026-11-18

## Context

The assignment requires at least four microservices in at least three languages. The archive needs separate responsibilities for HTTP entry, long-running workflow coordination, page capture, and retrieval.

## Decision

Use four logical microservices:

- API Gateway (Go): stateless REST entry point and request validation.
- Archive Coordinator (Go): archive-job lifecycle and cross-service workflow coordination.
- Capture (Python): page discovery, browser capture, and crawl-specific processing.
- Search and Index (TypeScript): full-text indexing, querying, and historical retrieval.

Each service is deployed independently and has its own health check. Replicas of the Capture service may execute page-level work concurrently.

## Consequences

The gateway requires no application database. The coordinator need not implement crawler-specific URL rules. Service-to-service boundaries introduce event contracts and operational complexity, but allow failures and scaling to be demonstrated independently. Detailed state machines, internal module boundaries, and crawl-frontier algorithms remain separate decisions.
