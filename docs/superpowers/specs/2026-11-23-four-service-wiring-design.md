# Four-Service Wiring — Design

Date: 2026-11-23

## Intent

Extend the standalone `tests/` harness from dependency readiness to a runnable full system:
Terraform provisioning plus gateway, coordinator, capture, and search. This slice wires the
services and proves they start and answer health checks. Archive workflows and fault scenarios
come later.

The test source continues to show only behavior; Compose, builds, credentials, ports, and
readiness polling stay in `tests/internal/infra`.

## Goals

- `tests/compose.yaml` starts the provisioner and all four application services from source.
- The fixture exposes gateway, coordinator, capture, and search alongside the three dependencies.
- One tagged e2e test checks that all seven services answer their health endpoints.
- Search becomes buildable and gains the same readiness endpoint convention as its siblings.

## Non-goals

- No archive submission, message-flow, or recovery assertions yet.
- No changes to the deployment `docker-compose.yaml`.
- No CI wiring, Makefile, or manual up/down commands.
- No commits under `docs/superpowers/` (user instruction).

## Constraints

- Go 1.25.0 module in `tests/`, `//go:build e2e`, testify `require`/`assert`, `t.Helper`,
  `t.Cleanup`, bounded polling, no sleeps (see `docs/testing.md`).
- ADR-0008: services own their source and Dockerfiles; tests interact through public APIs.
- ADR-0009: Testcontainers + Compose, build-tag gating.
- Existing branch `test/go-e2e-harness` is pushed; keep it intact and work in `~/dev/castellani`.
- Do not change the root deployment compose.

## Approaches

1. **Full real stack (chosen).** Build every service from its Dockerfile, add the missing search
   Dockerfile and health route, fix search's TypeScript build errors, add the Terraform
   provisioner, and extend the fixture. Higher first-slice cost, but the stack is genuinely
   runnable and later behavior tests can use it.
2. **Transpile-only search.** Skip search type errors and build with `tsc || true`. Smaller diff
   now, but leaves a container built from code that does not typecheck.
3. **Reuse root compose.** Rejected earlier: it lacks capture and search and conflicts with the
   standalone test topology decision.

## Decisions

- `tests/compose.yaml` adds a `provision` service mirroring the root compose's Terraform step,
  mounting `../infra/terraform` and depending on a healthy MiniStack.
- Gateway, coordinator, and capture use build contexts relative to `tests/` (`context: ..` with
  their service Dockerfiles). Search gets `services/search/Dockerfile` using Node 24, `npm ci`,
  `npm run build`, and `node dist/main.js`.
- Search's TypeScript build errors are fixed in this slice, and a `/health/ready` route is added
  to its Fastify server so it can be checked like the other services.
- Service URLs and credentials mirror the root compose: services talk to `ministack`, `rabbitmq`,
  `opensearch`, and each other over the Compose network by service name.
- `tests/internal/infra` gains `Gateway`, `Coordinator`, `Capture`, and `Search` services with
  mapped-port discovery and bounded readiness polling. A second tagged test checks them.
- `t.Cleanup` still owns stack teardown; ordinary `go test ./...` stays Docker-free.

## Left to the builder

- Exact search TypeScript fixes and Dockerfile details.
- Whether the new test replaces or complements `TestDependencies_AllReachable` (plan decides).
- Implementation plan and task breakdown.
