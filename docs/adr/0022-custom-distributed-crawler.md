# ADR-0022: Custom distributed web crawler and page execution

- Status: Accepted
- Date: 2026-11-18

## Context

The archive must crawl static, dynamic, and authenticated sites while preserving page-level distribution, recovery, depth/page limits, and incremental indexing. ADR-0013 assigns authoritative URL admission, scheduling, and completion accounting to the Python Capture service's DynamoDB frontier, with RabbitMQ distributing tasks to competing workers. Adopting an additional framework-owned crawl scheduler would produce overlapping sources of truth.

Browsertrix Crawler is a demonstrated capture solution in the related `open-archive` project, but using full independent Browsertrix crawls per job would move link scheduling and task accounting away from the distributed frontier. Reimplementing all browser-recording behavior would also be costly and risky.

## Decision

Implement a **custom Python crawl execution layer**, while reusing established browser and HTTP libraries rather than implementing a browser or HTTP client.

- The DynamoDB frontier remains the only authoritative source for URL admission, scope, depth, page limits, task state, deduplication, ownership, and crawl completion; RabbitMQ distributes admitted work under ADR-0013.
- Use Playwright with Chromium as the primary HTML capture executor for JavaScript-rendered pages and authenticated navigation. Isolate browser contexts by archive run and authentication generation under ADR-0015. Browser availability and concurrent execution remain governed by ADR-0021.
- Use HTTPX for suitable direct HTTP resource retrieval, especially downloadable non-HTML content. Use Selectolax for efficient HTML parsing and extraction of navigational links and resource references where appropriate. These libraries do not own scheduling or retry authority.
- Workers classify navigation versus downloadable resources, preserve requested/final URL and redirect information, discover links, and submit eligible candidates to the shared frontier. The frontier decides whether candidates are admitted; worker-local discovery is not a second task queue.
- Apply explicit crawl scope, URL/network safety controls, per-host politeness/rate limits, resource-size limits, timeouts, and bounded browser execution. Protect against requests to internal or otherwise disallowed network destinations, including redirects.
- Persist page/resource outcomes with enough metadata to distinguish successful capture, blocked authentication, unsupported content, and partial capture with missing dependencies. Failures of secondary pages must not invalidate independently captured pages under ADR-0014.
- Treat complex browser behaviors, infinite scrolling, arbitrary application workflows, streaming content, and perfect replay of every website as best-effort or unsupported rather than making unconditional fidelity claims.

The execution engine must emit immutable capture artifacts and references suitable for the WARC/WACZ preservation path in ADR-0023 and the incremental indexing protocol in ADR-0019.

## Consequences

The project explicitly implements distributed crawl scheduling, retries, ownership, and failure recovery while depending on mature libraries for browser execution and HTML/HTTP mechanics. It avoids the competing task-management semantics of Scrapy/Crawlee/Browsertrix when those tools own an entire crawl.

A custom executor requires integration tests for redirects, authenticated navigation and renewal, dynamic pages, PDFs, link admission, resource limits, and crash recovery. This decision does not imply that Playwright's response events alone form a complete archival recorder. The archival recording implementation and its acceptance gate are addressed separately in ADR-0023.

Exact URL normalization, depth semantics, site-scoping rules, browser interaction policy, and artifact layouts remain separate implementation decisions.
