# API Gateway

Stateless public HTTP entry point for the Distributed Web Archive.

## Development

Requires Go 1.25.4. This service is an independent Go module.

From `services/gateway`:

- `make install` downloads pinned module dependencies.
- `make run` starts the HTTP server on `:8080`, or `GATEWAY_ADDR` when set.
- `make fmt` formats Go source.
- `make test` runs service-local tests.
- `make check` runs static analysis and tests with the race detector.

## Health

- `GET /health/live`: the HTTP process is serving requests.
- `GET /health/ready`: the stateless Gateway can accept requests.

Readiness deliberately does not depend on upstream service availability: a temporary Coordinator, Capture, or Search outage must not remove otherwise healthy Gateway replicas from service. Dependency-specific failures will be surfaced by public routes as Problem Details in subsequent steps.

## Scope of step 1

This foundation provides the service entry point, explicit HTTP server timeouts, signal-driven graceful shutdown, and health checks. No public archive, authentication, replay, or search route has been implemented yet. Public API behavior is specified in `contracts/openapi/api.yaml`; service ownership and failure semantics are specified in `docs/adr/` and `docs/backend/`.

The service currently has no third-party modules. When public routing is introduced, use the ADR-0024-selected `chi` router with an exact pinned version and commit `go.sum`.
