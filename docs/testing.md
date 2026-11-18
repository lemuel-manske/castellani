# Testing conventions

These rules apply across Go, Python, TypeScript, and system-level tests. Use idiomatic tooling for each language while preserving the same behavioral focus and readability.

## Behavior, not implementation

Tests must verify observable behavior, user interactions, documented contracts, and correctness invariants. Do not couple tests to incidental implementation details such as internal functions, private storage layouts, CSS classes, or styling.

For UI tests, prefer semantic queries and assertions (such as accessible role/name, visibility, and enabled state) over selectors or matchers such as `toHaveClass` or `toHaveStyle`. Visual-regression and snapshot-based visual testing are out of scope for now.

For backend tests, assertions against public APIs, message contracts, and domain outcomes are preferred. Infrastructure assertions are appropriate where infrastructure behavior itself is the requirement (for example, redelivery, queue isolation, or broker recovery); avoid relying on unrelated internal details.

## Readability and organization

- Start test files with tests of primary, observable behavior; follow with exceptional, boundary, and recovery scenarios.
- Give each meaningful scenario its own explicitly named test. Name tests for the action or precondition and expected behavior, not the internal method being exercised. For example, `TestArchive_BrokerUnavailable_RecoversWithoutLosingWork`.
- Do not generate test cases with loops, tables, or dynamic parameterization. Write each distinct test case explicitly. Ordinary loops within a single scenario are allowed for workloads such as 100 concurrent requests.
- Keep a clear progression: establish a fixture and preconditions, perform the action, then verify the outcome. Use straightforward test bodies rather than deep nesting or helper abstractions that hide the behavior under test.
- Prefer small, focused tests with direct, meaningful assertions. Assertions should explain the behavior being guaranteed, not merely check that execution did not panic.
- Keep setup and teardown in focused helpers only where repetition warrants it. Helpers should expose intent (such as starting a test website or waiting for archive completion) and should not embed the test's behavioral assertions.
- Use fixture builders or small test doubles where appropriate for isolated tests. Their purpose is to make preconditions explicit, not to reproduce implementation logic.

## Assertions and failures

- Stop immediately when a prerequisite fails and subsequent assertions cannot be meaningful (for example, failure to create an archive or start a fixture). In Go, use `require` for these checks.
- Use non-fatal assertions for independent properties that can be meaningfully evaluated together. In Go, use `assert`.
- Assert concrete results and invariants. A successful command response or event publication alone is not proof that a distributed operation completed correctly.
- Prefer verifying both the presence of intended effects and the absence of prohibited effects, especially for idempotency, compensation, and concurrent processing.

## Determinism and lifecycle

- Avoid arbitrary sleeps for synchronization. Wait for observable conditions using bounded polling, explicit readiness checks, and deadlines.
- Tests must be isolated, create unique identifiers or resources where necessary, and not depend on execution order.
- Fixtures that create temporary files, containers, services, or network changes must register cleanup so it runs even if assertions fail. In Go, use `t.Cleanup` and mark reusable helpers with `t.Helper`.
- Integration tests that require real dependencies should be distinguishable from fast unit tests; Go build tags such as `integration` are acceptable.
- Prefer real infrastructure in integration and end-to-end tests. Test doubles are appropriate for isolated behavior tests, but must not replace the real broker or database when their failure or concurrency semantics are under test.
- Failure tests should establish normal behavior, introduce a controlled fault, verify the degraded state where relevant, remove the fault, and assert recovery or a valid terminal state.
- Ensure cleanup and recovery are verified rather than leaving hidden effects that can contaminate subsequent tests.

## Test placement

- Service-local unit and integration tests stay alongside the respective service source.
- Cross-service integration and end-to-end tests live under `tests/` and use their own Go module.
- Prefer documented APIs and message contracts to imports of implementation code from `services/`.
- Use Docker-backed fixtures when a test requires real infrastructure. Full-system tests may reuse the version-controlled Compose deployment.

The assignment's F1–F8 demonstrations should have reproducible tests covering both failure injection and expected recovery.
