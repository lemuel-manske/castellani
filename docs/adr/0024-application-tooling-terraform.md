# ADR-0024: Application tooling and Terraform-first infrastructure

- Status: Accepted
- Date: 2026-11-18

## Context

ADRs 0002–0007 establish Go, Python, and TypeScript services with RabbitMQ, DynamoDB, S3, OpenSearch, and MiniStack. ADR-0016 establishes Docker Compose as the single-host deployment. The project needs a small, reproducible implementation stack that leaves distributed behavior explicit instead of outsourcing the SAGA or distributed frontier to another orchestration framework.

The local infrastructure must be provisioned from versioned code. Initial development should use Terraform rather than defer infrastructure as code until after the application is built. Frontend work is not part of the initial scope.

## Decision

Use the following implementation baseline:

- **Go Gateway and Coordinator:** Go standard HTTP facilities with `chi` for routing, AWS SDK for Go v2, and `amqp091-go` for RabbitMQ. Use standard `testing` and structured `log/slog` logging.
- **Python Capture:** Python with `asyncio`, FastAPI for service/control endpoints, Playwright/Chromium for browser execution, HTTPX and Selectolax for retrieval/parsing, `aio-pika` for RabbitMQ, and `boto3` for S3/DynamoDB. Blocking SDK operations must not stall the asyncio event loop. Use `pytest`, Ruff, and Pyright.
- **TypeScript Search and Index:** Node.js, TypeScript, Fastify for HTTP endpoints, `amqplib` for RabbitMQ, AWS SDK for JavaScript v3, and the official OpenSearch JavaScript client. Use JSON Schema validation (for example Ajv), Vitest, TypeScript checks, and lint/format tools.
- **Dependencies and packaging:** Go modules, Python `uv`, and **plain npm** with a committed `package-lock.json` for Node packages. Do not introduce pnpm.
- **Cross-service verification:** Go-based integration/end-to-end tests and reproducible scripts that enforce the behavior specified in ADR-0018.
- **Infrastructure:** Terraform from the start to provision supported MiniStack AWS-compatible resources, particularly DynamoDB tables, S3 buckets, and OpenSearch resources. Keep RabbitMQ exchange/queue setup in versioned broker bootstrap/configuration or a proven provider where appropriate. Terraform must be invoked through reproducible initialization commands integrated with Docker Compose; the reference environment remains startable using the single-command contract of ADR-0016.

Pin toolchain and container versions and commit dependency lockfiles. The first infrastructure milestone must exercise real DynamoDB conditional transactions, S3 operations, and OpenSearch **document indexing and search** end to end; successfully creating an emulated domain alone is insufficient. Confirm MiniStack's supported OpenSearch data-plane setup before depending on it.

Avoid adding Celery or Temporal: RabbitMQ, the custom frontier, and the Go Coordinator already own delivery and orchestration responsibilities. No separate frontend application is required initially; interactive authentication must still provide a usable remote browser access mechanism under ADR-0015, with its delivery technology chosen separately.

## Consequences

The application uses lightweight frameworks and explicit SDKs to keep distributed algorithms visible and testable. Terraform adds setup and provider-compatibility work at the beginning but produces reproducible infrastructure and supports the assignment's infrastructure-as-code bonus.

The local MiniStack environment is an emulation target, not proof of AWS parity. If a Terraform resource or API is unsupported, validate a documented provisioning fallback while retaining reproducibility; do not silently depend on manually provisioned state. Python browser execution, WARC recording, and replay remain governed by ADRs 0022–0023.

This ADR records a baseline, not immutable library versions. Specific package versions, Terraform modules/providers, browser deployment, logging/trace exporters, and CI workflows are implementation details.
