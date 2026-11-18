# ADR-0001: Single-tenant, self-hosted deployment

- Status: Accepted
- Date: 2026-11-18

## Context

The archive is intended to be deployed as a separate installation for each user. It is a course project rather than a hosted multi-tenant product. Requiring accounts and tenant administration would add complexity unrelated to its distributed-systems objectives.

## Decision

Each deployment serves one tenant. The application will not implement an end-user login or multi-tenant data model. The installation will be reproducible locally with Docker Compose; deployment scripts and configuration will be version-controlled.

## Consequences

Application-level tenant isolation and account management are out of scope. An installation still needs appropriate network exposure controls, secure handling of credentials for authenticated website captures, and protection of archived content. Single-tenancy does not make its HTTP endpoints safe to expose publicly without access controls.
