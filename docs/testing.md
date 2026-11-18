# Testing conventions

These rules apply across Go, Python, TypeScript, and system-level tests. Use idiomatic tooling for each language while preserving the same behavioral focus and readability.

## Behavior, not implementation

Tests must verify observable behavior, user interactions, documented contracts, and correctness invariants. Do not couple tests to incidental implementation details such as internal functions, private storage layouts, CSS classes, or styling.

For UI tests, prefer semantic queries and assertions (such as accessible role/name, visibility, and enabled state) over selectors or matchers such as `toHaveClass` or `toHaveStyle`. Visual-regression and snapshot-based visual testing are out of scope for now.

For backend tests, assertions against public APIs, message contracts, and domain outcomes are preferred. Infrastructure assertions are appropriate where infrastructure behavior itself is the requirement (for example, redelivery, queue isolation, or broker recovery); avoid relying on unrelated internal details.

## The more integrated, the better

Do not create so isolated tests that they fail to exercise the system's real behavior.

Integration and end-to-end tests are preferred over classic unit tests, and service-local tests are preferred over cross-service tests.

Use **test doubles** only for isolated behavior tests, and prefer real infrastructure for integration and end-to-end tests.

## Readability and organization

- Tests should read like a specification: a recognizable situation, one action (or workflow), and observable outcomes. The reader should not need to understand HTTP clients, transport setup, fixture storage, or container orchestration to understand the scenario.
- Start test files with tests of primary, observable behavior; follow with exceptional, boundary, and recovery scenarios.
- Give each meaningful scenario its own explicitly named test. Name tests for the action or precondition and expected behavior, not the internal method being exercised. For example, `TestArchive_BrokerUnavailable_RecoversWithoutLosingWork`.
- Do not generate test cases with loops, tables, or dynamic parameterization. Write each distinct test case explicitly. Ordinary loops within a single scenario are allowed for workloads such as 100 concurrent requests.
- Keep a clear progression: establish a fixture and preconditions, perform the action, then verify the outcome. Use straightforward test bodies rather than deep nesting or helper abstractions that hide the behavior under test.
- Prefer small, focused tests with direct, meaningful assertions. Assertions should explain the behavior being guaranteed, not merely check that execution did not panic.
- Put reusable setup, HTTP request construction, server/container startup, response decoding, and cleanup into intention-revealing helpers. Do not hide a test's behavioral assertions or the action being tested inside those helpers.
- Avoid repeated inline mock handlers or anonymous callback plumbing for the same scenario. Prefer a named fixture behavior such as `coordinator.Accept` or `gateway.Submit`; use inline handlers only when behavior is genuinely specific to one test.
- Prefer fixture builders or small test doubles that model a real boundary and can record observable calls. They should not reproduce application business logic.
- Keep a test's fixtures minimal: do not introduce general-purpose configuration frameworks, extensive builder chains, or helper APIs that make the scenario harder to read.

## Assertions and failures

- Stop immediately when a prerequisite fails and subsequent assertions cannot be meaningful (for example, failure to create an archive or start a fixture). In Go, use `github.com/stretchr/testify/require` for these checks.
- Use non-fatal assertions for independent properties that can be meaningfully evaluated together. In Go, use `github.com/stretchr/testify/assert`.
- Assert concrete results and invariants. A successful command response or event publication alone is not proof that a distributed operation completed correctly.
- Prefer verifying both the presence of intended effects and the absence of prohibited effects, especially for idempotency, compensation, and concurrent processing.
- Do not write `if` statements to branch around test assertions or prerequisites. Use `require` and `assert` directly, with a clear separation of fatal and non-fatal checks.
- Do not silently discard fixture errors. Fail at the fixture setup boundary when a prerequisite cannot be established.

## Determinism and lifecycle

- Avoid arbitrary sleeps for synchronization. Wait for observable conditions using bounded polling, explicit readiness checks, and deadlines.
- Tests must be isolated, create unique identifiers or resources where necessary, and not depend on execution order.
- Fixtures that create temporary files, containers, services, or network changes must register cleanup so it runs even if assertions fail. In Go, use `t.Cleanup` and mark reusable helpers with `t.Helper`.
- Do not share mutable fixture state across tests. Use per-test fakes or recorders and synchronization where request handlers run concurrently.
- Integration tests that require real dependencies should be distinguishable from fast unit tests; Go build tags such as `integration` are acceptable.
- Prefer real infrastructure in integration and end-to-end tests. Test doubles are appropriate for isolated behavior tests, but must not replace the real broker or database when their failure or concurrency semantics are under test.
- Failure tests should establish normal behavior, introduce a controlled fault, verify the degraded state where relevant, remove the fault, and assert recovery or a valid terminal state.
- Ensure cleanup and recovery are verified rather than leaving hidden effects that can contaminate subsequent tests.

## Test placement and fixtures

- Service-local unit and integration tests stay alongside the respective service source.
- Place **reusable, service-scoped fixtures** in one dedicated test-support package (for example, `internal/gatewaytest/`), following the purpose-specific `*test` helper packages in `chaosd`. Avoid scattered `fixtures_test.go` or `test_helpers_test.go` files in multiple service directories.
- Organize the test-support package by responsibility, such as `gateway.go`, `coordinator.go`, and `config.go`, rather than by arbitrary test-file placement.
- Reuse a shared fixture instead of copying request/response handling, server startup, or recorder logic between test packages. Provide a focused helper method when more than one scenario needs the same action.
- Keep setup that genuinely depends on unexported implementation details local to its test package; **do not export production internals solely to centralize tests**.
- Do not import test-support packages into production code. Service-local Go test-support packages should live under the service's `internal/` subtree and may depend on the production API, not the reverse.
- Cross-service integration and end-to-end tests live under `tests/` and use their own Go module.
- Prefer documented APIs and message contracts to imports of implementation code from `services/`.
- Use Docker-backed fixtures when a test requires real infrastructure. Full-system tests may reuse the version-controlled Compose deployment.

The assignment's F1–F8 demonstrations should have reproducible tests covering both failure injection and expected recovery.
