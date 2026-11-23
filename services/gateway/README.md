# API Gateway

The API Gateway is the stateless public HTTP entry point for the application.

It routes client requests to the services that own their operations and state.

## Development

Requires Go 1.25.4. From `services/gateway`:

- `make install`: download dependencies.
- `make run`: start the Gateway.
- `make fmt`: format Go code.
- `make test`: run service-local tests.
- `make check`: run static analysis and race-enabled tests.

## Configuration

| Variable |  Description |
|---|---|
| `GATEWAY_PORT` | Listen port |
| `GATEWAY_COORDINATOR_URL` | HTTP(S) origin of the Archive Coordinator |
| `GATEWAY_CAPTURE_URL` | HTTP(S) origin of the Capture service |
| `GATEWAY_SEARCH_URL` | HTTP(S) origin of the Search service |
| `GATEWAY_GATEWAY_UPSTREAM_TIMEOUT` | Upstream HTTP request deadline. Defaults to 5s |
| `GATEWAY_GATEWAY_STREAM_TIMEOUT` | WACZ transfer deadlin. Defaults to 30m |
| `GATEWAY_GATEWAY_SHUTDOWN_TIMEOUT` | Graceful shutdown deadline. Defaults to 10s |
