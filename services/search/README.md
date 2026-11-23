# Search

Search indexes captured pages and exposes published documents through a query API. It consumes capture and publication events, reads archived WARC artifacts from S3, and maintains the search index in OpenSearch.

## Development

Requires Node.js 24.16.0 or later. From `services/search`:

- `make install`: install dependencies.
- `make test-infra-up`: start isolated DynamoDB Local, MinIO, OpenSearch, and RabbitMQ.
- `make test-infra-down`: stop local dependencies.
- `make run`: build and start the Search service.
- `make fmt`: format the service.
- `make test-unit`: run unit tests.
- `make test-integration`: run tests requiring local infrastructure.
- `make test`: run unit and integration tests.
- `make check`: run formatting and lint checks.

## Configuration

| Variable                                 | Description                                                          |
| ---------------------------------------- | -------------------------------------------------------------------- |
| `SEARCH_HTTP_PORT`                       | HTTP listen port                                                     |
| `SEARCH_AWS_REGION`                      | AWS SDK region                                                       |
| `SEARCH_AWS_ACCESS_KEY_ID`               | AWS SDK access key                                                   |
| `SEARCH_AWS_SECRET_ACCESS_KEY`           | AWS SDK secret key                                                   |
| `SEARCH_DYNAMODB_ENDPOINT_URL`           | DynamoDB endpoint                                                    |
| `SEARCH_S3_ENDPOINT_URL`                 | S3 endpoint                                                          |
| `SEARCH_OPENSEARCH_URL`                  | OpenSearch endpoint                                                  |
| `SEARCH_RABBITMQ_URL`                    | RabbitMQ connection URL                                              |
| `SEARCH_INDEXING_LEASE_DURATION_SECONDS` | Indexing lease duration. Defaults to 120 seconds                     |
| `SEARCH_INDEXING_MAX_ATTEMPTS`           | Maximum indexing attempts. Defaults to 5                             |
| `SEARCH_RECONNECT_DELAY_MILLISECONDS`    | Delay before reconnecting to RabbitMQ. Defaults to 1000 milliseconds |
