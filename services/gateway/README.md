# API Gateway

The API Gateway is the stateless public HTTP entry point for the Distributed Web Archive. It routes client requests to the services that own their operations and state, including the Archive Coordinator.

The architecture and intended behavior are documented in the [ADRs](../../docs/adr/README.md), [backend specifications](../../docs/backend/README.md), and [public OpenAPI contract](../../contracts/openapi/api.yaml).

## Development

Requires Go 1.25.4. From `services/gateway`:

- `make install`: download dependencies.
- `make run`: start the Gateway.
- `make fmt`: format Go code.
- `make test`: run service-local tests.
- `make check`: run static analysis and race-enabled tests.

Development conventions and testing guidance are in [conventions.md](../../docs/conventions.md) and [testing.md](../../docs/testing.md).

## Configuration

| Variable | Default | Description |
|---|---|---|
| `GATEWAY_ADDR` | `:8080` | Listen address |
| `COORDINATOR_URL` | required | HTTP(S) origin of the Archive Coordinator |
| `GATEWAY_UPSTREAM_TIMEOUT` | `5s` | Coordinator request deadline |
| `GATEWAY_SHUTDOWN_TIMEOUT` | `10s` | Graceful shutdown deadline |
