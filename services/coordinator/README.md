# Coordinator

The Archive Coordinator durably admits archive runs and owns workflow coordination across Capture and Search.

## Development

Requires Go 1.25.4. From `services/coordinator`:

- `make install`: download dependencies.
- `make run`: start the Coordinator.
- `make fmt`: apply repository Go formatting conventions.
- `make check`: run static analysis and compile all packages without executing tests.
- `make test-unit`: run unit tests without external infrastructure.
- `make test-integration`: run integration tests against local DynamoDB and RabbitMQ. Start the services first with `make test-infra-up`.
- `make test`: run unit and integration tests.
- `make test-infra-up`: start local DynamoDB and RabbitMQ for integration tests.
- `make test-infra-down`: stop the local test infrastructure.

## Configuration

| Variable | Description |
|---|---|
| `COORDINATOR_PORT` | HTTP listen port |
| `COORDINATOR_AWS_REGION` | AWS SDK region |
| `COORDINATOR_SHUTDOWN_TIMEOUT` | Graceful shutdown deadline. Defaults to 10s |
| `COORDINATOR_RECONCILIATION_INTERVAL` | Delay between stalled-workflow reconciliation passes. Defaults to 30s |
| `COORDINATOR_STALLED_WORKFLOW_AGE` | Minimum time without a state update before a SAGA decision is reissued. Defaults to 2m |
| `COORDINATOR_DYNAMODB_ENDPOINT` | Optional DynamoDB-compatible endpoint |
| `COORDINATOR_RABBITMQ_URL` | Message broker connection |
| `COORDINATOR_CONTRACTS_DIR` | Directory containing JSON Schema contracts |
| `COORDINATOR_AWS_ACCESS_KEY_ID` | AWS SDK access key |
| `COORDINATOR_AWS_SECRET_ACCESS_KEY` | AWS SDK secret key |
