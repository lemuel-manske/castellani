# Conventions

## Commands

Each service owns a `Makefile` as its documented command interface. Common development and verification tasks must be exposed through short, abstract targets such as `install`, `run`, `fmt`, `test`, and `check` instead of project-specific target names or raw tool commands. Makefiles do not contain explanatory comments; supporting documentation belongs in the service README.

## Go-specific conventions

### Style

Use one empty line to separate adjacent blocks of code with different responsibilities or context. Prefer a deliberate extra empty line to visually merging unrelated operations, but do not stack two or more empty lines.

Always put **exactly one empty line immediately before an `if` statement** (unless it is the first statement in its containing block). This includes short guard clauses. Keep related operations together while making decision boundaries easy to scan.

Never write long or compound `if` conditions. Name intermediate predicates to make the condition explain itself. Extract a helper function when the predicate has a distinct meaning or can be reused; do not extract a function solely to obscure a condition. Keep the final `if` compact.

Prefer named constants for stable protocol and application values: HTTP endpoint paths and route templates, header names, content types, limits, defaults, and timeouts. Keep constants close to their owning package and share them across packages only when an actual consumer warrants it. Do not turn dynamic values or arbitrary one-off details into constants.

Separate `require` and `assert` statements with a blank line whenever one follows the other.

### Organization and dependencies

Keep entry points thin. Assemble concrete dependencies at the composition boundary; place application operations, transport handlers, and external adapters in packages with clear responsibilities, following the separation used in `chaosd`.

Prefer explicit, meaningful package and concrete-type names. Avoid redundant names that repeat the package (such as `coordinator.CoordinatorClient`) and ambiguous abstractions that hide a real dependency.

Do not introduce interfaces or shared libraries solely to satisfy a pattern. Define interfaces at the boundary that consumes them when they genuinely decouple a use case from a transport or external dependency.

Keep HTTP paths, headers, and wire-format constants with their owning transport or contract package, not in domain models. Do not import sibling service implementation packages; consume documented language-neutral contracts.

### Tests and fixture organization

Test names and bodies must describe observable behavior rather than the mechanics of building a request or configuring dependencies. Use concise scenario → action → assertion flow.

Move **reusable service-wide test setup** into a dedicated purpose-specific package such as `internal/gatewaytest/`, as in the `chaosd` test-support packages. Keep all common fixture construction, HTTP helpers, response decoding, and recording doubles together, organized into files by responsibility. Do not scatter equivalent `fixtures_test.go` or `test_helpers_test.go` files around the service.

Avoid duplicating test fixture code across packages. Keep implementation-private lifecycle tests local where required by Go visibility rules rather than exporting internals just to share setup. Fixture helpers must expose intent, register cleanup, and leave behavioral assertions visible in the tests.

Do not use `if` statements in tests to handle assertions; use `require` for prerequisites and `assert` for independent results. Do not use table-driven or dynamically generated test scenarios. Follow `docs/testing.md` for the full rules.

Apply these formatting and organization conventions to production code and tests.
