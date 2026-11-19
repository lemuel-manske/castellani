# go/codemods

This module provides opinionated, source-aware Go formatting rules. Each rule can be tested independently through the exported `Format(source, rules...)` API.

## Commands

Requires Go 1.25.4. From `libs/httpx`:

- `make fmt`: format Go code.
- `make test`: run module tests.
- `make check`: run static analysis and race-enabled tests.
