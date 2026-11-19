# Go codemods

This module provides opinionated, source-aware Go formatting rules. Each rule can be tested independently through the exported `Format(source, rules...)` API.

## Commands

From `codemods/go`:

- `make test` runs the inline source/expected-output tests.
- `make check` runs vet and race-enabled tests.
- `go run ./cmd/gofmtx ../../libs/httpx ../../services/gateway` lists files that would change (exit 1 when changes are needed).
- Add `-w` to apply changes. Files are selected recursively, without requiring a Go workspace or importing the target modules.
- Use `-rules declarations,spacing,signatures,calls` to select rules and their order.

The default CLI mode never writes files. Generated Go files, `vendor`, hidden directories, and `testdata` are excluded when scanning directories. Explicitly provided files are still processed unless generated.

Repository-wide style checks are opt-in until existing source is migrated; CI verifies the codemod module itself. Each rule has named, inline tests and must preserve Go syntax and be idempotent.
