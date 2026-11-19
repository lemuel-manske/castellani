# Conventions

This document separates **language-independent engineering principles** from **tooling and language-specific rules**. General principles apply to every service and language. Language-specific guidance supplements them without changing their intent.

## Engineering principles — all languages

### Readability and style

Separate code blocks with different responsibilities or contexts using one empty line. Prefer a deliberate empty line over merging unrelated operations, but do not stack multiple blank lines.

Put exactly one empty line immediately before an `if` statement unless it is the first statement in its containing block. Apply the equivalent visual separation to conditional constructs in other languages, using idiomatic syntax.

Declare constants before types and functions in source files. Group related constants by purpose so a reader can find them without searching through implementation code.

Never write long or hard-to-scan conditional expressions. Name intermediate predicates to clarify the decision; extract a helper when the predicate represents a meaningful concept or supports reuse. Avoid creating helpers that merely hide complexity.

Prefer named constants for meaningful stable values: endpoints, route templates, header names, content types, defaults, limits, timeouts, and configuration keys. Keep them near the code that owns them and share them across boundaries only when needed. Do not turn changing data or arbitrary one-off literals into constants.

Let actual requirements and complexity determine the implementation. Neither the shortest implementation nor the most layered one is automatically the simplest or best. Introduce abstractions to clarify real responsibilities, not to satisfy a template.

### Architecture and organization

Keep process entry points thin. Assemble dependencies at clear composition boundaries. Separate domain semantics, application use cases, inbound transports, and outbound adapters according to their actual responsibilities.

Choose precise, context-aware names that reveal purpose and dependencies. Avoid redundant names repeating their namespace, and vague names that obscure what a component does.

Introduce interfaces and shared packages only where they represent meaningful, consumed boundaries. Do not add them solely for architectural symmetry.

Avoid pass-through wrappers and re-exported constants or types that merely mirror another library. Import the owning package and call its API directly. Extract a wrapper only when it contributes meaningful behavior, policy, or adaptation.

Place reusable code and contracts at a boundary accessible to their intended consumers; reserve implementation-private directories for code that is genuinely private to that scope. Prefer dependency-light, broadly applicable functionality for shared libraries rather than moving service-specific logic into them.

Keep transport-specific data and protocol constants in the transport/contract layer, not in domain models. Keep each service's route templates, path prefixes, and route parameter names together rather than duplicating them across handlers and clients. Communicate between services through documented contracts rather than importing their private implementations.

### Documentation

Keep service READMEs broad: explain the service's purpose, prerequisites, development commands, configuration, and where authoritative specifications live. Do not duplicate ADRs, API contracts, lifecycle designs, implementation layouts, or test plans in README sections.

Record architectural decisions in ADRs, API behavior in contracts and specifications, and detailed testing rules in [testing.md](testing.md). Prefer linking to an authoritative document over repeating it.

### Tests

Tests must make scenarios, actions, and observable results clear. Hide incidental setup in focused, intention-revealing fixtures without hiding behavioral assertions.

Centralize reusable test infrastructure by service and responsibility rather than scattering or duplicating fixtures. Keep implementation-private setup local if centralization would require exposing private internals.

See [testing.md](testing.md) for the comprehensive testing policy.

## Tooling conventions — all services

Every service owns a `Makefile` that provides short, consistent targets such as `install`, `run`, `fmt`, `test`, and `check`. These targets abstract service-specific commands. Do not put explanatory comments in Makefiles; describe their use in the service README.

## Go-specific conventions

These rules apply only to Go source and Go tests.

- Follow the general whitespace rules for Go `if` statements: exactly one preceding empty line, except at the beginning of a containing block.
- Separate adjacent `require` and `assert` assertions with one empty line. Use `github.com/stretchr/testify/require` for prerequisites and `github.com/stretchr/testify/assert` for independent outcomes.
- Do not use `if` statements in Go tests for prerequisite or assertion handling. Write distinct named scenarios rather than table-driven or dynamically generated test cases.
- Use Go package boundaries and `internal/` visibility for implementation isolation. Shared contract types and widely consumed test infrastructure should not be buried under `internal/` merely because they originate in one package.
- Apply a consistent constructor vocabulary across packages: `NewClient` for clients and `NewHandler` for handlers, distinguishing constructors only when they genuinely initialize different types or configurations. Favor package-contextual naming over unnecessary qualifiers.
- Keep meaningful calls readable by assigning intermediate results rather than nesting lengthy constructor or helper calls inside other calls.
- Keep reusable Go service fixtures in a dedicated purpose-specific package such as `gatewaytest/` at the service root; organize fixture files by responsibility. Do not export production internals only to reuse test setup.
- Mark reusable test helpers with `t.Helper`, and register cleanup with `t.Cleanup`.

See [testing.md](testing.md) for further Go-specific testing guidance.
