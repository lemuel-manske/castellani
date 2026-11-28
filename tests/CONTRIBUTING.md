# Contributing to the end-to-end suite

- Do not commit; the maintainer handles commits.
- Do not run the suite here; use compile-only checks and ask the maintainer to run `make test`.
- Write Gherkin headers as behavior proposals, not harness descriptions: `Given a valid website ...`, not `Given the E2E stack ...`.
- Describe observable domain outcomes: admitted archive, captured pages, published WACZ, searchable snapshot.
- Share one immutable stack across the suite; do not start a new stack per test.
- Isolate mutable state with generated, test-specific idempotency keys and IDs.
- Clean up only the data owned by the test.
- Keep stack reuse opt-in with `CASTELLANI_E2E_KEEP_STACK=1`; default teardown removes volumes.
- Assert through documented APIs and message contracts; do not import service internals.
- Do not add `t.Parallel()` to pipeline tests without checking for contention on the shared stack.
- Never use loops or branching (`if`, `switch`) in tests; put that work in `internal/testutil` helpers.
- Use full URLs from `services.Gateway.URL(...)`; keep request bodies and headers as strings.
- Keep each scenario readable and focused on one behavior.
