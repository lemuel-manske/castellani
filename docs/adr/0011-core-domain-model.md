# ADR-0011: Core domain model and archival semantics

- Status: Accepted
- Date: 2026-11-18

## Context

The system captures websites repeatedly, preserves historical content, indexes captured pages, and compares versions. These operations need consistent domain terminology that is independent of database tables, crawler internals, and messaging protocols.

A website crawl can cover multiple pages captured at different times. Treating the whole run as a single instantaneous snapshot would misrepresent what was captured.

## Decision

Use the following core domain concepts:

- Collection: a logical group of related pages and their historical captures.
- Page: a logical page identity within a collection, maintained across captures.
- Archive Run: one requested archival execution, potentially discovering and capturing multiple pages.
- Snapshot: an immutable historical capture of one page, produced by an archive run.
- ChangeSet: derived information describing differences between two snapshots.

An archive run may produce multiple page snapshots. A page may have multiple snapshots from different runs. Re-archiving a page creates a new historical snapshot rather than overwriting an earlier committed capture.

Captured evidence and its provenance are immutable once committed. Operational status and derived representations, including search indexes and ChangeSets, may be updated or rebuilt without rewriting historical captured content. A ChangeSet must not mutate either snapshot being compared.

Each page snapshot records its actual capture time. An archive run groups captures performed during the same operation but does not claim that all pages reflect a single globally atomic point in time.

This ADR defines conceptual identities and relationships, not their physical storage schemas. In particular, it does not prescribe URL normalization or the rules for deciding when two URLs represent the same logical Page.

## Consequences

Historical retrieval and comparisons are grounded in stable, immutable evidence. Reindexing or recomputing a diff does not itself create a historical version. Storage must preserve committed artifacts and their associations with pages and runs.

The rules for URL identity and normalization, authenticated-context identity, partial crawl outcomes, snapshot commit and compensation, artifact manifests, and diff algorithms require separate decisions.
