# ADR-0008: Monorepo organization and service independence

- Status: Accepted
- Date: 2026-11-18

## Context

The application consists of independently deployed Go, Python, and TypeScript services. Keeping them in one repository simplifies local development, integration testing, contract review, and reproducible deployment. Repository proximity must not be confused with permission to share implementation details across service boundaries.

## Decision

Use a monorepo with the following directory conventions:

- `services/<name>/`: each uniquely named service owns its source code, tests, dependency manifests and lockfiles, and Dockerfile.
- `contracts/`: language-neutral cross-service message and API contracts, not executable shared implementation.
- `docker/`: Docker Compose files and deployment-specific Docker configuration.
- `infra/`: cloud infrastructure provisioning, including the selected Terraform configuration (ADR-0024).
- `docs/`: documentation and ADRs.
- `scripts/`: repository-level development and automation commands.
- `tests/`: cross-service integration and end-to-end tests; service-local tests remain in their services.
- `libs/`: optional, purpose-specific libraries introduced only when concrete, worthwhile code reuse is identified.

Services must not import code from sibling service directories, access sibling services' internals, or use a generic repository-wide `common` or `utils` package. Similar code or data representations may remain duplicated when extracting a library would increase coupling. Any extracted library must have a clear responsibility and explicit consumers.

Each Go service uses an independent Go module. A root `go.work` may coordinate local Go modules and subsequently extracted libraries; it is not a reason to merge services into one module. Docker and CI builds must be able to resolve declared dependencies without relying on undeclared developer-local paths.

Do not mandate a repository-wide build framework or prescribe the internal package layout of each service.

## Consequences

The repository offers shared visibility and tooling without compromising independent builds and deployments. Services manage their dependencies separately, and some duplication is accepted to preserve boundaries. Explicit libraries require their own versioning and build consideration; Docker contexts must include them when used. Cross-service integration is performed through published contracts and public interfaces, not source imports.
