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

## Security Contract

The [HTTP route security matrix](#http-route-security-matrix) is the
authoritative inventory for the 14 routes mounted by
[`src/api/app.py`](../src/api/app.py), including FastAPI's documentation
routes. A route defined elsewhere is not public unless the application mounts
its router.

These endpoints already use:

- explicit request/response schemas
- structured error payloads
- cleaned session snapshot semantics
- router-scoped auth enforcement for the alerts surface

The current alerts router can apply API-key authentication and principal-aware
rate limiting. The limiter is still one local in-memory fixed window, so the
enforcement is per-process rather than distributed. The owning HTTP protection
composition lives in
[`src/api/alert_route_policy.py`](../src/api/alert_route_policy.py), and the
app validates enabled auth/rate-limit settings during startup so invalid
boundary config fails before the first protected request.

### Runtime Mode And Network Exposure

The CLI applies runtime-mode policy and binding separately. Both `local` and
`share` default to `127.0.0.1`, but both currently accept `--host` and pass it
directly to Uvicorn.

| Concern | `local` | `share` |
| --- | --- | --- |
| Default bind address | `127.0.0.1` | `127.0.0.1` |
| Custom bind address | Accepted through `--host`, including non-loopback addresses | Accepted through `--host`, including non-loopback addresses |
| Authentication default | Disabled | Enabled |
| Rate-limit default | Disabled | Enabled |
| Credentials | No key is generated | Generates one strong process-local API key when no manual key is supplied and auth remains enabled |
| Startup output | Mode, listen address, auth state, and rate-limit state | The same summary plus protected-sharing guidance; a generated key is printed once, while a manual key is not echoed |

Lower-level `ESM_API_AUTH_ENABLED` and `ESM_API_RATE_LIMIT_ENABLED` settings
can override either mode's defaults. Startup validation rejects enabled auth
without usable keys, but it does not currently impose a relationship between
run mode and bind address.

**Current audit finding:** non-loopback exposure can happen without selecting
`share`, for example through `api_server_cli local --host 0.0.0.0`. In that
case local-mode auth and rate limiting remain disabled by default. Therefore,
the eventual access policy must consider route, run mode, and bind address
together; `local` must not be interpreted as an enforced loopback-only mode.

This is a documented current-state gap. The later bind/exposure hardening task
will decide and enforce the permitted host-and-mode combinations.

### Security Classification Vocabulary

Use these terms in route, MCP, test, and deployment notes. They describe the
intended access contract; they do not claim that every current route already
enforces it.

| State | Meaning |
| --- | --- |
| `local-public` | Available without authentication only to loopback local use. It is not permission to bind the route to a network-visible host. |
| `share-public` | Deliberately available without authentication in share mode, such as a minimal reachability check. |
| `share-protected` | Requires an API key and the applicable HTTP rate limit in share mode. |
| `local-only` | Available for local use but intentionally unavailable in share mode. This is a route policy, not a transport type. |
| `MCP-local-read-only` | Available only to a trusted local MCP client over stdio and limited to non-mutating tools. |
| `disabled-remotely` | Intentionally has no remote/network transport. This describes the current MCP transport guarantee. |

Always name the relevant mode with `public`. Local openness does not permit
remote exposure, and FastAPI HTTP protections do not apply to MCP stdio.

### HTTP Route Security Matrix

Authentication settings are owned by
[`src/api_boundary_config.py`](../src/api_boundary_config.py), API-key
validation and principal creation by [`src/api_auth.py`](../src/api_auth.py),
and HTTP error mapping by
[`src/api/alert_route_policy.py`](../src/api/alert_route_policy.py). The
alerts router applies `require_http_alert_principal` as a router dependency.
There is no application-wide authentication middleware or endpoint-specific
authentication dependency elsewhere today.

The table states current behavior first. `Intended classification` is proposed
future enforcement, not a claim that the route already has that protection.
All HTTP routes can be network-visible today if either mode is started with a
non-loopback host; the `Remote availability now` column describes the policy
that applies in that case.

| Surface | Operation | Local policy now | Share policy now | Intended classification | Auth and rate limit today | Remote availability now | Owner |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `GET`, `HEAD /openapi.json` | diagnostic | `local-public` | `share-public` | `local-only` | None | Yes; unprotected | FastAPI framework |
| `GET`, `HEAD /docs` | diagnostic | `local-public` | `share-public` | `local-only` | None | Yes; unprotected | FastAPI framework |
| `GET`, `HEAD /docs/oauth2-redirect` | diagnostic | `local-public` | `share-public` | `local-only` | None | Yes; unprotected | FastAPI framework |
| `GET`, `HEAD /redoc` | diagnostic | `local-public` | `share-public` | `local-only` | None | Yes; unprotected | FastAPI framework |
| `GET /health` | diagnostic | `local-public` | `share-public` | `share-public` | None | Yes; public minimal-status route | Health router |
| `GET /detectors` | read | `local-public` | `share-public` | `share-protected` | None | Yes; unprotected | Detectors router |
| `POST /sessions` | mutation | `local-public` | `share-public` | `share-protected` | None | Yes; unprotected | Sessions router |
| `GET /sessions/{session_id}` | read | `local-public` | `share-public` | `share-protected` | None | Yes; unprotected | Sessions router |
| `POST /sessions/{session_id}/cancel` | control | `local-public` | `share-public` | `share-protected` | None | Yes; unprotected | Sessions router |
| `GET /sessions/{session_id}/alerts` | read | `local-public` by default | `share-protected` by default | `share-protected` | Alert dependency; fixed window when enabled | Yes; protected by default in share | Alerts router |
| `GET /sessions/{session_id}/alerts/summary` | read | `local-public` by default | `share-protected` by default | `share-protected` | Alert dependency; fixed window when enabled | Yes; protected by default in share | Alerts router |
| `GET /sessions/{session_id}/alerts/timeline` | read | `local-public` by default | `share-protected` by default | `share-protected` | Alert dependency; fixed window when enabled | Yes; protected by default in share | Alerts router |
| `GET /sessions/{session_id}/alerts/incident-summary` | read | `local-public` by default | `share-protected` by default | `share-protected` | Alert dependency; fixed window when enabled | Yes; protected by default in share | Alerts router |
| `POST /playback/resolve` | control | `local-public` | `share-public` | `share-protected` | None | Yes; unprotected | Playback router |

`local-public` alert routes can become protected only when the lower-level
auth setting is explicitly enabled. That existing alert-router dependency
cannot protect the other routers. The later route-hardening task must apply a
shared policy dependency to the operational routes or provide equally explicit
per-router policy.

### Rate-Limit And Resource Controls

Only the alerts router currently invokes the limiter. When enabled, it uses a
local in-memory fixed window, shared across the four alert routes. The default
budget is 100 requests per 60 seconds, configurable through
`ESM_API_RATE_LIMIT_MAX_REQUESTS` and `ESM_API_RATE_LIMIT_WINDOW_SEC`.
The default identity is the authenticated API-key fingerprint; the optional
`ip` strategy instead uses the request host. When auth is disabled locally,
the principal strategy uses one shared local identity.

| Route family | Rate limited today | Existing input or result control | Missing resource control to record |
| --- | --- | --- | --- |
| Framework docs, OpenAPI, health | No | Small static or constant responses | No route-specific abuse control; share-mode exposure is addressed by the intended route policy |
| Detector catalog | No | Optional `mode` is a fixed enum; catalog is registry-backed | No request budget if exposed remotely |
| Session start | No | `mode` is a fixed enum; source validation rejects blank, unsupported, missing, and disallowed remote sources | No request budget, body-size cap, or detector-count cap before a detached worker is started |
| Session read | No | Session identifier is the only route input | Snapshot may contain unbounded persisted alerts and results; no response cap or pagination |
| Session cancel | No | Session identifier is the only route input | No request budget for a state-changing control operation |
| Alert list, summary, timeline, incident summary | Yes, only through the alerts-router dependency | `severity` is a fixed enum; time ranges are parsed and ordered; invalid values return validation errors | Raw lists and grouped timelines have no pagination or response-size cap; summaries still scan the selected session's alerts |
| Playback resolution | No | `mode` is a fixed enum; source and remote-host trust validation run before resolution | No request budget or body-size cap; resolution can inspect local media paths or validate remote stream URLs |

The protected alerts routes return the standard `429` envelope plus a
whole-window `Retry-After` header. Tests confirm that one exhausted alert
budget does not affect health, documentation, detector, or OpenAPI routes.

The limiter is intentionally local-first, in-memory, and per process. It is
appropriate for current single-process desktop-backed runs, but it is not a
shared-store or multi-worker throttling contract.

**Current audit finding:** authentication and rate limiting are separate
controls. Even after share-mode authentication is extended beyond alerts,
session start, cancellation, playback resolution, and potentially large read
responses still need their own proportionate request, input, or result bounds.
The later resource-abuse task owns those implementation choices.

### Security Gaps And Intended Decisions

This register compares current behavior with the intended access policy. Its
classifications set branch priority; they do not imply that every hosted-system
control belongs in this local-first project now.

| Surface or concern | Current behavior | Intended decision | Classification |
| --- | --- | --- | --- |
| Mode and bind address | `local` accepts non-loopback `--host` values while auth and rate limiting remain off by default | Treat non-loopback binding as an explicit sharing decision; reject or safely promote an unprotected `local` bind | Confirmed unsafe exposure |
| Session start, read, and cancel | No authentication or rate limiting in `share` mode | Make all three `share-protected`; apply proportionate limits to start and cancel, and bound large reads separately | Confirmed unsafe exposure |
| Playback resolution | No authentication or rate limiting in `share` mode | Make the route `share-protected`; retain source and remote-host validation and add an applicable request budget | Confirmed unsafe exposure |
| Alert and incident reads | API-key and fixed-window protection already apply in `share`; raw and timeline responses are unbounded | Preserve `share-protected`; add pagination or response bounds before broader remote use | Acceptable local-first limitation |
| Detector catalog | Unauthenticated in `share` mode | Treat detector metadata as `share-protected` for one consistent remote API boundary | Policy gap requiring a decision |
| `/docs`, `/redoc`, OAuth redirect, and `/openapi.json` | Enabled without authentication in `share` mode | Keep available as `local-public`, but disable in `share` mode | Policy gap requiring a decision |
| `/health` | Returns a small unauthenticated response | Keep `share-public`, limited to minimal reachability/readiness status with no configuration, dependency, or secret detail | Policy gap requiring a decision |
| Share-mode security overrides | Lower-level environment settings can disable auth or rate limiting after `share` supplies secure defaults | Protected sharing must not start network-visible with required controls disabled unless a future explicit unsafe-development override is designed and named | Policy gap requiring a decision |
| HTTP limiter scope | In-memory and per process | Keep for the current single-process runtime; require shared enforcement only before multi-worker or distributed deployment | Later deployment concern |
| MCP tools | Four read-only alert tools run over trusted local `stdio`, without HTTP auth or HTTP rate limiting | Keep `MCP-local-read-only` and `disabled-remotely`; do not add a network transport in this branch | Acceptable local-first limitation |
| Future remote MCP | No network transport exists | Treat remote MCP as a new security boundary requiring separate authentication, authorization, request/result bounds, and error review | Later deployment concern |

The immediate implementation backlog is therefore bounded to bind/mode
enforcement, share-mode protection for operational HTTP routes, framework-doc
availability, minimal health output, and proportionate HTTP resource controls.
Distributed throttling and remote MCP remain deployment-stage work rather than
defects in the current local transport model.

### Policy And Regression Ownership

This document owns the HTTP route, run-mode, and share-mode security policy,
including the intended matrix and its open decisions. The MCP transport and
tool policy belongs in [mcp-server.md](./mcp-server.md#current-tool-inventory).
`contracts.md`, `architecture.md`, testing guidance, and the root README
should link here rather than repeat the matrix.

| Guarantee to protect after implementation | Regression-test owner |
| --- | --- |
| Loopback-only local mode and safe non-loopback/share startup | `tests/test_api_server_cli_runtime.py` |
| Share-mode route availability, authentication scope, and framework-doc availability | `tests/test_api_server_cli_routes.py` |
| API-key failure and success envelopes for protected routes | `tests/test_api_alert_route_auth_policy.py`, expanded or renamed when protection is no longer alerts-only |
| Rate-limit envelopes and route-family budgets | `tests/test_api_alert_route_rate_limit_policy.py`, expanded or renamed with the protected route scope |
| Session/read/playback input and response bounds | A focused route-resource-policy test module added with the resource-control implementation |
| Local stdio-only MCP transport, exact tool allowlist, and read-only capability | `tests/test_mcp_server_contracts.py` |
| MCP alert and incident behavior, including error mapping | Existing `tests/test_mcp_server_*_behavior.py` and `tests/test_mcp_server_*_errors.py` modules |

This map records future regression ownership only. It does not widen the
current security suite before the associated controls exist.

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

FastAPI's HTTP authentication and rate limits do not apply to the separate
local `stdio` MCP server. [mcp-server.md](./mcp-server.md#current-tool-inventory)
owns its exact tool, data-exposure, and result-bound policy; any remote MCP
transport would require a separately designed security boundary.

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

The current CLI-focused test slice reflects that role:

- runtime tests protect mode/default resolution and fail-fast config behavior
- output tests protect operator-facing startup guidance, including custom
  listen-address reflection for manual `share` and `local` startup
- route tests protect the real `local`/`share` boundary behavior without
  treating the CLI as the primary desktop runtime path
- route tests also keep the current public-surface split explicit:
  protected alerts routes versus open `/health`, `/docs`, `/openapi.json`,
  and `/detectors`

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

This route is a read-only HTTP adapter over the shared
`src/session_alerts.py` and `src/session_alert_incidents.py` services, not an
independent query implementation. Its current and intended access policy is
defined once in the [HTTP route security matrix](#http-route-security-matrix).

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

The summary keeps the same top-level key set even when the filtered result set
is empty. Clients should receive zero counts plus `null` timestamp bounds
instead of a special reduced envelope.

Its current and intended access policy is defined once in the
[HTTP route security matrix](#http-route-security-matrix).

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

When no grouped incidents remain after filtering, the route still returns the
same top-level envelope with an empty `entries` list.

Its current and intended access policy is defined once in the
[HTTP route security matrix](#http-route-security-matrix).

### `GET /sessions/{session_id}/alerts/incident-summary`

Returns the grouped incident read model for one session, including:

- total raw alerts
- total grouped incidents
- counts by detector
- counts by severity
- top incident categories by grouped title
- first and last alert timestamps
- one optional short `narrative_summary`

This route is distinct from `/alerts/summary`. The older summary route reports
raw alert counts only; this route reports grouped incident semantics.

Like the other alert routes, the grouped summary keeps a stable envelope for
empty results so clients do not need a separate "no incidents" response
parser. Its current and intended access policy is defined once in the
[HTTP route security matrix](#http-route-security-matrix).

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
