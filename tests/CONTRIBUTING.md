# Rules

- Share one immutable stack across the suite; do not start a new stack per test.

- Write Gherkin headers as behavior proposals, not harness descriptions: `Given a valid website ...`, not `Given the E2E stack ...`.

- Describe observable domain outcomes: admitted archive, captured pages, published WACZ, searchable snapshot.

- Isolate mutable state with generated, test-specific idempotency keys and IDs.

- Clean up only the data owned by the test.

- Do not add `t.Parallel()` to pipeline tests without checking for contention on the shared stack.

- Never use loops or branching (`if`, `switch`) in tests; put that work in `internal/testutil` helpers.

- Keep stack reuse opt-in with `CASTELLANI_E2E_KEEP_STACK=1`; default teardown removes volumes.

- Assert through documented APIs and message contracts; do not import service internals.

- Keep each scenario readable and focused on one behavior.

- Restart a service only through `TestEnv.RestartService`; those tests stay serial and must not call Compose `Up` with `RunServices`, which narrows the shared project.
