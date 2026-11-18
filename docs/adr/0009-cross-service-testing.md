# ADR-0009: Go for cross-service integration and end-to-end tests

- Status: Accepted
- Date: 2026-11-18

## Context

The system must demonstrate correct behavior across HTTP APIs, asynchronous processing, container failures, competing consumers, broker outages, and recovery. These scenarios need an executable test suite that can control infrastructure and verify results through observable behavior.

The services use different languages, and choosing one language for system-level tests must not force all service-local tests to use it.

## Decision

Use a dedicated Go module under `tests/` for cross-service integration and end-to-end tests, with:

- Go's standard `testing` package as the runner.
- `testify/assert` and `testify/require` for assertions.
- Testcontainers for Go where programmatic container lifecycle control is useful.
- The application's Docker Compose environment for full-system end-to-end runs, avoiding a parallel definition of the production topology.

Go supports concurrent workload tests and infrastructure fault orchestration without adding another implementation language. System-level tests will use explicitly named behavior scenarios, concise setup/action/assertion sequences, isolated fixtures with automatic cleanup, and assertions against observable outcomes. Non-recoverable setup failures should stop the test immediately; independent outcome checks should remain readable. Integration tests requiring external infrastructure can be gated separately from ordinary unit tests, for example with Go build tags.

Each service retains unit and service-local integration tests in its implementation language (Go `testing`, Python `pytest`, and TypeScript `Vitest`). Cross-service tests should interact with documented APIs and contracts rather than import service implementation packages.

Detailed, language-independent test conventions are maintained in [../testing.md](../testing.md).

## Consequences

System-level tests have one consistent runner, assertions, and infrastructure test harness. Managing a separate Go module adds a small amount of dependency configuration but avoids coupling the tests to the coordinator or gateway module. Container-backed tests require Docker and may be slower than service-local tests; they should be isolated, reproducible, and run separately where appropriate.
