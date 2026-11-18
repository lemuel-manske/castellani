# ADR-0028: Interactive authentication execution and profile protection

- Status: Accepted
- Date: 2026-11-18

## Context

ADR-0015 requires interactive Chromium login with possible MFA, protected reusable state, mid-run renewal, and independent Capture workers. Live interactive browsers are stateful: unlike page tasks, their in-progress sessions cannot be transparently retried on a different Capture worker. Running them inside arbitrarily scaled Capture replicas would require replica-affinity routing. Docker Compose makes that visible, but the underlying issue exists in any horizontally scaled deployment.

The project does not need an additional domain service or frontend design to resolve this backend deployment concern.

## Decision

Deploy a **dedicated Python interactive-login manager process/container** from the Capture codebase, separate from the horizontally scalable page-capture workers. It remains part of the existing **logical Capture service** with Capture-owned persistence, contracts, and domain responsibility; it is not a new independent microservice or database owner. Initially run one manager with a stable internal Compose service endpoint, while scaling ordinary Capture workers independently.

The Gateway forwards authorized interactive-browser connections and lifecycle commands to that stable manager endpoint. The manager supervises multiple short-lived, isolated Chromium login sessions under configurable concurrency and time limits. Each live session has an opaque, unpredictable identifier, durable Capture-owned DynamoDB metadata, and an ephemeral browser process/profile. Live session transport and remote browser connectivity are backend capabilities; the choice of transport and all presentation/frontend details are explicitly deferred.

The manager does **not** need access to the Docker socket to launch a browser process. It must not route requests by guessing Capture worker container IPs or rely on fixed host-bound ports per scalable replica.

Once the user explicitly completes authentication, the manager finalizes and securely stores protected authentication state in S3. Use encryption at rest with an explicitly managed application key or equivalent verified mechanism, protect profile references and permissions, and persist the run's immutable authentication-generation metadata in Capture-owned DynamoDB. Never put raw credentials, cookies, profile data, or sensitive tokens into RabbitMQ, logs, or public error responses.

Workers use isolated browser contexts derived from an authorized, versioned authentication generation; they do not share live mutable browser profile directories. A new login/renewal creates a new generation and reactivates only relevant `WAITING_FOR_AUTH` tasks, subject to execution fencing, under ADR-0015. Browser profile persistence may not cover every site's authentication scheme; unsupported state must be handled explicitly.

If the manager crashes, its live sessions are interrupted and reconciled to an explicit failed/expired state; users can start another session. Previously finalized protected profile generations remain available. Do not attempt live Chromium migration or pretend that an interrupted MFA interaction was resumed.

Expire and clean up abandoned sessions and temporary credentials. Apply authorization, network scope/SSRF controls, and strict isolation between authenticated capture state and downloadable WARC/WACZ artifacts. Any retained archival HTTP requests containing private information require the protection policy of ADR-0026.

## Consequences

The deployment adds a distinct Capture process without creating another business-service boundary. It decouples stateful human-driven browser sessions from scalable, recoverable page work and eliminates the need for a distributed browser-session routing registry in the Gateway.

The single manager is initially a failure point for *active login sessions only*, not for ongoing captures or already persisted auth profiles. Increasing its availability or choosing browser streaming technology is deferred. No frontend framework, UI layout, navigation controls, or noVNC presentation details are decided here.
