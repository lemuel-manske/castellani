# Go E2E Harness — Design

Date: 2026-11-23

## Intent

Establish the cross-service end-to-end test module under `tests/` with the smallest useful
first test: prove that the local dependency stack starts and is reachable. Full multi-service
behavior is added in later slices.

The test itself must read as behavior only. Container images, Compose lifecycle, port mapping,
credentials, and readiness polling belong in a fixture package; the test states a situation,
one action, and observable outcomes.

## Goals

- A standalone Go module under `tests/`, independent of service modules (ADR-0008, ADR-0009).
- A standalone `tests/compose.yaml` defining local dependency images only.
- Testcontainers owns stack startup and teardown; no manual up/down commands to remember.
- One behavior-focused e2e test, gated by a build tag.

## Non-goals

- Application service containers (coordinator, gateway, capture, search).
- Terraform provisioning of DynamoDB tables, S3 buckets, or OpenSearch domains.
- Archive submission, message-flow assertions, fault injection, CI wiring.

## Constraints

- `docs/testing.md`: `require` for failed prerequisites, `assert` for independent properties;
  no `if` statements for assertions; no table-driven scenarios; `t.Helper` and `t.Cleanup`;
  bounded polling instead of sleeps; assertions stay in the test, setup in helpers.
- ADR-0009: standard `testing` runner, testify, Testcontainers where useful, Compose for
  full-system runs, build-tag gating for infrastructure-dependent suites.
- Go `1.25.0` with `toolchain go1.25.4`, matching the other Go modules in the monorepo.
- Do not modify or stage the pre-existing uncommitted changes under `services/capture/`.

## Approaches

1. **Include the root compose, add app services.** ADR-compliant single topology, but the root
   compose has no capture or search service and search has no Dockerfile. Rejected for now.
2. **Standalone compose in `tests/`** redefining dependencies. Chosen: independent and easy to
   read, with no changes to the deployment compose file. Risk of topology drift is accepted for
   this isolated dependency fixture and will be revisited when app services are added.
3. **Extend root `docker-compose.yaml`.** Rejected: changes the deployment file and conflicts
   with the request for a compose under `tests/`.

## Decisions

- `tests/compose.yaml` defines MiniStack (local DynamoDB/S3), RabbitMQ, and a native
  OpenSearch container. A native OpenSearch container is used instead of MiniStack's
  `OPENSEARCH_DATAPLANE` because it has a plain `:9200` health endpoint and matches the image
  used by search's service-local compose.
- Go test uses `testcontainers-go/modules/compose` with `t.Cleanup` to start and stop the same
  Compose file; there is no Makefile and no manual setup step.
- Fixture package `tests/internal/infra` owns stack lifecycle, mapped-port discovery,
  credentials, and bounded readiness polling. It exposes `Start(t) Dependencies` and
  `Service.HealthStatus(ctx) (int, error)`; the test owns all assertions.
- One test, `TestDependencies_AllReachable`, behind `//go:build e2e`.

## Left to the builder

Nothing for this slice. Later slices decide how application services join the stack and which
behavioral scenarios are tested.
