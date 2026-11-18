# ADR-0004: MiniStack for local AWS-compatible infrastructure

- Status: Accepted
- Date: 2026-11-18

## Context

The assignment permits local AWS emulation with MiniStack and requires reproducible, scripted infrastructure. A public cloud account, ongoing costs, and external credentials are unnecessary for the intended demonstration.

## Decision

Use MiniStack as the local AWS-compatible infrastructure target. AWS resources will be created using Terraform from the beginning where supported (ADR-0024), with version-controlled provisioning fallbacks for emulator/provider gaps, never by undocumented manual setup. Docker Compose will start the complete local environment. Service endpoints, resource names, and credentials will come from configuration rather than hard-coded values.

RabbitMQ will run as a separate container because it is not an AWS service.

## Consequences

The application can use AWS SDKs while remaining locally deployable. MiniStack's service support and behavior must be tested for each selected API; emulation is not proof of full AWS feature parity. Terraform-first provisioning is selected in ADR-0024. Emulator/provider parity must be checked using functional tests, and Docker Compose remains the reference orchestration choice in ADR-0016.
