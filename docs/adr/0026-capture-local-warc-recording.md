# ADR-0026: Capture-local WARC recording and fidelity verification

- Status: Accepted
- Date: 2026-11-18

## Context

ADR-0022 selects a custom Playwright-based crawl executor; ADR-0023 selects WARC preservation and WACZ packaging. A Playwright response callback or HAR export does not itself establish complete, correct archival recording. HTTPS, redirects, subresources, authenticated requests, downloads, and service workers introduce fidelity and security risks.

Full Browsertrix crawls would introduce another scheduling authority, conflicting with ADR-0013. A shared recorder service would also complicate per-attempt isolation and cross-replica failure handling.

## Decision

Run a **capture-local WARC recording mechanism inside each Python Capture replica's deployment boundary**, attached to the lifecycle of its browser capture attempts. Use an established HTTP(S) WARC recording proxy or proven recorder instead of implementing a WARC encoder and browser-network recording stack from scratch.

Evaluate pywb's recording facilities as the initial integration candidate and warcprox as an alternative. These are candidates, **not** a claim that either integrates successfully with the selected Playwright and Chromium versions. A recorder may be a supervised local process or embedded component; it is not an additional independently owned microservice or centralized, horizontally shared recording authority.

Every capture attempt must have isolated recording identity and output. Capture workers must not interleave unrelated attempts or authentication contexts in one mutable WARC segment. The recorder must flush and finalize its output before validation/upload and the fenced durable capture commit. WARC segments are immutable, attempt-scoped artifacts; only a currently authorized attempt's verified artifacts can enter the final manifest and WACZ package. Crash residue and stale attempts remain subject to cleanup and reconciliation.

Configure Chromium to route applicable network traffic through the recording path. Direct HTTPX retrieval and browser downloads must also be recorded or represented by valid archival records, rather than silently bypassing WARC preservation. Define explicit behavior for redirects, TLS interception and certificate trust, service workers, caching, and requests that cannot be captured; do not globally disable TLS validation to make a recorder work.

Recorded HTTP traffic can contain cookies, authorization headers, POST bodies, and private content. Treat WARC artifacts as potentially sensitive, restrict access and retention, avoid exposing authentication profiles or secrets in diagnostics, and distinguish required archival HTTP provenance from credential material that must not be disclosed. The exact safe header/body redaction and preservation trade-offs must be tested rather than assuming arbitrary WARC files are safe to publish.

### Acceptance gate

Before scaling implementation beyond the vertical prototype, validate an authenticated, JavaScript-rendered page with essential HTML/CSS/images/fonts and downloads through the selected recorder into WARC, package a valid WACZ, and replay it without contacting the original site. Include redirects, concurrent isolated attempts, failed/interrupted writes, and a comparison against Browsertrix on representative sites. Inspect actual replay fidelity and missing resources, not merely recorder exit codes.

If the capture-local recording integration does not meet acceptable fidelity or performance, evaluate a constrained Browsertrix-based recording fallback while preserving **one DynamoDB frontier** as the only crawl scheduling authority. Do not silently replace page-level scheduling with independent full Browsertrix crawls.

## Consequences

Keeping the recorder with Capture replicas aligns browser execution, recording ownership, crash recovery, and fencing. It may require local recorder lifecycle management, trusted TLS proxy configuration, and per-attempt storage overhead. Browsertrix remains a quality baseline rather than a second scheduler.

This decision intentionally does not pin the recorder implementation until the acceptance gate passes; exact proxy configuration, process model, WARC segment size, and performance thresholds are implementation details. WACZ packaging and public replay visibility remain separate decisions in ADR-0023 and ADR-0027.
