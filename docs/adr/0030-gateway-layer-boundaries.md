# ADR-0030: Gateway application and service-client boundaries

- Status: Accepted
- Date: 2026-11-19

## Context

Previously, Gateway used two incompatible request paths. Archive admission and status go through `application.Application` and a Coordinator client. Pages, snapshots, WACZ, sessions, and search bypassed the application and invoked `internal/upstream.Client` directly from API handlers.

The former generic upstream client's `JSON(ctx, method, path, query, key, body)` and `Stream(ctx, method, path, byteRange, ifRange)` expose outbound HTTP mechanics to inbound adapters. They gave Search an unnecessary streaming capability and forced handlers to construct service paths, validate upstream responses, and interpret dependency failures. `common/proxy.go` likewise crossed boundaries by combining upstream result interpretation with public HTTP response writing.

## Decision

Gateway uses one runtime flow for all public operations:

```text
Public HTTP API -> Application -> service-specific client -> net/http
```

The API depends on the application for every operation, never on an outbound client. The application owns use cases, input semantics, and Gateway policy. Clients own their service's outbound HTTP protocol and service-local types. Dependency interfaces belong with their consumers in `application`. Clients do not import application interfaces, DTOs, or errors. A dedicated `assembly` package implements the application ports with adapters over the concrete clients; the composition root creates and wires these adapters. Constructors use `NewClient` for clients and `NewHandler` for handlers.

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

The application uses typed, operation-specific inputs (including pagination and search filters) rather than raw query strings and arbitrary HTTP method/path/body parameters. Types should be introduced only where justified by a current contract. Retain raw JSON only where the existing public contract intentionally treats content as opaque.

### Outbound client capabilities

Three service-specific client packages are implemented: `clients/coordinator`, `clients/capture`, and `clients/search`. Each exposes only the operations supported by its upstream service. No client exposes a general-purpose `JSON`, `Stream`, or `Request` method as its application-facing API.

- Coordinator: archive admission and status.
- Capture: page listing, snapshot metadata, WACZ retrieval, and session creation/lookup/update.
- Search: search only. No streaming API or streaming-specific transport configuration.

The clients own route construction, HTTP methods, request encoding, service headers, response decoding, service-local DTOs and errors, upstream schema checks, timeouts, and transport errors. The assembly adapters translate their results and failures into application-owned representations; there is no common service-contract package. Use `net/http` directly; the former `internal/upstream` package has been removed. Do not create a replacement generic client layer. Shared helpers are justified only by proven meaningful reuse, never by a desire to eliminate small amounts of HTTP plumbing.

### Boundary-specific responsibilities

- **API:** route parameters, HTTP body decoding, headers, public status and problem representation, streaming to `http.ResponseWriter`, and route/readiness middleware. It never imports concrete outbound clients or constructs outbound URLs.
- **Assembly:** implements the application ports by calling concrete clients and explicitly mapping client input, result, and error types to application contracts; it owns the dependency construction. No generic common contracts layer is introduced.
- **Application:** validates domain/use-case inputs, applies Gateway policies, selects the appropriate dependency operation, and exposes transport-independent results or errors. Simple operations may delegate directly; avoid empty wrapper layers and duplicated validation.
- **Clients:** validate upstream responses against their own protocols, expose client-local result and error types, and preserve validated information needed for public failure forwarding. They do not write public HTTP responses or import application.
- **WACZ:** only Capture retrieves the streaming body. An operation-specific result exposes a closeable stream and validated delivery metadata without leaking a raw `*http.Response` into API or application contracts. The API owns HEAD behavior and the public response copy. Streaming must remain bounded and must not buffer entire WACZ files.
- **Errors:** transport failures and invalid upstream responses originate in clients; application validation and policy failures originate in the application; the API alone maps both to public HTTP statuses and problem documents. A validated upstream problem may be carried as data where faithful forwarding is required. The API does not inspect generic upstream result/status objects.

### Dependency organization

Keep a single application composition path in `server.go`, via `assembly.NewApplication`. The router takes the application (and independent HTTP infrastructure such as readiness and logging), never capture/search clients. Optional dependency wiring must not silently turn application-layer operations into direct API-to-client paths.

Shared route definitions and cross-boundary types remain in an appropriately accessible owning package; do not put service-specific client logic or HTTP response writers in `common`. Interfaces are declared at the application boundary and implemented by assembly adapters; provider clients have no application-layer imports. Avoid re-export aliases and pass-through helpers.

### Verification

`gatewaytest` assembles the production application and service-specific clients behind HTTP test services, exercising the actual API -> application -> assembly adapter -> client chain. Service-local tests cover archive admission, page and snapshot response validation, session behavior, search, error forwarding, and WACZ streaming, HEAD, and range requests. Import-boundary tests reject API imports of outbound clients and outbound-client imports of application or assembly. The Gateway's `make check` runs static analysis and race-enabled tests.

## Consequences

The API has one dependency boundary and no knowledge of outbound service protocols. Each client exposes only relevant capabilities; Search never inherits WACZ streaming. Use-case and upstream validation have clear ownership, and tests can continue exercising end-to-end Gateway behavior. Some low-level HTTP code may appear in more than one client, which is preferable to a broad, leaky generic client abstraction.

The old generic upstream client, direct API-to-client paths, and the mixed-responsibility proxy helper have been removed. Public HTTP response writing remains exclusively in the inbound API.
