# API Gateway

Stateless Go HTTP entry point for the Distributed Web Archive. The Gateway owns no application database and cannot admit an archive independently of the Coordinator (ADR-0002 and ADR-0010).

## Development

Requires Go 1.25.4. This service is an independent Go module with pinned dependencies.

From `services/gateway`:

- `make install`: download the module graph.
- `make run`: start the Gateway.
- `make fmt`: format Go sources.
- `make test`: run service-local tests.
- `make check`: run `go vet` and race-enabled tests.

## Configuration

| Variable | Default | Meaning |
|---|---|---|
| `GATEWAY_ADDR` | `:8080` | TCP listen address, in host:port form |
| `GATEWAY_SHUTDOWN_TIMEOUT` | `10s` | Deadline for draining active requests on SIGINT/SIGTERM |

Invalid configuration fails at startup. Binding failures also fail startup rather than logging a misleading listening message.

## HTTP lifecycle and health

The Gateway binds its TCP listener before logging that it is listening. Liveness indicates a responsive Gateway process. Readiness transitions to available when the server starts serving and becomes unavailable when shutdown begins.

- `GET /health/live`: 200 if the process can serve HTTP.
- `GET /health/ready`: 200 while accepting traffic; 503 before serving or during graceful shutdown.

Readiness intentionally does **not** probe Coordinator, Capture, or Search. Their transient unavailability must not remove an otherwise healthy Gateway replica from load balancing. Public operations will return dependency-specific errors when appropriate.

On termination, the Gateway marks itself unready, stops accepting new connections, waits for in-flight requests up to the configured deadline, then closes remaining connections. Unexpected listener exit is treated as a process error.

The server bounds request-header parsing and idle/read time. It deliberately has **no server-wide `WriteTimeout`**, since that would truncate future long-running WACZ transfers. Route-specific timeouts, streaming cancellation and downstream budgets belong to the respective endpoint implementations.

Logs use structured JSON with a `service=gateway` attribute. The process does not log request bodies or credentials.

## Scope of step 1

This step establishes bootstrapping, validated configuration, lifecycle management, distinct health semantics, and HTTP-level lifecycle tests. It does **not** claim working archive admission, sessions, search, or replay. Those routes must follow `contracts/openapi/api.yaml`, with RFC 9457 errors and bounded upstream calls introduced in later steps.

The `chi` router selected by ADR-0024 is deferred until public routes are added in step 2. Avoid adding middleware or interfaces without a concrete consumer.
