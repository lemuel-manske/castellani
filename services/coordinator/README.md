# Archive Coordinator

The Archive Coordinator owns durable archive admission, archive lifecycle decisions, and cross-service workflow coordination for the Distributed Web Archive. The API Gateway forwards archive submissions and status requests to the Coordinator.

The architecture and intended behavior are documented in the [ADRs](../../docs/adr/README.md), [backend specifications](../../docs/backend/README.md), and [public OpenAPI contract](../../contracts/openapi/api.yaml).

## Development

Requires Go 1.25.4. From `services/coordinator`:

- `make install`: download dependencies.
- `make run`: start the Coordinator.
- `make fmt`: format Go code.
- `make test`: run service-local tests.
- `make check`: run static analysis and race-enabled tests.

Development conventions and testing guidance are in [conventions.md](../../docs/conventions.md) and [testing.md](../../docs/testing.md).

## Configuration

| Variable | Default | Description |
|---|---|---|
| `COORDINATOR_ADDR` | `:8081` | Listen address |
| `COORDINATOR_TABLE_PREFIX` | empty | Namespace prefix for Coordinator-owned DynamoDB tables |
| `DYNAMODB_ENDPOINT` | AWS SDK default | Optional DynamoDB endpoint for local development |
| `AWS_REGION` | AWS SDK default | DynamoDB region |

The service requires its DynamoDB tables to be provisioned before startup. Broker dispatch and incoming SAGA event processing have not yet been implemented.
