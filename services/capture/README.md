# Capture

Capture executes page-level web captures for Castellani. Its distributed frontier remains the authority for URL admission, task ownership, retries, and crawl completion; browser execution does not schedule work independently.

## Development

> [!NOTE]
> On Linux, `certutil` from `libnss3-tools` must be available so Chromium can trust the attempt-local recorder CA without disabling TLS verification. Each capture attempt owns its recorder process, browser profile, and output directory.

Install the matching Playwright browser with `uv run playwright install chromium`.

- `make install`: download dependencies.
- `make test-infra-up`: start isolated DynamoDB Local and RabbitMQ.
- `make test-infra-down`: stop local dependencies.
- `make run`: start the Capture API and background worker runtime.
- `make fmt`: format and lint the Python service.
- `make test-unit`: run unit tests.
- `make test-integration`: run tests requiring local infra.
- `make test`: runs both unit and integration tests.
- `make check`: run static analysis.

The local recording prototype uses pywb as an HTTP(S) recording proxy. The runtime uses a durable RabbitMQ command queue and a DynamoDB-backed transactional outbox; publisher confirms are required before an outbox record is marked as published.

## Configuration

| Variable | Description |
|---|---|
| `CAPTURE_AWS_ACCESS_KEY_ID` | AWS SDK access key |
| `CAPTURE_AWS_SECRET_ACCESS_KEY` | AWS SDK secret key |
| `CAPTURE_DYNAMODB_ENDPOINT_URL` | DynamoDB endpoint |
| `CAPTURE_S3_ENDPOINT_URL` | S3 endpoint |
| `CAPTURE_RABBITMQ_URL` | RabbitMQ endpoint |
