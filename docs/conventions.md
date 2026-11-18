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

Apply these formatting conventions to production code and tests. Follow `docs/testing.md` for test organization and assertion behavior.
