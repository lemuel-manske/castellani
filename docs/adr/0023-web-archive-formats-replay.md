# ADR-0023: Standard web archive recording, packaging, and replay

- Status: Accepted
- Date: 2026-11-18

## Context

Saving rendered HTML alone does not reliably preserve pages' dependencies or enable replay once the original website is unavailable. The archive needs a recognizable preservation format for captured HTTP traffic and a portable collection representation. Browsertrix has already demonstrated usable WACZ-based capture in the related `open-archive` project, providing a practical fidelity baseline.

Our distributed frontier must allow independently captured pages to become available for indexing immediately, without waiting for an entire website to be packaged. A custom recorder and replay engine would add significant implementation risk unrelated to the project's core distributed-systems goals.

## Decision

Use **WARC as the canonical preservation format** for HTTP capture records and **WACZ as the portable archive collection package**. Store immutable WARC segments and resulting WACZ packages in S3; reference them through service-owned metadata and the final crawl manifest. Use an established WACZ-compatible replay implementation such as ReplayWeb.page rather than building a custom HTML-rewriting replay engine.

Capture workers may write independent, attempt-scoped WARC segments; they must not append concurrently to a single mutable WARC file. The authorized capture result durably associates its WARC resources with the page/snapshot identity. Failed and fenced attempts must not become published artifacts. Final collection packaging assembles the authorized segments and required indexes/metadata into WACZ after the relevant capture set is known, without preventing incremental `PageCaptured` events or indexing before packaging.

Reuse a mature WARC recording component or compatible recording proxy, and an existing WACZ packaging implementation, wherever practical. **Do not assume Playwright event listeners or HAR export alone provide complete archival capture.** The exact recording mechanism is a technical integration choice that must be proved before it is treated as supported. Browsertrix is a quality baseline and a fallback engine if the custom executor cannot meet the agreed preservation target; any fallback must preserve the single authoritative distributed frontier rather than silently introducing independent recursive scheduling.

### Early acceptance gate

Before committing substantial implementation effort to the custom recording path, deliver a vertical prototype that captures a JavaScript-rendered, authenticated page with its essential resources into WARC, produces a valid WACZ, and replays it without requiring the original website. Compare representative cases against Browsertrix, including static navigation, redirects, CSS/images/fonts, PDFs/downloads, and authenticated resources. Inspect missing resources and replay behavior rather than accepting a merely successful WARC write.

If the prototype does not meet acceptable fidelity and performance, prefer an established Browsertrix-based recording integration or constrained fallback over developing an unproven recorder from scratch. A fallback must not be represented as complete until its page-task granularity, link-discovery integration, isolation, and resource overhead are validated.

## Consequences

Standard formats improve portability, inspectability, and interoperability with existing replay tooling. They also give the project a strong comparison baseline without requiring feature parity with Browsertrix.

Independent WARC segments, manifest assembly, indexes, and eventual WACZ packaging add artifacts and recovery steps to the SAGA. Packaging failures must be assigned an explicit workflow outcome before publication; the exact transactional boundary and which packages are mandatory remain to be decided alongside the publication protocol. Sensitive authenticated traffic and session material demand explicit retention, access-control, and redaction policies.

This ADR does not select a specific recorder, guarantee perfect reproduction of arbitrary modern websites, prescribe WARC segment sizes, or define exact WACZ tooling and replay delivery endpoints.
