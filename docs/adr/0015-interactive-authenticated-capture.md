# ADR-0015: Interactive authentication and resumable capture

- Status: Accepted
- Date: 2026-11-18

## Context

A self-hosted archive must capture pages behind website authentication, including linked pages and downloadable resources. Logins may require multi-factor authentication or site-specific interactions, making automated username/password flows brittle. Authentication may expire partway through an archive run, after some pages have been successfully captured.

The Python Capture service uses independent replicas and page-level work distribution (ADR-0013). Sharing one mutable live browser profile across replicas would couple workers and risk corrupting session state. Discarding an entire run when one page requires fresh authentication would contradict the best-effort, page-isolated archive lifecycle (ADR-0014).

## Decision

### Interactive login and isolation

Support interactive target-site login from the initial implementation. The client can start a dedicated browser authentication session, interact with the target website (including MFA), and explicitly finish the login flow. Python captures the resulting browser authentication state for use by the Capture service. The archive application does not require knowledge of the user's password or site-specific login form.

The interactive browser must be accessible to the client even when Python executes headlessly in Docker. It must be isolated, short-lived, and accessible only through an authorized session. The browser delivery technology is an implementation decision.

Authentication is distinct from application login: this single-tenant archive does not introduce user accounts merely to authenticate against target websites.

Protected authentication profiles may serve as reusable source state, but every archive run receives an isolated, versioned authentication context. Python workers create independent Playwright browser contexts initialized from that run's state. Replicas do not concurrently share a mutable browser profile directory. A run's authentication state must not leak into another run, and state updates cannot silently change the context used by in-flight workers.

Authentication material is owned by Python and protected separately from historical archive artifacts. RabbitMQ commands and other service contracts carry opaque references, never cookies, passwords, or raw browser storage state. Browser credentials, session tokens, and sensitive headers must not appear in message payloads, logs, or error responses. **Raw WARC network records can inherently contain cookies, authorization headers, and submitted form data**; such sensitive archival evidence must be secured with access controls, retention/redaction policies, and restricted replay/download rather than incorrectly claiming all raw captures can omit it. A captured page's legitimate authenticated content may itself be sensitive.

### Authentication failure and continuation

An authentication failure is not a successful capture of a login or error page. Python must distinguish detected authentication rejection or expiration from ordinary page failures; the exact detection strategy may be site-dependent.

When a page needs renewed authentication, only tasks depending on the invalid context become blocked in a durable `WAITING_FOR_AUTH`-like state. They are not prematurely counted as terminal failures. Unaffected page tasks continue concurrently; the entire run is not globally paused. The client receives an actionable notification identifying the affected pages, their authentication failure reasons, and the available choices.

The client can:

- **Renew authentication:** start another interactive login for the same run. Python records a new authentication-state generation, makes applicable blocked tasks eligible for retry, and resumes page capture and link discovery without resetting the frontier or repeating already completed tasks.
- **Keep captured pages:** decline renewal. The blocked tasks become terminal capture failures with an explicit authentication reason; other work is allowed to finish, and the Coordinator may publish the successful captures as `COMPLETED_WITH_ERRORS` under ADR-0014.

Refreshing authentication does not guarantee a page will become accessible. A failed or abandoned renewal must not erase previous successful captures. Authentication context generations and execution authorization must prevent stale workers from committing incorrect results after a context is invalidated; the precise fencing protocol is specified separately.

The archive remains one SAGA instance throughout authentication renewal. Blocked tasks must be accounted for by the frontier, so the crawl cannot report completion while it still awaits a client decision. The Coordinator exposes the need for client action as a recoverable, nonterminal condition, not a successful or compensated run. Indexing of already captured pages can continue while other pages await authentication.

### Mandatory seed and publication

The seed page remains mandatory under ADR-0014. If it has not been successfully captured and the client declines authentication renewal, the run cannot publish a partial archive and must follow the pre-publication compensation path. If the seed has been captured successfully, later authentication failures on other pages do not invalidate it or other successful captures.

No staged snapshots or search documents become publicly visible merely because the client has been asked to renew authentication. Publication and compensation continue to follow the SAGA's durable decision boundary.

## Consequences

Interactive authentication supports sites with complex login flows without hard-coding website credentials. Durable per-page blocking and resumption retain successful work and preserve Python replica independence, but introduce user-intervention states, authentication-context generations, and a browser-access surface that must be secured.

A website may not permit multiple independent authenticated browser sessions, and some authentication mechanisms rely on state that cannot be reproduced by copying Playwright storage state alone. Such cases must be detected or reported rather than claiming universal authenticated-capture support.

A separate Capture-owned interactive-login manager, protected S3 auth state, and session lifecycle are defined in ADR-0028. Browser streaming transport, site-specific expiration detection, client-notification transport (polling initially, potentially SSE later), profile retention policy, and exact recovery/fencing algorithms remain implementation decisions. Frontend experience is deferred. An indefinitely unanswered authentication request must not be mistaken for a completed crawl.
