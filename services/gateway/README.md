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

| Variable | Default | Description |
|---|---|---|
| `GATEWAY_ADDR` | `:8080` | Listen address |
| `COORDINATOR_URL` | required | HTTP(S) origin of the Archive Coordinator |
| `CAPTURE_URL` | required | HTTP(S) origin of the Capture service |
| `SEARCH_URL` | required | HTTP(S) origin of the Search service |
| `GATEWAY_UPSTREAM_TIMEOUT` | `5s` | Upstream HTTP request deadline |
| `GATEWAY_STREAM_TIMEOUT` | `30m` | WACZ transfer deadline |
| `GATEWAY_SHUTDOWN_TIMEOUT` | `10s` | Graceful shutdown deadline |
