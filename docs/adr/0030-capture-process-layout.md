# ADR-0030: Capture process layout and route modules

- Status: Accepted
- Date: 2026-11-24

## Context

ADR-0028 requires a dedicated interactive-login process alongside scalable page-capture workers. Both processes implement one logical Capture service under ADR-0002, so they share domain rules, persistence adapters, contracts, and resource ownership. The Python source tree did not make that boundary visible: API code, runtime assembly, configuration, and serialization were mixed under generic `api`, `assembly`, `worker`, and flat `domain`/`application` modules, while login HTTP handlers were defined inline in its application factory.

That layout made process ownership ambiguous, allowed composition roots to import each other, and put unrelated flow facades behind the same package name.

## Decision

Organize Capture source by process while keeping shared code shared:

- `capture/` owns the page-capture process: its API, browser engine, worker, runtime, and settings.
- `login/` owns the interactive-login process: its API, runtime, settings, serialization, and web assets.
- `domain/`, `application/`, `adapters/`, `utils/`, and `topology/` remain shared within the logical Capture service. Their public facades are split by flow as `domain/capture`, `domain/login`, `application/capture`, and `application/login`; no mixed root facade remains.
- Login domain errors live in `domain/login/errors.py` so persistence adapters do not import application modules.

Each process owns its composition root and exposes an application factory: `capture.api:app --factory` and `login.api:app --factory`. No process imports another process's runtime, settings, or composition root. Compose and local `make` targets select the entrypoint explicitly, and the Capture image has no default `CMD`.

HTTP surfaces belong to route modules, not application factories. Capture keeps health routes and shared path constants in `capture/api/routes.py`, with archive metadata and WACZ endpoints in focused route modules. Login keeps all paths, request models, handlers, and VNC proxy helpers in `login/routes.py`; `login/api.py` only builds the application, stores runtime state, and installs exception handlers. Both processes use the shared problem-response helper in `src/problem.py`.

Resource topology remains fixed in versioned Terraform and is mirrored by `topology/tables.py` and `topology/buckets.py`. Bucket names, including `AUTH_PROFILE_BUCKET`, are not configurable; other environment values remain configurable per process.

## Consequences

Process ownership is visible in the tree, so a change to runtime wiring, settings, or transport is less likely to affect the wrong process. The split also removes the adapter-to-application dependency for login errors and makes the explicit uvicorn factories the only supported entrypoints.

The processes still form one Capture service. Shared domain, application, and adapter packages must remain compatible with both flows, and the process split does not create a new business-service or persistence-owner boundary. Public REST behavior and the published OpenAPI contract are unchanged.

Capture runtime construction now includes archive retrieval with the fixed artifact bucket, so the archive metadata and WACZ routes have a complete dependency chain. Raw credentials, cookies, profile data, and sensitive tokens remain excluded from RabbitMQ, logs, and public errors.
