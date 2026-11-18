# ADR-0004: MiniStack for local AWS-compatible infrastructure

- Status: Accepted
- Date: 2026-11-18

## Context

The assignment permits local AWS emulation with MiniStack and requires reproducible, scripted infrastructure. A public cloud account, ongoing costs, and external credentials are unnecessary for the intended demonstration.

## Decision

Use MiniStack as the local AWS-compatible infrastructure target. AWS resources will be created by version-controlled scripts or infrastructure as code, not manually. Docker Compose will start the complete local environment. Service endpoints, resource names, and credentials will come from configuration rather than hard-coded values.

RabbitMQ will run as a separate container because it is not an AWS service.

## Consequences

The application can use AWS SDKs while remaining locally deployable. MiniStack's service support and behavior must be tested for each selected API; emulation is not proof of full AWS feature parity. The choice of Terraform versus another provisioning mechanism and any container orchestration beyond Compose are independent decisions.
