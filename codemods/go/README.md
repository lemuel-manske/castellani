# go/codemods

This module provides opinionated, source-aware Go formatting rules. Each rule can be tested independently through the exported `Format(source, rules...)` API.

## Commands

Requires Go 1.25.4. From `libs/httpx`:

- `make fmt`: format Go code.
- `make test`: run module tests.
- `make check`: run static analysis and race-enabled tests.

The `returns` rule separates a `return` immediately following an `if` block. `structs` expands nonempty single-line struct bodies. `types` separates adjacent top-level type declarations; `interfaces` separates interface members with blank lines. All rules preserve comments where the rewrite is unambiguous.
