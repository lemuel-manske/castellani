# ADR-0006: S3 for archive artifacts

- Status: Accepted
- Date: 2026-11-18

## Context

A web archive preserves page content and potentially associated assets across multiple captures. These artifacts can be large and should not be embedded in DynamoDB records or a full-text search index.

## Decision

Use AWS S3-compatible object storage, provided locally by MiniStack, for captured artifacts. Keep structured processing metadata in service-owned databases and searchable representations in the search index. Archive artifacts will be referenced by stable identifiers rather than copied into messages.

## Consequences

Object storage separates large binary and text artifacts from workflow metadata and search projections. Uploads and deletions are not part of a DynamoDB transaction, so partial writes and SAGA cleanup must be handled explicitly. Artifact naming, manifests, retention, and deduplication remain future decisions.
