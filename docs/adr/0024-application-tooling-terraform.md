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

### Mandatory dependency and toolchain pinning

All application and development dependencies **must be pinned to exact resolved versions**, including direct and transitive dependencies wherever supported. Do not use floating versions, wildcard ranges, unbounded minimums, `latest` tags, or installs that silently resolve to newer releases during CI or deployment.

- **npm / TypeScript:** Use exact dependency declarations (no `^` or `~` ranges) and commit `package-lock.json`. Use `npm ci` for reproducible installs; lockfile changes are reviewed alongside dependency upgrades.
- **Python:** Declare exact dependency versions and commit `uv.lock`. Use `uv sync --frozen` or an equivalent locked install in CI and container builds. Pin the Python interpreter version and the Playwright package/browser revision in a compatible combination.
- **Go:** Specify the Go toolchain version and commit `go.mod` and `go.sum`. Select explicit module versions, keep the module graph reproducible, and use vendoring or another immutable artifact strategy if stronger supply-chain guarantees are required. Do not use `@latest` or uncontrolled `go get` during automated builds.
- **Terraform:** Pin Terraform CLI and provider versions, constrain provider versions to explicit selections, and commit `.terraform.lock.hcl`. Pin referenced modules by immutable versions or commit SHAs.
- **Containers and tooling:** Pin base/service images to immutable digests where practical (otherwise exact tags with controlled updates), as well as linters, formatters, test runners, and other build tools. Dependency updates must be intentional and verified by tests.

The first infrastructure milestone must exercise real DynamoDB conditional transactions, S3 operations, and OpenSearch **document indexing and search** end to end; successfully creating an emulated domain alone is insufficient. Confirm MiniStack's supported OpenSearch data-plane setup before depending on it.

Avoid adding Celery or Temporal: RabbitMQ, the custom frontier, and the Go Coordinator already own delivery and orchestration responsibilities. No separate frontend application is required initially; interactive authentication must still provide a usable remote browser access mechanism under ADR-0015, with its delivery technology chosen separately.

## Consequences

The application uses lightweight frameworks and explicit SDKs to keep distributed algorithms visible and testable. Terraform adds setup and provider-compatibility work at the beginning but produces reproducible infrastructure and supports the assignment's infrastructure-as-code bonus.

The local MiniStack environment is an emulation target, not proof of AWS parity. If a Terraform resource or API is unsupported, validate a documented provisioning fallback while retaining reproducibility; do not silently depend on manually provisioned state. Python browser execution, WARC recording, archival formats, publication/replay, and authentication infrastructure remain governed by ADRs 0022–0023 and 0026–0028.

This ADR fixes the reproducibility policy, while exact pinned version numbers are maintained and deliberately updated in the repository's manifests, lockfiles, and container definitions. Browser deployment, logging/trace exporters, and CI workflow details remain implementation choices.
