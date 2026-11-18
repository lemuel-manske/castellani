# Testing conventions

These rules apply across Go, Python, TypeScript, and system-level tests. Use idiomatic tooling for each language while preserving the same behavioral focus and readability.

## Behavior, not implementation

Tests must verify observable behavior, user interactions, documented contracts, and correctness invariants. Do not couple tests to incidental implementation details such as internal functions, private storage layouts, CSS classes, or styling.

For UI tests, prefer semantic queries and assertions (such as accessible role/name, visibility, and enabled state) over selectors or matchers such as `toHaveClass` or `toHaveStyle`. Visual-regression and snapshot-based visual testing are out of scope for now.

For backend tests, assertions against a public API, message contract, or domain outcome are preferred. Infrastructure assertions are appropriate where infrastructure behavior itself is the requirement (for example, redelivery, queue isolation, or broker recovery); avoid relying on unrelated internal details.

## Readability and organization

- Start each test file with tests of primary, observable behavior. Follow with exceptional, boundary, and recovery cases.
- Give each meaningful scenario its own explicitly named test. Do not use loops, tables, or dynamic generation to create parameterized test cases.
- Ordinary loops inside a single scenario are allowed when exercising concurrency, workload size, or repeated actions, such as sending 100 competing requests.
- Make setup, action, and assertions easy to identify. Prefer direct tests to generic abstractions that obscure intent.
- Extract helpers for recurring fixture setup, cleanup, polling, and client calls; keep the behavior under test visible in the test body.
- Use descriptive names that communicate the precondition and expected outcome. The `chaosd` test suite is the style reference, not a library dependency.

## Determinism and isolation

- Avoid arbitrary sleeps for synchronization. Wait for observable conditions using bounded polling, explicit readiness checks, and deadlines.
- Tests must be isolated from one another, create uniquely identified fixtures where required, and clean up resources they own.
- Failure tests should establish the baseline behavior, introduce a controlled failure, then assert the externally observable recovery or terminal state.
- A passing test must establish the promised invariant, not merely verify that a message was published or a command returned without error.

## Test placement

- Service-local unit and integration tests stay alongside the respective service source.
- Cross-service integration and end-to-end tests live under `tests/` and use their own Go module.
- Prefer documented APIs and message contracts to imports of implementation code from `services/`.
- Use Docker-backed fixtures when a test requires real infrastructure. Full-system tests may reuse the version-controlled Compose deployment.

The assignment's F1–F8 demonstrations should have reproducible tests covering both failure injection and expected recovery.
