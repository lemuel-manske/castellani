# Capture

Capture executes page-level web captures for Castellani. Its distributed frontier remains the authority for URL admission, task ownership, retries, and crawl completion; browser execution does not schedule work independently.

## Development

> [!NOTE]
> On Linux, `certutil` from `libnss3-tools` must be available so Chromium can trust the attempt-local recorder CA without disabling TLS verification. Each capture attempt owns its recorder process, browser profile, and output directory.

Install the pinned Python toolchain and dependencies with `make install`.

Install the matching Playwright browser with `uv run playwright install chromium`.

Start local dependencies with `make db-up`. This starts DynamoDB Local and RabbitMQ.

Run the service locally with:

```sh
DYNAMODB_ENDPOINT_URL=http://localhost:8000 \
RABBITMQ_URL=amqp://castellani:castellani@localhost:5672/ \
make run
```

- `make install`: download dependencies.
- `make db-up`: start DynamoDB Local and RabbitMQ.
- `make db-down`: stop local dependencies.
- `make run`: start the Capture API and background worker runtime.
- `make fmt`: format and lint the Python service.
- `make test-unit`: run unit tests.
- `make test-integration`: run tests requiring DynamoDB Local.
- `make check`: run static analysis.

The local recording prototype uses pywb as an HTTP(S) recording proxy. The runtime uses a durable RabbitMQ command queue and a DynamoDB-backed transactional outbox; publisher confirms are required before an outbox record is marked as published.
