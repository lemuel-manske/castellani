# Capture

Capture executes page-level web captures for Castellani. Its distributed frontier remains the authority for URL admission, task ownership, retries, and crawl completion; browser execution does not schedule work independently.

## Development

> [!NOTE]
> On Linux, `certutil` from `libnss3-tools` must be available so Chromium can trust the attempt-local recorder CA without disabling TLS verification. Each capture attempt owns its recorder process, browser profile, and output directory.

Install the pinned Python toolchain and dependencies with `make install`.

Install the matching Playwright browser with `uv run playwright install chromium`.

For the complete local stack, run `docker compose up -d` from the repository root. The root Compose stack starts MiniStack and RabbitMQ and applies the Terraform configuration, including Capture's DynamoDB tables.

Run the Capture API and worker runtime from this directory:

```sh
DYNAMODB_ENDPOINT_URL=http://localhost:4566 \
RABBITMQ_URL="amqp://castellani:${RABBITMQ_PASSWORD:-local-development-only}@localhost:5672/" \
make run
```

The service-local Compose file provides isolated DynamoDB Local and RabbitMQ dependencies for Capture development and tests. Use `make db-up` and `make db-down` for that environment. The integration-test fixtures create their DynamoDB tables automatically; the runtime expects tables to have been provisioned.

- `make install`: download dependencies.
- `make db-up`: start isolated DynamoDB Local and RabbitMQ.
- `make db-down`: stop local dependencies.
- `make run`: start the Capture API and background worker runtime.
- `make fmt`: format and lint the Python service.
- `make test-unit`: run unit tests.
- `make test-integration`: run tests requiring DynamoDB Local.
- `make check`: run static analysis.

The local recording prototype uses pywb as an HTTP(S) recording proxy. The runtime uses a durable RabbitMQ command queue and a DynamoDB-backed transactional outbox; publisher confirms are required before an outbox record is marked as published.
