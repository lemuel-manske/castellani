# ADR-0005: DynamoDB tables owned by individual services

- Status: Accepted
- Date: 2026-11-18

## Context

The assignment requires database-per-service ownership and forbids services from reading or writing each other's databases. DynamoDB does not organize tables inside separately named databases as a relational server does.

## Decision

Use one DynamoDB infrastructure service provided through MiniStack. Every stateful microservice exclusively owns its tables, data model, and access layer. No service may read, write, or transact against another service's tables. Cross-service state changes are communicated through messages, not shared database access.

The stateless API Gateway has no application database.

## Consequences

Services can evolve their persistence models independently while sharing the underlying DynamoDB infrastructure. They also share its availability and operational failure domain. In real AWS, table-scoped IAM permissions can enforce isolation; equivalent enforcement in MiniStack must not be assumed without verification. We will document this as logical database-per-service isolation and confirm that interpretation with the professor if necessary.
