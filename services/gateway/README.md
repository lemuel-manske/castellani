# API Gateway

The Gateway is the stateless public HTTP entry point of the Distributed Web Archive. It owns no application database and does not publish crawl commands. The Archive Coordinator remains authoritative for admission and idempotency (ADRs 0002, 0005, 0010 and 0012).

## Layout

The package structure follows the same dependency direction as [chaosd](https://github.com/lemuel-manske/chaosd):

- `main.go`, `config.go`, `server.go`: process entry point, validated runtime configuration, server lifetime and dependency assembly.
- `api/`: public HTTP router and request middleware.
- `api/archive/`: archive-specific public HTTP handlers, decoding, validation boundary and response translation.
- `application/`: application use cases and the Coordinator port. Does not import HTTP router packages or an external service implementation.
- `internal/archive/`: Gateway-side archive contract representations and semantic validation.
- `internal/coordinator/`: outgoing HTTP adapter, bounded calls and typed upstream failures.
- `internal/httpx/`: RFC 9457 response serialization used by HTTP handlers.

The independent Go module does not import implementation code from other services. It consumes language-neutral public contracts from `contracts/openapi/api.yaml`. Interfaces are introduced at the application-to-Coordinator boundary, where they enable transport replacement and isolated verification.

## Development

Requires Go 1.25.4. All modules are pinned in `go.mod` and checksums tracked in `go.sum`.

From `services/gateway`:

- `make install`: download declared dependencies.
- `make run`: start the Gateway.
- `make fmt`: format Go sources.
- `make test`: run service-local behavioral tests.
- `make check`: run static analysis and race-enabled tests.

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `GATEWAY_ADDR` | `:8080` | Host:port on which to listen |
| `COORDINATOR_URL` | required | HTTP(S) origin of the Archive Coordinator, without a path or credentials |
| `GATEWAY_UPSTREAM_TIMEOUT` | `5s` | Deadline on each Coordinator HTTP call, including response-body reading |
| `GATEWAY_SHUTDOWN_TIMEOUT` | `10s` | Deadline for draining requests on SIGINT/SIGTERM |

Malformed configuration and listener binding errors fail startup. Upstream requests are context-bound, with a bounded response-body size and disabled redirect following, so a configured Coordinator cannot redirect the Gateway to another target.

## Public HTTP boundary

Implemented:

- `POST /archives`: validates the public JSON envelope and required idempotency header, then forwards the original body and key to the Coordinator. Returns 202 **only after the Coordinator confirms durable admission**. A network failure is an *unknown admission outcome*, surfaced as 503 with instructions to retry using the same key.
- `GET /archives/{archiveId}`: retrieves current durable status from the Coordinator rather than a Gateway cache.
- `GET /health/live` and `GET /health/ready`: process health and readiness.

The Gateway does not calculate request fingerprints, persist idempotency keys, deduplicate retries, or infer a successful operation from a transient HTTP response. Those guarantees are owned by the Coordinator. The accepted response uses a public `Location` and `statusUrl`, never the Coordinator's internal address.

Public failures follow RFC 9457 Problem Details and carry a request ID header. Response bodies from upstream are size-bounded and malformed response contracts are treated as upstream failures. No request bodies or credentials are written to application logs.

The router is built using the pinned `chi` dependency selected by ADR-0024. Middleware and HTTP handlers are kept separate from application and transport adapters.

## Service lifecycle

The Gateway binds before logging listener availability, becomes ready while serving, and withdraws readiness when shutdown begins. Graceful termination drains in-flight requests within the configured deadline. Readiness does not probe the Coordinator: temporary upstream outages must not remove otherwise healthy Gateway replicas from load balancing.

The HTTP server bounds header size, header parsing, request reading, and idle time. A global write timeout is deliberately omitted because published WACZ downloads may require streaming in a later step; the streaming routes must enforce their own cancellation and deadline rules.

## Verification and remaining work

Service-local tests exercise the actual HTTP listener and Gateway-to-Coordinator boundary using an HTTP fixture, including accepted requests, status, validation failures, conflicts, uncertain admission, and invalid upstream output. This does **not** prove Coordinator-side persistence or 24-hour idempotency retention; those require cross-service integration tests when the Coordinator is implemented.

The remaining steps cover search, interactive authentication, replay/WACZ streaming, and full deployment/fault-tolerance verification.
