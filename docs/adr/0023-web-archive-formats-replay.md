# ADR-0023: Standard web archive formats and replay interoperability

- Status: Accepted
- Date: 2026-11-18

## Context

An archival crawler must preserve HTTP responses, their resources, and provenance in a portable format rather than relying on raw rendered HTML or a proprietary replay layout. Distributed page workers create records independently, whereas the user ultimately needs a coherent collection archive. A custom replay engine would add complexity unrelated to the project's core distributed-systems goals.

## Decision

Use **WARC as the canonical HTTP preservation format** and **WACZ as the portable collection package**. Store immutable captured WARC segments and validated WACZ packages in S3 with stable references and provenance. Preserve original capture timestamps and requested URLs so multiple historical snapshots can coexist.

Do not have multiple workers append to a shared mutable WARC. Individual attempts produce separately identifiable immutable segments; the final collection package contains only successfully authorized capture records. Packaging must retain the indexes/metadata necessary for standard WACZ replay and direct navigation to an archived URL and timestamp.

Use **self-hosted ReplayWeb.page** as the replay engine for published WACZ archives, rather than writing a custom historical HTML-rewriting engine. The replay engine is distinct from the application's unified OpenSearch query API (ADR-0029).

The **recording integration and fidelity acceptance gate** belong in ADR-0026. **Package preparation, publication authorization, and replay visibility** belong in ADR-0027. This ADR establishes artifact formats and replay interoperability only.

## Consequences

The archive has a portable preservation format, independent of its search index and metadata databases. Replaying content still depends on sufficient recorded resources; valid WARC/WACZ syntax alone does not guarantee faithful rendering.

WARC files can contain sensitive authenticated HTTP records and must be protected according to ADR-0026 and ADR-0028. Specific recorder/proxy selection, package writer, compression, object keys, byte-range delivery details, and performance tuning are implementation decisions.
