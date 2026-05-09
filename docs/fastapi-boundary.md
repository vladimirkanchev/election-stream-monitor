# FastAPI Boundary

This document explains the current FastAPI layer in the project: what it does,
how to run it locally, what contract it exposes, and what is still incomplete.

Right now, FastAPI is the owned runtime backend for the main Electron session
bridge. It is still a thin HTTP boundary over the existing local-first
session/domain code, and it does not replace Electron-specific playback or
other desktop/runtime host responsibilities.

The backend is installable for local runtime and development work, but this
repo is still not presented as a polished standalone Python product
distribution.

## Current Status

The FastAPI layer currently provides:

- `GET /health`
- `GET /detectors`
- `POST /sessions`
- `GET /sessions/{session_id}`
- `GET /sessions/{session_id}/alerts`
- `GET /sessions/{session_id}/alerts/summary`
- `GET /sessions/{session_id}/alerts/timeline`
- `GET /sessions/{session_id}/alerts/incident-summary`
- `POST /sessions/{session_id}/cancel`
- `POST /playback/resolve`

These endpoints already use:

- explicit request/response schemas
- structured error payloads
- cleaned session snapshot semantics
- router-scoped auth enforcement for the alerts surface

The current alerts router is authenticated when FastAPI auth is enabled.
The same router can also enforce principal-aware rate limiting when that
setting is enabled. The current implementation uses one local in-memory
fixed-window limiter, so the enforcement is per-process rather than
distributed.
The owning HTTP protection composition now lives in
[`src/api/alert_route_policy.py`](../src/api/alert_route_policy.py), which
keeps the alerts router declarations smaller and keeps auth/rate-limit mapping
local to the boundary.
The FastAPI app also validates the current auth and rate-limit settings during
startup so invalid enabled boundary config fails before the first protected
request.

Current FastAPI access-mode policy:

- `local` is the default run mode
- `local` keeps FastAPI auth and rate limiting disabled by default
- `share` is the protected-sharing preset
- `share` turns FastAPI auth and rate limiting on by default before any
  lower-level overrides apply
- when no manual share-mode API key is configured, the CLI can auto-generate
  one strong process-local key at startup
- the lower-level auth and limiter settings still exist, but run mode is now
  the main top-level UX seam for choosing the default FastAPI security posture

Current alerts-router protection scope:

- `GET /sessions/{session_id}/alerts`
- `GET /sessions/{session_id}/alerts/summary`
- `GET /sessions/{session_id}/alerts/timeline`
- `GET /sessions/{session_id}/alerts/incident-summary`

Current alerts-router rate-limit rule:

- default identity strategy is authenticated principal, keyed by
  `principal.key_id`
- auth-disabled local runs fall back to one deterministic local identity
- alternate `ip` strategy can instead key the budget by request host
- `429` responses use the standard structured API error envelope:
  - `detail = "Rate limit exceeded"`
  - `error_code = "rate_limit_exceeded"`
  - `status_reason = "rate_limit_exceeded"`
  - `status_detail = "Too many requests for the configured window."`
- `429` responses also include `Retry-After` with a coarse whole-window number
  of seconds so clients can retry later without guessing the current budget

Current limitation:

- the limiter is intentionally local-first, in-memory, and per-process
- it is appropriate for the current local backend/runtime model
- it is not yet a shared-store or multi-worker rate-limit contract

Current readiness summary:

- safe to rely on today for:
  - local development
  - demos
  - single-process desktop-backed backend runs
- not yet ready to claim as:
  - multi-worker distributed rate limiting
  - shared-store production throttling
  - remote MCP security coverage
  - a general production-distributed security boundary

Current MCP boundary difference:

- this FastAPI auth/rate-limit boundary applies only in FastAPI `share` mode
  to the HTTP alerts router
- the current MCP server still runs over `stdio` and remains a separate
  local-trust transport
- that means today's `X-API-Key` checks and HTTP `429` limiter contract do not
  automatically secure MCP
- if MCP later becomes remote, reuse the principal identity model, the general
  structured error style, and possibly the limiter concepts, but add them at
  the MCP transport boundary instead of coupling MCP to FastAPI-specific
  request handling

What is still partial:

- playback proxying and renderer-specific media handling still live in Electron
- startup/readiness ownership is in place, but the runtime model still needs
  hardening and broader validation

## Current Runtime State

For normal desktop operation, Electron now talks to the local FastAPI backend.

Electron owns local FastAPI startup/readiness and uses FastAPI for the main
session lifecycle and playback-resolution bridge operations.

Python CLI commands remain available as tooling/debugging commands, not as the
normal Electron runtime backend path.

## Session Ownership

Session start/read/cancel orchestration is now owned by the shared application
service in [`src/session_service.py`](../src/session_service.py).

That means:

- FastAPI is the canonical runtime path for session lifecycle work in the
  desktop app
- [`src/api/routers/sessions.py`](../src/api/routers/sessions.py) is an HTTP
  adapter over that shared service
- [`src/session_cli.py`](../src/session_cli.py) is a tooling/debugging adapter
  over the same shared service
- `run-session` remains the internal worker command used to execute the actual
  detached monitoring run
- detached worker diagnostics belong to a backend-owned
  `data/sessions/<session_id>/worker.log` artifact, not a FastAPI response field
- worker-log capture is intentionally separate from the current API/session
  payload contract; if the product needs UI-visible diagnostics later, add a
  dedicated diagnostics field or endpoint in a follow-up milestone

Operationally, that means FastAPI owns session start, but the actual
monitoring work happens in a detached worker process that now leaves a
session-scoped backend trace in `worker.log`.

The important current rule is:

- do not duplicate session-start orchestration in FastAPI and CLI separately
- change shared session lifecycle mechanics in
  [`src/session_service.py`](../src/session_service.py)
- keep FastAPI-specific error mapping in
  [`src/api/routers/sessions.py`](../src/api/routers/sessions.py)
- keep CLI parsing/printing behavior in [`src/session_cli.py`](../src/session_cli.py)

Recommended reading order for this boundary:

1. [`src/session_service.py`](../src/session_service.py)
2. [`src/api/routers/sessions.py`](../src/api/routers/sessions.py)
3. [`src/session_cli.py`](../src/session_cli.py)

That order mirrors the current ownership split:
shared session mechanics first, then the FastAPI and CLI adapters.

## Current Startup Model

Electron now:

- starts the local FastAPI process when needed
- waits briefly for `/health` during startup
- uses one shared runtime policy for unavailable-backend behavior

The next step is to harden and validate that startup model rather than decide
whether it should exist.

That means:

- validating startup/readiness ownership with focused Electron tests
- deciding whether any development-only escape hatch is still needed
- tightening docs and runtime policy as the model settles

## Run Locally

This backend-only startup path is mainly for development and debugging. The
normal desktop application path is still Electron startup, which owns FastAPI
process launch and readiness for ordinary local use.

For ordinary application use, treat `npm run dev` as the canonical runtime
path. Use direct backend startup only when you intentionally want the backend
without the Electron shell around it.

From the repository root:

```bash
. .venv/bin/activate
PYTHONPATH=src python -m api_server_cli local
```

For temporary protected demo/shared access:

```bash
. .venv/bin/activate
PYTHONPATH=src python -m api_server_cli share
```

If you omit `--api-key` in `share` mode, the CLI generates one API key and
prints it once together with `X-API-Key` usage guidance.

The backend still uses the current flat `src/` module layout, so
`PYTHONPATH=src` remains the intended raw-checkout startup path for this CLI.

The Electron desktop runtime can also start the local FastAPI process as part
of its owned startup/readiness flow. Running `uvicorn` manually is mainly
useful for backend-focused development and debugging.

[`src/session_cli.py`](../src/session_cli.py) also remains available for
tooling and debugging, but it is not a peer startup path to Electron. It is a
shared-service adapter for backend-focused workflows.

Open the interactive docs at:

- `http://127.0.0.1:8000/docs`

## What The API Owns

The FastAPI layer currently wraps stable backend/session behavior:

- detector catalog reads
- monitoring session start
- monitoring session snapshot read
- cancellation request
- validated playback-source resolution

It does not currently own:

- Electron `local-media://` serving
- Electron remote HLS proxying
- desktop/runtime-specific process management
- the full frontend transport path

## Endpoints

### `GET /health`

Simple local backend health check.

### `GET /detectors`

Returns the detector catalog for the current runtime. Optional `mode` filtering
is supported for:

- `video_segments`
- `video_files`
- `api_stream`

### `POST /sessions`

Starts a monitoring session and returns the pending session metadata.

### `GET /sessions/{session_id}`

Returns the current persisted session snapshot.

### `GET /sessions/{session_id}/alerts`

Returns persisted alert events for one session. Current optional filters are:

- `detector_id`
- `severity`
- `start_time_utc`
- `end_time_utc`

This route is intentionally a read-only HTTP adapter over the shared
shared `src/session_alerts.py` and `src/session_alert_incidents.py` services
rather than an independent query
implementation.

This route is currently protected by the FastAPI auth boundary. When auth is
enabled in configuration, callers must send `X-API-Key`.
When FastAPI rate limiting is enabled, this route also participates in the
shared alerts-router request budget.

### `GET /sessions/{session_id}/alerts/summary`

Returns a deterministic summary of one session's persisted alerts, including:

- total alert count
- counts by detector
- counts by severity
- first alert timestamp
- last alert timestamp

The summary remains numeric and deterministic by design. If a later milestone
needs prose or operator-facing explanation, that should be added in a higher
layer such as an MCP or agent workflow rather than changing the core alert
query contract.

This route is currently protected by the same router-level `X-API-Key`
dependency as the rest of the alerts router.
It also participates in the same router-level request budget when FastAPI rate
limiting is enabled.

### `GET /sessions/{session_id}/alerts/timeline`

Returns grouped incident entries for one session after applying the same
optional alert filters:

- `detector_id`
- `severity`
- `start_time_utc`
- `end_time_utc`

The route remains a thin adapter over the shared alert service. Grouping rules
stay deterministic and intentionally simple: ordered alert rows with matching
`detector_id`, `severity`, and `title`, plus a fixed gap threshold.

This route is currently protected by the same router-level `X-API-Key`
dependency as the other alerts routes.
It also participates in the same router-level request budget when FastAPI rate
limiting is enabled.

### `GET /sessions/{session_id}/alerts/incident-summary`

Returns the grouped incident read model for one session, including:

- total raw alerts
- total grouped incidents
- counts by detector
- counts by severity
- top incident categories by grouped title
- first and last alert timestamps
- one optional short `narrative_summary`

This route is currently protected by the same router-level `X-API-Key`
dependency as the other alerts routes.
It also participates in the same router-level request budget when FastAPI rate
limiting is enabled.

This route is distinct from `/alerts/summary`. The older summary route reports
raw alert counts only; this route reports grouped incident semantics.

This route is currently protected by the same router-level `X-API-Key`
dependency as the rest of the alerts router.

### `POST /sessions/{session_id}/cancel`

Requests cancellation for an existing monitoring session.

### `POST /playback/resolve`

Validates monitoring input and returns a playback source contract for the
frontend/Electron layer.

## Structured Error Payloads

Route-level failures use one consistent JSON shape:

```json
{
  "detail": "Session not found",
  "error_code": "session_not_found",
  "status_reason": "session_not_found",
  "status_detail": "No persisted session snapshot found for session_id=abc123"
}
```

Authentication failures use the same envelope with:

- `detail = "Authentication failed"`
- `error_code = "authentication_failed"`
- `status_reason = "authentication_failed"`
- `status_detail` describing the concrete auth failure, such as:
  - missing key
  - invalid key
  - enabled auth without configured keys

Rate-limit failures use the same envelope pattern with:

- `detail = "Rate limit exceeded"`
- `error_code = "rate_limit_exceeded"`
- `status_reason = "rate_limit_exceeded"`
- `status_detail` describing the current limiter rejection

Typical cases include:

- `validation_failed`
- `session_not_found`
- `playback_unavailable`
- `session_start_failed`
- `internal_error`

The API also normalizes request validation failures into the same structured
shape instead of using the default FastAPI validation response.

## Session Snapshot Meaning

`GET /sessions/{session_id}` returns a snapshot with these top-level fields:

- `session`
- `progress`
- `alerts`
- `results`
- `latest_result`

Important `progress` fields:

- `status`
- `status_reason`
- `status_detail`

Use them like this:

- route-level request failure:
  returned as a structured API error payload
- ongoing or terminal session state:
  returned through the session snapshot

That separation is important. A request can succeed while the session itself is
already failed, completed, or cancelled.

Current observability rule:

- session snapshots and start/cancel responses do not surface `worker.log`
  paths yet
- worker diagnostics remain backend-owned until a later milestone deliberately
  adds a public diagnostics surface
- parent-side launch logging and worker-side failure output are both expected
  to land in backend-owned traces rather than in API payloads

## Input Modes

The FastAPI layer currently accepts these monitoring modes:

- `video_segments`
- `video_files`
- `api_stream`

Invalid mode values are rejected at the API boundary.

## Current Integration Limits

This is still a migration-stage backend layer.

Today that means:

- FastAPI wraps the current local-first backend logic and is the owned runtime
  path for session lifecycle work
- CLI entry points still exist for tooling/debugging and scripted inspection
  over the shared session service
- detached worker logs remain backend diagnostics and are not yet surfaced as
  an API or frontend contract
- Electron integration is still partial
- renderer-facing playback concerns still belong to Electron

So the FastAPI layer is already useful and testable, but it is not yet the only
owned runtime concern in the application.
