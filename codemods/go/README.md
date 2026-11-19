# go/codemods

This module provides opinionated, source-aware Go formatting rules. Each rule can be tested independently through the exported `Format(source, rules...)` API.

## Commands

Requires Go 1.25.4. From `libs/httpx`:

- `make fmt`: format Go code.
- `make test`: run module tests.
- `make check`: run static analysis and race-enabled tests.

The `grouping` rule inserts blank lines between recognizable statement phases: repeated header setter calls and subsequent operations; local initialization and multi-field configuration; object configuration and method execution; and separate field-mutation runs for different objects. It leaves arbitrary method chains, single field writes, comments and continuous computations unchanged. It does not infer general semantic intent.
