# ADR-0029: Unified full-text search and historical replay navigation

- Status: Accepted
- Date: 2026-11-18

## Context

The archive provides full-text retrieval across historical collections, archive runs, and individual pages. ReplayWeb.page can offer collection-local search, but exposing that alongside OpenSearch would create two application search paths with different ranking, filtering, and failure behavior. The user should use one contract whether searching all archives or only one collection. Historical search is a derivative of preserved content and must not determine whether a validated WACZ can be replayed.

## Decision

Expose **one application search API**, through Go Gateway to the TypeScript Search & Index service, backed exclusively by OpenSearch. The same endpoint, result schema, ranking, highlighting, pagination, and error semantics apply regardless of scope. Optional filters restrict queries to a collection, archive run, snapshot, and/or capture time range; omitting filters searches all published archival content.

Results refer to matching **historical snapshots**, not merely source websites. Each result includes relevant archive/collection and snapshot identifiers, original URL, capture timestamp, title or metadata where available, and a highlighted matching snippet. Highlighted snippets must be safely encoded (or returned as structured ranges), never trusted as unescaped HTML. Ranking is performed by the Search service.

Selecting a result resolves the corresponding published WACZ, captured URL, and timestamp for direct navigation through the self-hosted ReplayWeb.page engine defined in ADR-0027. ReplayWeb.page is a **replay engine, not a second application search backend**. Do not expose a separate built-in WACZ search API or maintain a second app-specific indexing pipeline solely for collection-scoped queries.

Search only returns authorized, published snapshots. It must not surface staged/compensated runs merely because their OpenSearch documents exist. Search availability, index catch-up, repair, and terminal indexing failures are observable separately from archival publication. If OpenSearch is unavailable, search can fail explicitly while replay of published WACZ remains operational.

Search never mutates immutable WARC/WACZ artifacts. Within-page match highlighting in the replayed document is not required initially; matching snippets in results and opening the correct historical snapshot are sufficient. Portable WACZ metadata or optional independent interoperability features must not be confused with a second search API.

## Consequences

One query implementation supports global, per-collection, and per-archive search, reducing divergent behavior and maintenance overhead. All application search scopes depend on OpenSearch; there is deliberately no fallback to ReplayWeb.page local search when the index is unavailable.

The unified `/search` API and filter/result contract are specified in [OpenAPI 3.1](../../contracts/openapi/api.yaml). OpenSearch mappings, analyzer selection, ranking weights, and frontend presentation remain implementation details. Search must not expose a result until the corresponding WACZ has been durably activated for replay under ADR-0027.
