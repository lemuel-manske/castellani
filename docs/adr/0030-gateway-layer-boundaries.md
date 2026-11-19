# ADR-0030: Gateway application and service-client boundaries

- Status: Proposed
- Date: 2026-11-19

## Context

Gateway currently uses two incompatible request paths. Archive admission and status go through `application.Application` and a Coordinator client. Pages, snapshots, WACZ, sessions, and search bypass the application and invoke `internal/upstream.Client` directly from API handlers.

The generic upstream client's `JSON(ctx, method, path, query, key, body)` and `Stream(ctx, method, path, byteRange, ifRange)` expose outbound HTTP mechanics to inbound adapters. They give Search an unnecessary streaming capability and force handlers to construct service paths, validate upstream responses, and interpret dependency failures. `common/proxy.go` likewise crosses boundaries by combining upstream result interpretation with public HTTP response writing.

## Decision

Gateway uses one runtime flow for all public operations:

```text
Public HTTP API -> Application -> service-specific client -> net/http
```

The API depends on the application for every operation, never on an outbound client. The application owns use cases, input semantics, and Gateway policy. Clients own their service's outbound HTTP protocol. Dependency interfaces belong with their consumers in `application`; concrete implementations implement them implicitly. Constructors use `NewClient` for clients and `NewHandler` for handlers.

### Application operations

The application exposes operations grouped by responsibility, not by HTTP method:

| Capability | Application operation | Dependency |
|---|---|---|
| Archive admission | `CreateArchive` | Coordinator |
| Archive status | `GetArchive` | Coordinator |
| Captured pages | `ListPages` | Capture |
| Snapshot metadata | `GetSnapshot` | Capture |
| WACZ retrieval | `GetWACZ` | Capture |
| Session creation | `CreateSession` | Capture |
| Session lookup | `GetSession` | Capture |
| Session update | `UpdateSession` | Capture |
| Unified search | `Search` | Search |

The application uses typed, operation-specific inputs (including pagination and search filters) rather than raw query strings and arbitrary HTTP method/path/body parameters. Exact Go signatures and response types are established while implementing each operation; introduce only types justified by a current contract. Retain raw JSON only where the existing public contract intentionally treats content as opaque.

### Outbound client capabilities

Implement three service-specific client packages: `clients/coordinator`, `clients/capture`, and `clients/search`. Each exposes only the operations supported by its upstream service. No client exposes a general-purpose `JSON`, `Stream`, or `Request` method as its application-facing API.

- Coordinator: archive admission and status.
- Capture: page listing, snapshot metadata, WACZ retrieval, and session creation/lookup/update.
- Search: search only. No streaming API or streaming-specific transport configuration.

The clients own route construction, HTTP methods, request encoding, service headers, response decoding, upstream schema checks, timeouts, and transport errors. Use `net/http` directly; remove `internal/upstream` after callers have migrated. Do not create a replacement generic client layer. Shared helpers are justified only by proven meaningful reuse, never by a desire to eliminate small amounts of HTTP plumbing.

### Boundary-specific responsibilities

- **API:** route parameters, HTTP body decoding, headers, public status and problem representation, streaming to `http.ResponseWriter`, and route/readiness middleware. It never imports concrete outbound clients or constructs outbound URLs.
- **Application:** validates domain/use-case inputs, applies Gateway policies, selects the appropriate dependency operation, and exposes transport-independent results or errors. Simple operations may delegate directly; avoid empty wrapper layers and duplicated validation.
- **Clients:** validate upstream responses against their own protocols, map upstream errors into application-consumable error values, and preserve validated information needed for public failure forwarding. They do not write public HTTP responses.
- **WACZ:** only Capture retrieves the streaming body. An operation-specific result exposes a closeable stream and validated delivery metadata without leaking a raw `*http.Response` into API or application contracts. The API owns HEAD behavior and the public response copy. Streaming must remain bounded and must not buffer entire WACZ files.
- **Errors:** transport failures and invalid upstream responses originate in clients; application validation and policy failures originate in the application; the API alone maps both to public HTTP statuses and problem documents. A validated upstream problem may be carried as data where faithful forwarding is required. The API does not inspect generic upstream result/status objects.

### Dependency organization

Keep a single application composition path in `server.go`. The router takes the application (and independent HTTP infrastructure such as readiness and logging), never capture/search clients. Optional dependency wiring must not silently turn application-layer operations into direct API-to-client paths.

Shared route definitions and cross-boundary types remain in an appropriately accessible owning package; do not put service-specific client logic or HTTP response writers in `common`. Interfaces are declared at consumed boundaries, not duplicated in provider packages. Avoid re-export aliases and pass-through helpers.

### Migration and verification

Refactor incrementally, preserving existing externally observable API behavior and OpenAPI contracts. Update `gatewaytest` to construct and exercise the real API -> application -> client chain. Test through public behavior, including invalid upstream responses, problem forwarding, session validation, search, WACZ partial content/HEAD, cancellation and streaming. Enforce the no-client-import rule for API packages. Remove dead `internal/upstream` code and `common/proxy.go` when no longer needed.

The migration is reviewed in stages: (1) contracts and ownership, (2) clients, (3) application, (4) handlers and router, (5) errors and streaming, (6) composition and fixtures, (7) final verification. Each stage requires explicit review before the next.

## Consequences

The API has one dependency boundary and no knowledge of outbound service protocols. Each client exposes only relevant capabilities; Search never inherits WACZ streaming. Use-case and upstream validation have clear ownership, and tests can continue exercising end-to-end Gateway behavior. Some low-level HTTP code may appear in more than one client, which is preferable to a broad, leaky generic client abstraction.

During the migration, the old and new paths may coexist temporarily, but the final architecture prohibits API-to-client calls and public HTTP writers in application or client code.
