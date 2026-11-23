# Four-Service Wiring Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the `tests/` harness to a runnable full system: provisioner plus gateway, coordinator, capture, and search, with behavior tests that check all seven services are reachable.

**Architecture:** `tests/compose.yaml` becomes a standalone full-system Compose file. Application images are built from source; the existing `tests/internal/infra` fixture starts/stops the stack with Testcontainers, resolves dynamic host ports, and polls health endpoints. Tests contain only assertions. Search gains a Dockerfile, a readiness route, and the TypeScript fixes needed to build.

**Tech Stack:** Go 1.25.0 / toolchain 1.25.4, `testify`, `testcontainers-go` v0.41.0 Compose module, Docker Compose v2.20+, Node 24 for search, Terraform 1.16.5, MiniStack 1.5.42, RabbitMQ 4.1.4-management-alpine, OpenSearch 3.10.0.

**Spec:** `docs/superpowers/specs/2026-11-23-four-service-wiring-design.md`

## Global Constraints

- Work in `/home/lkmliz/dev/castellani`, on the existing `test/go-e2e-harness` branch (check it out before Task 1).
- Do **not** commit anything under `docs/superpowers/`.
- Do not modify the root `docker-compose.yaml`.
- Go module path `github.com/lemuel-manske/castellani/tests`; Go `1.25.0`; toolchain `go1.25.4`.
- E2E files carry `//go:build e2e`; ordinary `go test ./...` must remain Docker-free.
- `require` for prerequisites, `assert` for independent outcomes; no `if` statements for assertion handling; no table-driven scenarios; `t.Helper` in fixtures; `t.Cleanup` for teardown; bounded polling, no sleeps.
- All setup detail stays in `tests/internal/infra`; tests state behavior only.
- Service names and credentials mirror the root deployment compose: `castellani` / `local-development-only` for RabbitMQ, `test` / `test` for AWS.
- Publish **dynamic** host ports in `tests/compose.yaml` (single-number `ports` entries), never fixed 4566/5672/8080/etc.
- Conventional Commit messages; stage only files belonging to the task.

## Review Focus

- Search source does not typecheck at HEAD: `npm run build` must succeed in the new Dockerfile. Covered by Task 1, step 2 (red) and step 4 (green).
- Search has no readiness endpoint, so the fixture cannot tell whether it started. Covered by Task 1, step 3 and Task 2, step 6 (`/health/ready` on search).
- Capture validates DynamoDB tables at startup: it must not start before Terraform finishes. Covered by Task 2, step 4 (`depends_on: provision: service_completed_successfully`) and step 6.
- Gateway's `/health/ready` does not probe capture or search, so checking gateway alone would give false confidence. Covered by Task 2, steps 1 and 6 (separate health checks for all four app services).
- Fixed host ports collide with a developer's existing capture stack. Covered by Task 2, step 4 (dynamic ports) and step 6 (`MappedPort` discovery).

---

### Task 1: Make search buildable and health-checkable

**Files:**
- Create: `services/search/Dockerfile`
- Create: `services/search/test/api/health.test.ts`
- Modify: `services/search/src/api/server.ts`
- Modify: `services/search/src/adapters/messaging/rabbitmq/publicationConsumer.ts`
- Modify: `services/search/src/api/server.ts` (error handler typing)
- Modify: `services/search/src/application/processCrawlCompleted.ts`
- Modify: `services/search/src/application/types.ts`
- Modify: `services/search/src/assembly/runtime.ts`

**Interfaces:**
- Consumes: existing `createSearchServer(reader, publicationLedger, manifestLedger)` in `services/search/src/api/server.ts`.
- Produces:
  - `GET /health/ready` on a `createSearchServer` instance returns `200` with `{"status":"ok"}`.
  - `services/search/Dockerfile` builds a runnable image from context `services/search/` with `node dist/main.js`.

- [ ] **Step 1: Write the failing health-route test**

Create `services/search/test/api/health.test.ts`. It imports `createSearchServer` from `../../src/api/server.js`, builds a server with minimal typed stubs for the three dependencies, and asserts:

```ts
const response = await server.inject({ method: "GET", url: "/health/ready" });
expect(response.statusCode).toBe(200);
expect(response.json()).toEqual({ status: "ok" });
```

Run: `cd services/search && npm test -- health.test.ts`
Expected: FAIL — route does not exist (404).

- [ ] **Step 2: Record the build failure**

Run: `cd services/search && npm run build`
Expected: FAIL with the seven known TypeScript errors in `publicationConsumer.ts` (3), `api/server.ts` (1), `processCrawlCompleted.ts` (1), `application/types.ts` (1), and `assembly/runtime.ts` (2).

- [ ] **Step 3: Implement the health route and fix the build errors**

In `services/search/src/api/server.ts`, register `GET /health/ready` on the Fastify instance, returning `{ status: "ok" }`. Also fix the `error is of type unknown` error in the existing `setErrorHandler` without weakening the response contract.

Fix the remaining TypeScript errors so `npm run build` succeeds:

- `publicationConsumer.ts:35,41,46`: preserve the validated envelope fields (`version`, `messageId`, `correlationId`, `occurredAt`) when narrowing to a `PublicationEvent`; do not drop them.
- `processCrawlCompleted.ts:88`: add `version: 1` to the synthesized `PageCapturedEvent`.
- `application/types.ts:188`: make `PublicationEventSchema` acceptable to `createSchemaValidator<PublicationEvent>` while keeping runtime validation of the same fields.
- `assembly/runtime.ts:113`: call `ensureSearchIndex(opensearch)` — the function takes one argument and the index name comes from `SEARCH_INDEX_NAME`.

Create `services/search/Dockerfile`:

- Build stage `node:24.16.0-alpine`, `WORKDIR /app`, copy `package.json` and `package-lock.json`, `RUN npm ci`, copy `tsconfig*.json` and `src`, `RUN npm run build`.
- Runtime stage `node:24.16.0-alpine`, `WORKDIR /app`, copy `node_modules` and `dist` from build, copy `package.json`, `USER node`, `EXPOSE 8082`, `CMD ["node", "dist/main.js"]`.

No other search source files change.

- [ ] **Step 4: Verify search**

Run: `cd services/search && npm test -- health.test.ts && npm run build`
Expected: health test PASS; build exits 0 with no TypeScript errors.

- [ ] **Step 5: Commit**

```bash
git add services/search/Dockerfile services/search/test/api/health.test.ts services/search/src
git commit -m "fix(search): make service buildable and add readiness route"
```

---

### Task 2: Wire the full stack and assert all services are reachable

**Files:**
- Modify: `tests/compose.yaml`
- Modify: `tests/internal/infra/stack.go`
- Create: `tests/services_test.go`
- Modify: `tests/e2e_test.go` only if the existing test name or imports need adjustment (no new assertions there)

**Interfaces:**
- Consumes: `infra.Start(t *testing.T) Dependencies`, `Service.HealthStatus(ctx context.Context) (int, error)` from Task 1's existing fixture.
- Produces:
  - `infra.Dependencies{Gateway, Coordinator, Capture, Search Service}` in addition to the existing three dependency fields.
  - `TestServices_AllReachable` in `tests/services_test.go`, behind `//go:build e2e`.

- [ ] **Step 1: Write the failing e2e behavior test**

Create `tests/services_test.go` with `//go:build e2e`, package `tests_test`, and one test:

```go
func TestServices_AllReachable(t *testing.T) {
	ctx := context.Background()
	services := infra.Start(t)

	gatewayStatus, gatewayErr := services.Gateway.HealthStatus(ctx)
	require.NoError(t, gatewayErr)

	coordinatorStatus, coordinatorErr := services.Coordinator.HealthStatus(ctx)
	require.NoError(t, coordinatorErr)

	captureStatus, captureErr := services.Capture.HealthStatus(ctx)
	require.NoError(t, captureErr)

	searchStatus, searchErr := services.Search.HealthStatus(ctx)
	require.NoError(t, searchErr)

	assert.Equal(t, http.StatusOK, gatewayStatus)
	assert.Equal(t, http.StatusOK, coordinatorStatus)
	assert.Equal(t, http.StatusOK, captureStatus)
	assert.Equal(t, http.StatusOK, searchStatus)
}
```

Run: `cd tests && go test -tags=e2e ./... -run TestServices_AllReachable`
Expected: FAIL — `Dependencies` has no `Gateway` field.

- [ ] **Step 2: Extend the fixture's public shape**

In `tests/internal/infra/stack.go`, add `Gateway`, `Coordinator`, `Capture`, and `Search` fields of type `Service` to `Dependencies`. Do not change `Service` or `HealthStatus`.

- [ ] **Step 3: Add healthchecks to the Compose app services**

In `tests/compose.yaml`, add Compose `healthcheck` blocks for the four app services, using `/health/ready`:

- `gateway`: `wget -q -O /dev/null http://127.0.0.1:8080/health/ready` (interval 10s, timeout 3s, start_period 10s, retries 3).
- `coordinator`: same shape on port 8081.
- `capture`: `python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health/ready')"` (interval 10s, timeout 3s, start_period 10s, retries 3).
- `search`: `wget -q -O /dev/null http://127.0.0.1:8082/health/ready` (interval 10s, timeout 3s, start_period 10s, retries 3).

- [ ] **Step 4: Add the provisioner and application services**

In `tests/compose.yaml`, add, in dependency order:

- `provision`: `hashicorp/terraform:1.16.5`, `working_dir: /workspace`, `TF_VAR_ministack_endpoint: http://ministack:4566`, `TF_VAR_aws_region: us-east-1`, mount `../infra/terraform:/workspace`, `depends_on: ministack: service_healthy`, entrypoint `/bin/sh -c`, command `terraform init -input=false -lockfile=readonly && terraform apply -auto-approve -input=false`, `restart: "no"`.
- `coordinator`: build `context: ..`, `dockerfile: services/coordinator/Dockerfile`; `COORDINATOR_ADDR=:8081`, `COORDINATOR_AWS_REGION=us-east-1`, `COORDINATOR_DYNAMODB_ENDPOINT=http://ministack:4566`, `COORDINATOR_RABBITMQ_URL=amqp://castellani:local-development-only@rabbitmq:5672/`, `COORDINATOR_RABBITMQ_EXCHANGE=castellani.events`, `AWS_ACCESS_KEY_ID=test`, `AWS_SECRET_ACCESS_KEY=test`, `AWS_EC2_METADATA_DISABLED=true`; publish `8081`; depends on `provision: service_completed_successfully` and `rabbitmq: service_healthy`.
- `capture`: build `context: ..`, `dockerfile: services/capture/Dockerfile`; `AWS_REGION=us-east-1`, `DYNAMODB_ENDPOINT_URL=http://ministack:4566`, `S3_ENDPOINT_URL=http://ministack:4566`, `RABBITMQ_URL=amqp://castellani:local-development-only@rabbitmq:5672/`, `AWS_ACCESS_KEY_ID=test`, `AWS_SECRET_ACCESS_KEY=test`, `AWS_EC2_METADATA_DISABLED=true`, `CAPTURE_BROWSER_SLOT_COUNT=1`; publish `8000`; depends on `provision: service_completed_successfully` and `rabbitmq: service_healthy`.
- `search`: build `context: ../services/search`, `dockerfile: Dockerfile`; `SEARCH_AWS_REGION=us-east-1`, `SEARCH_AWS_ACCESS_KEY_ID=test`, `SEARCH_AWS_SECRET_ACCESS_KEY=test`, `SEARCH_HTTP_HOST=0.0.0.0`, `SEARCH_HTTP_PORT=8082`, `SEARCH_DYNAMODB_ENDPOINT_URL=http://ministack:4566`, `SEARCH_S3_ENDPOINT_URL=http://ministack:4566`, `SEARCH_RABBITMQ_URL=amqp://castellani:local-development-only@rabbitmq:5672/`, `SEARCH_OPENSEARCH_URL=http://opensearch:9200`; publish `8082`; depends on `provision: service_completed_successfully`, `rabbitmq: service_healthy`, and `opensearch: service_healthy`.
- `gateway`: build `context: ..`, `dockerfile: services/gateway/Dockerfile`; `GATEWAY_ADDR=:8080`, `COORDINATOR_URL=http://coordinator:8081`, `CAPTURE_URL=http://capture:8000`, `SEARCH_URL=http://search:8082`, `GATEWAY_UPSTREAM_TIMEOUT=5s`, `GATEWAY_STREAM_TIMEOUT=30m`, `GATEWAY_SHUTDOWN_TIMEOUT=10s`; publish `8080`; depends on `coordinator`, `capture`, and `search` with `service_healthy`.

Keep the three dependency services unchanged except that each still publishes a dynamic host port.

- [ ] **Step 5: Resolve the new mapped ports in the fixture**

In `infra.Start`, after `stack.Up(ctx)`, construct the four new services with `newService(t, ctx, stack, name, port, "/health/ready", "", "")`:

- gateway: name `gateway`, port `8080`
- coordinator: name `coordinator`, port `8081`
- capture: name `capture`, port `8000`
- search: name `search`, port `8082`

Append them to the existing `waitForHealthy` calls and include them in the returned `Dependencies`.

- [ ] **Step 6: Verify the e2e suite**

Run: `cd tests && go test -tags=e2e ./... -v`
Expected: PASS for `TestDependencies_AllReachable` and `TestServices_AllReachable`. Docker builds may take several minutes on first run; all containers are removed on test completion.

- [ ] **Step 7: Verify build-tag gating and formatting**

Run: `cd tests && go test ./... && gofmt -l .`
Expected: no tests run without the tag; `gofmt -l` prints nothing.

- [ ] **Step 8: Commit**

```bash
git add tests/compose.yaml tests/internal/infra/stack.go tests/services_test.go
git commit -m "test(e2e): wire all four services into the test stack"
```

Leave `docs/superpowers/` uncommitted.
