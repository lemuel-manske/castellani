# Search testing policy

Search tests should exercise real behavior at the highest practical level of integration.

## Pure domain logic

Test pure functions directly with real inputs and outputs. Do not mock collaborators or modules. These tests belong under `test/domain` and run with `npm test`.

## Application workflows

Prefer real application services and real internal implementations. When an external boundary must be isolated, use a small stateful in-memory implementation rather than interaction mocks. Keep these tests focused on application behavior; verify the actual infrastructure adapters separately against their real local services.

## Infrastructure adapters

Use the local services defined in `compose.yaml` for persistence, messaging, object storage, and search infrastructure. Adapter tests must verify observable behavior against those services, including conditional writes, concurrency, serialization, delivery, and query semantics. Do not substitute mocked SDK clients for these tests.

## Permitted test doubles

Mocks are not the default. Use them only when a failure mode cannot be reproduced reliably with a real dependency, or when controlling an inherently nondeterministic boundary is necessary. Prefer injecting clocks, ID generators, and other narrow deterministic dependencies over mocking modules.

## Commands

- `make test-unit`: pure domain tests and application tests using real internal logic with in-memory boundary implementations.
- `make test-infra-up`: start DynamoDB Local, OpenSearch, and RabbitMQ.
- `make test-integration`: run adapter and infrastructure integration tests; required endpoints must be configured and missing infrastructure must fail the suite.
- `make test`: run both unit and integration suites.
