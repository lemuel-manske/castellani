# Go E2E Harness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create a standalone Go e2e module whose first test proves the local dependency stack is reachable, with all infrastructure setup hidden in a fixture package.

**Architecture:** `tests/` owns its own Go module and a standalone Compose file describing MiniStack, RabbitMQ, and OpenSearch. A Testcontainers Compose stack starts and stops that file; `tests/internal/infra` encapsulates lifecycle, port mapping, credentials, and readiness polling. The tagged e2e test contains only the behavior and assertions.

**Tech Stack:** Go 1.25.0 / toolchain 1.25.4, `testify v1.10.0`, `testcontainers-go v0.45.0`, `testcontainers-go/modules/compose v0.45.0`, Docker Compose v2.20+, standard `net/http`.

**Spec:** `docs/superpowers/specs/2026-11-23-go-e2e-harness-design.md`

## Global Constraints

- Module path: `github.com/lemuel-manske/castellani/tests`.
- Go directive `1.25.0`; toolchain `go1.25.4`.
- E2E test file carries `//go:build e2e`.
- `require` for failed prerequisites; `assert` for independent outcomes; blank line between adjacent `require` and `assert` calls.
- No `if` statements for prerequisite/assertion handling; no table-driven or generated scenarios.
- `t.Helper()` in every reusable fixture helper; `t.Cleanup` for teardown.
- No fixed sleeps; readiness uses bounded polling with a deadline.
- All setup detail (images, Compose, ports, credentials, polling) lives in `tests/internal/infra`; the test contains no setup logic.
- Do not import from `services/`; do not modify files under `services/capture/`.
- Conventional Commit message for the change.

## Review Focus

- Docker daemon or Compose binary unavailable: `Start` must fail fast through `require`, with no hang and no panic. Covered by Task 1, step 3 (`require.NoError` on stack creation and `Up`).
- Partial startup failure: teardown must still happen even if `Up` fails. Covered by Task 1, step 3 (`t.Cleanup` registered before `Up`).
- Slow dependency startup: health checks must not fire before services are ready, and must not use sleeps. Covered by Task 1, step 3 (bounded polling in `Start`) and step 5.
- RabbitMQ management API requires authentication: fixture must supply credentials so the health check returns 200. Covered by Task 1, step 4 and step 5.
- Running ordinary `go test` must not require Docker. Covered by Task 1, step 7.

---

### Task 1: Go e2e module, dependency stack, and first behavior test

**Files:**
- Create: `tests/e2e_test.go`
- Create: `tests/doc.go`
- Create: `tests/go.mod`
- Create: `tests/go.sum` (generated)
- Create: `tests/compose.yaml`
- Create: `tests/internal/infra/stack.go`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `infra.Start(t *testing.T) Dependencies`
  - `infra.Dependencies{ MiniStack Service; RabbitMQ Service; OpenSearch Service }`
  - `infra.Service.HealthStatus(ctx context.Context) (int, error)`

- [ ] **Step 1: Write the failing behavior test**

Create `tests/doc.go` containing only `package tests`, so the module root remains buildable when the e2e tag is absent.

Create `tests/e2e_test.go` with package `tests_test`, the `//go:build e2e` tag, and exactly one test:

```go
func TestDependencies_AllReachable(t *testing.T) {
	ctx := context.Background()
	deps := infra.Start(t)

	miniStackStatus, miniStackErr := deps.MiniStack.HealthStatus(ctx)
	require.NoError(t, miniStackErr)

	rabbitMQStatus, rabbitMQErr := deps.RabbitMQ.HealthStatus(ctx)
	require.NoError(t, rabbitMQErr)

	openSearchStatus, openSearchErr := deps.OpenSearch.HealthStatus(ctx)
	require.NoError(t, openSearchErr)

	assert.Equal(t, http.StatusOK, miniStackStatus)
	assert.Equal(t, http.StatusOK, rabbitMQStatus)
	assert.Equal(t, http.StatusOK, openSearchStatus)
}
```

Imports: `context`, `net/http`, `testing`, `infra`, `testify/assert`, `testify/require`.

- [ ] **Step 2: Confirm the test fails before implementation**

Run: `cd tests && go test -tags=e2e ./...`
Expected: FAIL — no `go.mod` / undefined `infra`.

- [ ] **Step 3: Define the module and the standalone dependency Compose file**

Create `tests/go.mod` with module `github.com/lemuel-manske/castellani/tests`, the Go/toolchain directives above, and direct requirements for `github.com/stretchr/testify v1.10.0`, `github.com/testcontainers/testcontainers-go v0.45.0`, and `github.com/testcontainers/testcontainers-go/modules/compose v0.45.0`.

Create `tests/compose.yaml` with three services and no application services:

- `ministack`: `ministackorg/ministack:1.5.42`; publish `4566:4566`; `AWS_DEFAULT_REGION: us-east-1`, `PERSIST_STATE: "0"`, `S3_PERSIST: "0"`; healthcheck polling `http://localhost:4566/_ministack/health` every 5s, 3s timeout, 20 retries.
- `rabbitmq`: `rabbitmq:4.1.4-management-alpine`; publish `5672:5672` and `15672:15672`; `RABBITMQ_DEFAULT_USER: castellani`, `RABBITMQ_DEFAULT_PASS: local-development-only`; healthcheck `rabbitmq-diagnostics -q ping` every 5s, 5s timeout, 20 retries.
- `opensearch`: `opensearchproject/opensearch:3.10.0`; publish `9200:9200`; `discovery.type: single-node`, `DISABLE_SECURITY_PLUGIN: "true"`, `OPENSEARCH_JAVA_OPTS: "-Xms512m -Xmx512m"`; healthcheck `curl -fsS http://localhost:9200/_cluster/health` every 5s, 3s timeout, 20 retries.

- [ ] **Step 4: Implement the fixture that hides all infrastructure detail**

Create `tests/internal/infra/stack.go` with the exact interfaces listed above. `Start` must:

- call `t.Helper()`;
- create a Compose stack from `compose.yaml` with `compose.NewDockerComposeWith(compose.WithStackFiles("compose.yaml"))` and `require.NoError`;
- register `t.Cleanup` calling `stack.Down(context.Background())` before calling `Up`;
- call `stack.Up(ctx)` with `require.NoError`;
- resolve each service's host port through `stack.ServiceContainer(ctx, name)` and `MappedPort`, then build these health endpoints: MiniStack `http://localhost:<4566>/_ministack/health`, RabbitMQ `http://localhost:<15672>/api/overview` with basic auth `castellani` / `local-development-only`, OpenSearch `http://localhost:<9200>/_cluster/health`;
- poll each endpoint with `Service.HealthStatus` until it returns 200, using a 500ms ticker and an overall 120s deadline, failing with `require` if the deadline expires.

`Service.HealthStatus` issues the HTTP GET with a 5s client timeout, closes the body, and returns the status code and any error. All fixture helpers call `t.Helper()` where a `*testing.T` is available.

- [ ] **Step 5: Generate the module checksums**

Run: `cd tests && go mod tidy`
Expected: `go.sum` created; no requirement changes beyond the declared direct dependencies and their transitive dependencies.

- [ ] **Step 6: Verify the e2e test**

Run: `cd tests && go test -tags=e2e ./... -v`
Expected: PASS with `TestDependencies_AllReachable`; Docker containers start and are removed when the test ends.

- [ ] **Step 7: Verify build-tag gating**

Run: `cd tests && go test ./...`
Expected: PASS with `[no test files]` for the module root; no Docker required.

- [ ] **Step 8: Commit**

```bash
git add tests/ docs/superpowers/
git commit -m "test(e2e): add Go harness with dependency readiness check"
```
