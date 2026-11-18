# Backend contract conventions

This specification makes ADRs 0010, 0012–0015, 0019–0021, and 0025–0029 executable. ADRs remain authoritative for *why*; these documents specify *what must hold*. No frontend implementation is specified.

- Public API: `contracts/openapi/api.yaml` (OpenAPI 3.1, JSON Schema compatible). Public paths are routed through the stateless Gateway to their owning service.
- Broker messages: `contracts/messages/`. Envelope fields are always `messageId`, `correlationId`, `type`, `version`, `occurredAt`, `payload`.
- State and conditional-write rules: `docs/backend/state-and-recovery.md`.
- Publication and replay: `docs/backend/publication.md`.
- Initial values and operations: `docs/backend/operations.md`.

## Normative invariants

| ID | Invariant | Source |
|---|---|---|
| INV-01 | An accepted POST archive submission is durably registered before HTTP 202; retry with its idempotency key does not create a second run | ADR-0010; API |
| INV-02 | Services never read or write another service's DynamoDB tables; Gateway has no owned application database | ADR-0005 |
| INV-03 | Every state-derived outgoing message is written to the owning service's outbox in the same DynamoDB transaction; confirmed publish may be repeated with the same `messageId` | ADR-0020 |
| INV-04 | An inbox record and its DynamoDB business effects commit together; externally effected work has a recoverable durable ledger and idempotent object/document identities | ADR-0020 |
| INV-05 | One normalized navigation identity is admitted at most once per run, and concurrent admission never exceeds `maxPages` | ADR-0013/0025 |
| INV-06 | A task commits only if its lease/fencing generation and current run authorization permit it; stale execution can never replace committed history | ADR-0021 |
| INV-07 | Terminal crawl closure forbids new work, and requires all pending page execution, discovery admission, and minimum-depth reevaluation work to be terminal | ADR-0013/0025 |
| INV-08 | Exactly ten of one hundred simultaneous nonblocking browser reservation contenders succeed in the F5 held-reservation test | ADR-0021 |
| INV-09 | Coordinator selects exactly one irreversible `PUBLISH` or `COMPENSATE` outcome using a conditional transaction; decision and outbox event commit atomically | ADR-0014 |
| INV-10 | A successful seed, terminal crawl, and validated immutable WACZ are prerequisites of `PUBLISH`; indexing success is **not** | ADR-0027 |
| INV-11 | Capture never exposes a prepared but unpublished WACZ; it activates replay only after durable publication authorization and produces `ArchivePublished` | ADR-0027 |
| INV-12 | Search never exposes a run until it has durably observed **both** `ArchivePublicationDecided` and `ArchivePublished` and verified local search-document eligibility; message order is immaterial | ADR-0027/0029; publication spec |
| INV-13 | Archive status depends on archival outcomes and replay readiness, not on indexing failures or OpenSearch availability | ADR-0014/0027 |
| INV-14 | Neither package creation nor publication requires moving/copying WACZ into public S3; objects remain private and immutable and retrieval is authorization-gated | Publication spec |
| INV-15 | A committed snapshot is referenced by stable `snapshotId`; index reconciliation uses final manifest references without reading Capture-private tables | ADR-0019 |
| INV-16 | Interactive login uses a dedicated Capture-owned manager; completed sessions create immutable encrypted auth generations, and repeating finalization never creates a new generation | ADR-0028; API |
| INV-17 | Compensated runs do not become replayable or searchable; stale events, late attempts and duplicated commands cannot reverse a committed decision | ADR-0014/0020/0021 |
| INV-18 | Logs, messages, and API errors do not expose credentials; raw authenticated WARC may contain sensitive material and is always protected by restrictive retrieval policy | ADR-0015/0026 |

## Scope limits

- Concrete HTTP paths and fields are frozen in the OpenAPI specification; service-internal routes, code layout, frontend appearance, and UI components are not.
- Table names/keys below are the initial implementation schema, not business-domain identities. Changes must preserve these invariants and ownership boundaries.
- This documentation does not claim distributed exactly-once execution, a globally atomic visibility instant, perfect offline replay of arbitrary websites, or multi-host fault tolerance.
