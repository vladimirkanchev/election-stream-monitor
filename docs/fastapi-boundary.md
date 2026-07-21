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
- router-scoped authentication for operational HTTP routes

Session and playback routers use shared API-key authentication. The alerts
router adds principal-aware rate limiting. The limiter is one local in-memory
fixed window, so enforcement is per-process rather than distributed. Shared
HTTP authentication lives in
[`src/api/http_auth_policy.py`](../src/api/http_auth_policy.py); alert-specific
rate-limit composition remains in
[`src/api/alert_route_policy.py`](../src/api/alert_route_policy.py).

### Runtime Mode And Network Exposure

The CLI applies runtime-mode policy and binding together. Both `local` and
`share` default to `127.0.0.1`; only `share` may intentionally bind a
network-visible host.

| Concern | `local` | `share` |
| --- | --- | --- |
| Default bind address | `127.0.0.1` | `127.0.0.1` |
| Custom bind address | Canonical loopback values only | Loopback, wildcard, and network-visible values through `--host` |
| Authentication default | Disabled | Enabled |
| Rate-limit default | Disabled | Enabled |
| Credentials | No key is generated | Generates one process-local API key from 24 random bytes (192 bits) only when neither the CLI nor environment configuration supplies one and auth remains enabled |
| Startup output | Mode, listen address, auth state, and rate-limit state | The same summary plus protected-sharing guidance; a generated key may be displayed intentionally, while a manual key is not echoed |

`ESM_API_AUTH_ENABLED` can opt local mode into authentication, but it cannot
disable authentication in `share` mode: that configuration fails before
startup. `ESM_API_RATE_LIMIT_ENABLED` can still override the mode default.
Startup validation also rejects enabled auth without usable keys. The CLI
separately rejects non-loopback or malformed local binds before runtime setup
or Uvicorn handoff.

Focused settings and CLI tests cover the supported false-like auth overrides,
including conflicting manual API-key configuration, so this guarantee does not
depend on startup documentation alone.

### Secret-Bearing Surface Audit

This audit distinguishes the one intentional direct-terminal disclosure of a
generated share key from unsafe disclosure through logs, errors, artifacts, or
persisted configuration.

| Surface | Secret flow | Current protection | Gap or follow-up |
| --- | --- | --- | --- |
| Manual API key | `--api-key` or `ESM_API_AUTH_ALLOWED_KEYS` enters `ApiAuthSettings` and the request-auth seam | CLI input takes precedence over the environment; an omitted flag preserves an environment key; blank explicit entries fail without echoing their value | Generated-key output is handled separately. |
| Generated share key | `secrets.token_urlsafe(24)` creates an in-memory `ApiAuthSettings` key when share auth has no configured key | The key is process-local and appears once in direct CLI output; generated commands use a placeholder, and normal auth telemetry never logs the key | A later deployment path should use managed secrets rather than terminal disclosure. |
| Request header | `X-API-Key` is normalized and compared inside `api_auth.py` | Auth-failure logs record only a route path and fixed reason code; the authenticated principal carries a fingerprint rather than the raw key | Successful-request telemetry is not added in this branch. |
| PostgreSQL URL | Session and alert database URL env values flow through typed settings into the selected PostgreSQL driver | Configuration validation names settings without values; connection and bootstrap failures are sanitized | Detailed diagnostic and worker handling is owned by [session-persistence-audit.md](./session-persistence-audit.md#credential-diagnostics). |
| Detached worker | `session_service` copies the parent environment and redirects worker stdout/stderr to the session worker log | The worker preserves persistence selection but excludes FastAPI API-key settings; persistence errors are sanitized before they reach worker diagnostics | A later deployment path can narrow inherited environment variables further. |
| CI and test helpers | Tests use fixture credentials; weekly PostgreSQL jobs pass a disposable service URL to helpers | Alert weekly helpers redact their printed plan and GitHub masks configured secrets in CI output | Keep real deployment credentials out of workflow literals and add redaction tests for any helper that reports connection failures. |

### Secret-Handling Contract

The following enforced contract covers supported FastAPI and worker paths.
PostgreSQL-specific diagnostic handling is summarized here and detailed in the
[persistence audit](./session-persistence-audit.md#credential-diagnostics).

| Channel | Required behavior |
| --- | --- |
| Logs, exceptions, tracebacks, worker logs, CI artifacts, and routine diagnostics | Never contain a raw API key, request header value, database password, or complete credential-bearing PostgreSQL URL. A sanitized failure may retain the backend, setting name, host, and error class. |
| Manual API keys | Are never echoed in CLI output, logs, errors, or generated commands. A blank or malformed explicitly supplied key is a configuration error, not a request to generate another key. |
| Generated share key | Uses 24 random bytes (192 bits) in process memory only, is not written to environment variables or files, and may appear exactly once in direct interactive CLI stdout. Example commands must use a placeholder rather than repeat the raw key. |
| Configuration errors | Identify the invalid setting and actionable expected form without showing the supplied value. The same rule applies to CLI parsing, runtime settings, and bootstrap errors. |
| PostgreSQL diagnostics | Redact URL credentials and sensitive query values before they reach observable errors or diagnostics. Safe endpoint context may remain when useful. |

Key resolution is deterministic: `--api-key` overrides
`ESM_API_AUTH_ALLOWED_KEYS`; when neither is configured, enabled share mode
generates one process-local key. Omitted configuration is distinct from an
explicit blank value, which fails before startup without echoing the value.

`--api-key` remains a local operator convenience, not a recommended deployment
secret transport: operating systems may expose command arguments to the local
user or process inspector. It must still obey the no-log and no-echo rules
above. A future secret-manager or deployment integration can provide a safer
injection mechanism without changing this HTTP contract.

### Bind And Startup Ownership

The current startup paths are intentionally distinct. This inventory records
where a host can enter the system so later bind enforcement does not disrupt
the Electron desktop path.

| Startup path | Bind or target owner | Current behavior | Relevant confidence |
| --- | --- | --- | --- |
| `python -m api_server_cli local|share` | `api_server_cli` parses and classifies `--host` before Uvicorn handoff | Both modes default to `127.0.0.1`; `local` accepts only canonical loopback values, while `share` accepts valid network-visible binds | `tests/test_api_bind_policy.py`, `tests/test_api_server_cli_runtime.py`, `tests/test_api_server_cli_output.py` |
| Electron desktop runtime | `frontend/electron/fastApiLocalRuntimeConfig.mjs` fixes the spawned backend host to `127.0.0.1` | Starts a local Uvicorn child through the startup orchestrator; normal desktop startup has no user-selected bind host and the backend's local mode remains keyless by default | `frontend/electron/fastApiStartupOrchestrator.test.mjs`, `tests/test_api_server_cli_routes.py` |
| Electron external-backend override | `ELECTION_API_BASE_URL` | Electron does not spawn a local backend and sends bridge requests to the supplied URL | Electron client and startup-policy tests |
| Raw Uvicorn command | operator shell | `uvicorn api.app:app --app-dir src` bypasses CLI mode and host handling; application lifespan validates auth and limiter settings only | backend-only development path |

`src/api_boundary_config.py` owns current run-mode, authentication, and
rate-limit validation. It does not receive a bind host, so it cannot currently
enforce a host-and-mode relationship. The FastAPI application lifespan calls
that validation for every startup path, but it cannot distinguish the CLI,
Electron, or raw-Uvicorn launcher.

### Bind-Policy Contract

The following policy is enforced by the supported `api_server_cli` startup
path before settings resolution, startup output, or Uvicorn handoff.

| Mode | Host class | Required outcome |
| --- | --- | --- |
| `local` | Canonical loopback: any IPv4 address in `127.0.0.0/8`, IPv6 `::1`, or exact `localhost` | Allowed; API-key authentication remains off by default. |
| `local` | Wildcard or non-loopback: `0.0.0.0`, `::`, private or public IPs, custom hostnames, IPv4-mapped IPv6, malformed values, or whitespace-padded values | Rejected before startup with guidance to use `share` for intentional network exposure. |
| `share` | Loopback | Allowed; API-key authentication is required. |
| `share` | Wildcard or non-loopback, including `0.0.0.0`, `::`, private/public IPs, and valid hostnames | Allowed; API-key authentication is required. |

`localhost` is the sole hostname accepted by `local` mode. The implementation
must not resolve arbitrary hostnames and infer safety from the result: DNS or
host-file configuration can vary between machines. Bracketed IPv6 URL syntax,
such as `[::1]`, is not a CLI bind host and should be rejected rather than
silently normalized. The policy also treats IPv4-mapped IPv6 forms as
non-loopback to avoid ambiguous bind behavior.

Electron remains compliant because its managed backend is pinned to
`127.0.0.1`. A raw `uvicorn api.app:app` command has no
run-mode input, so it is a backend-development escape hatch rather than a
supported network-sharing launcher; operators who need non-loopback exposure
must use `api_server_cli share`.

### Security Classification Vocabulary

Use these terms in route, MCP, test, and deployment notes. The route matrix
marks each entry as enforced or still pending; do not infer enforcement from
the vocabulary alone.

| State | Meaning |
| --- | --- |
| `local-public` | Available without authentication only to loopback local use. It is not permission to bind the route to a network-visible host. |
| `share-public` | Deliberately available without authentication in share mode, such as a minimal reachability check. |
| `share-protected` | Requires an API key in share mode and uses a route-specific rate limit when one is assigned. |
| `local-only` | Available for local use but intentionally unavailable in share mode. This is a route policy, not a transport type. |
| `MCP-local-read-only` | Available only to a trusted local MCP client over stdio and limited to non-mutating tools. |
| `disabled-remotely` | Intentionally has no remote/network transport. This describes the current MCP transport guarantee. |

Always name the relevant mode with `public`. Local openness does not permit
remote exposure, and FastAPI HTTP protections do not apply to MCP stdio.

### HTTP Route Security Matrix

Authentication settings are owned by
[`src/api_boundary_config.py`](../src/api_boundary_config.py), API-key
validation and principal creation by [`src/api_auth.py`](../src/api_auth.py),
and shared HTTP `401` mapping by
[`src/api/http_auth_policy.py`](../src/api/http_auth_policy.py). The alerts
router applies `require_http_alert_principal`, which composes that shared
authentication dependency with alert-specific rate limiting. There is no
application-wide authentication middleware or endpoint-specific authentication
dependency elsewhere today.

The table states current behavior first. The authentication columns record
whether an API key is required under each mode's configuration: local mode may
opt into authentication, while share mode cannot opt out. The final policy
column distinguishes active enforcement from decisions still deferred. Network
exposure through the supported CLI requires `share` mode; rate-limit ownership
is recorded in the next section.

| Surface | Operation | Local policy now | Share policy now | Auth required locally | Auth required in share | Current policy owner | Enforcement status | Remote availability now |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `GET`, `HEAD /openapi.json` | diagnostic | `local-public` | `local-only` | No | N/A: endpoint returns `404` | FastAPI framework plus app documentation guard | Enforced: `local-only` | No in share mode |
| `GET`, `HEAD /docs` | diagnostic | `local-public` | `local-only` | No | N/A: endpoint returns `404` | FastAPI framework plus app documentation guard | Enforced: `local-only` | No in share mode |
| `GET`, `HEAD /docs/oauth2-redirect` | diagnostic | `local-public` | `local-only` | No | N/A: endpoint returns `404` | FastAPI framework plus app documentation guard | Enforced: `local-only` | No in share mode |
| `GET`, `HEAD /redoc` | diagnostic | `local-public` | `local-only` | No | N/A: endpoint returns `404` | FastAPI framework plus app documentation guard | Enforced: `local-only` | No in share mode |
| `GET /health` | diagnostic | `local-public` | `share-public` | No | No | Health router | Enforced: minimal `share-public` status | Yes; public minimal-status route |
| `GET /detectors` | read | `local-public` | `share-public` | No | No | Detectors router | Decision pending: `share-protected` | Yes; unprotected |
| `POST /sessions` | mutation | `local-public` by default | `share-protected` | No by default; shared dependency accepts a local principal | Yes | Sessions router through `require_http_principal` | Enforced: `share-protected` | Yes; protected in share |
| `GET /sessions/{session_id}` | read | `local-public` by default | `share-protected` | No by default; shared dependency accepts a local principal | Yes | Sessions router through `require_http_principal` | Enforced: `share-protected` | Yes; protected in share |
| `POST /sessions/{session_id}/cancel` | control | `local-public` by default | `share-protected` | No by default; shared dependency accepts a local principal | Yes | Sessions router through `require_http_principal` | Enforced: `share-protected` | Yes; protected in share |
| `GET /sessions/{session_id}/alerts` | read | `local-public` by default | `share-protected` by default | No by default; alerts dependency accepts a local principal | Yes by default; alerts dependency requires an API key | Alerts router through `require_http_alert_principal` | Enforced: `share-protected` | Yes; protected by default in share |
| `GET /sessions/{session_id}/alerts/summary` | read | `local-public` by default | `share-protected` by default | No by default; alerts dependency accepts a local principal | Yes by default; alerts dependency requires an API key | Alerts router through `require_http_alert_principal` | Enforced: `share-protected` | Yes; protected by default in share |
| `GET /sessions/{session_id}/alerts/timeline` | read | `local-public` by default | `share-protected` by default | No by default; alerts dependency accepts a local principal | Yes by default; alerts dependency requires an API key | Alerts router through `require_http_alert_principal` | Enforced: `share-protected` | Yes; protected by default in share |
| `GET /sessions/{session_id}/alerts/incident-summary` | read | `local-public` by default | `share-protected` by default | No by default; alerts dependency accepts a local principal | Yes by default; alerts dependency requires an API key | Alerts router through `require_http_alert_principal` | Enforced: `share-protected` | Yes; protected by default in share |
| `POST /playback/resolve` | control | `local-public` by default | `share-protected` | No by default; shared dependency accepts a local principal | Yes | Playback router through `require_http_principal` | Enforced: `share-protected` | Yes; protected in share |

Operational routers share `require_http_principal`, which accepts a local
principal when local authentication is disabled and requires an API key in
share mode. Alerts compose the same dependency with their router-specific
limiter; sessions and playback have no limiter policy yet.

The enforced `share-protected` set is limited to the operational routes shown
in the matrix. Framework documentation is `local-only`; detector catalog and
health-route policy remain separate decisions.

### Intentionally Public Surfaces

This change intentionally preserves `GET /health` as a minimal
`share-public` reachability response. It keeps `/detectors` outside the
operational-router authentication scope pending a separate policy decision.
Framework documentation endpoints are disabled in share mode and remain
available locally; a future remote API integration may add an explicit opt-in.

### Rate-Limit And Resource Controls

Only the alerts router currently invokes the limiter. When enabled, it uses a
local in-memory fixed window, shared across the four alert routes. The default
budget is 100 requests per 60 seconds, configurable through
`ESM_API_RATE_LIMIT_MAX_REQUESTS` and `ESM_API_RATE_LIMIT_WINDOW_SEC`.
The default identity is the authenticated API-key fingerprint; the optional
`ip` strategy instead uses the request host. When auth is disabled locally,
the principal strategy uses one shared local identity.

| Route family | Rate limit and identity today | Existing input or result control | Missing resource control to record |
| --- | --- | --- | --- |
| Framework docs, OpenAPI, health | None | Small static or constant responses | Framework docs are local-only; health remains a minimal public status route |
| Detector catalog | None | Optional `mode` is a fixed enum; catalog is registry-backed | No request budget if exposed remotely |
| Session start | None | `mode` is a fixed enum; source validation rejects blank, unsupported, missing, and disallowed remote sources | No request budget, body-size cap, or detector-count cap before a detached worker is started |
| Session read | None | Session identifier is the only route input | Snapshot may contain unbounded persisted alerts and results; no response cap or pagination |
| Session cancel | None | Session identifier is the only route input | No request budget for a state-changing control operation |
| Alert list, summary, timeline, incident summary | Shared fixed window: 100 requests / 60 seconds when enabled. `principal` uses an API-key fingerprint or the local principal; `ip` uses the request host. | `severity` is a fixed enum; time ranges are parsed and ordered; invalid values return validation errors | Raw lists and grouped timelines have no pagination or response-size cap; summaries still scan the selected session's alerts |
| Playback resolution | None | `mode` is a fixed enum; source and remote-host trust validation run before resolution | No request budget or body-size cap; resolution can inspect local media paths or validate remote stream URLs |

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

### Remaining Security Gaps And Decisions

This register compares current behavior with the intended access policy. Its
classifications set branch priority; they do not imply that every hosted-system
control belongs in this local-first project now.

| Surface or concern | Current behavior | Intended decision | Classification |
| --- | --- | --- | --- |
| Mode and bind address | Supported CLI enforces loopback-only `local` binds; `share` permits explicit network-visible binds with authentication | Keep non-loopback binding behind explicit `share` selection; keep raw Uvicorn documented as a development escape hatch | Implemented policy; raw-Uvicorn limitation remains |
| Session start, read, and cancel | API-key authentication applies in `share`; no rate or result-size policy applies yet | Preserve `share-protected`; apply proportionate limits to start and cancel, and bound large reads separately | Acceptable local-first limitation |
| Playback resolution | API-key authentication applies in `share`; no rate policy applies yet | Preserve `share-protected`; retain source and remote-host validation and add an applicable request budget | Acceptable local-first limitation |
| Alert and incident reads | API-key and fixed-window protection already apply in `share`; raw and timeline responses are unbounded | Preserve `share-protected`; add pagination or response bounds before broader remote use | Acceptable local-first limitation |
| Detector catalog | Unauthenticated in `share` mode | Treat detector metadata as `share-protected` for one consistent remote API boundary | Policy gap requiring a decision |
| `/docs`, `/redoc`, OAuth redirect, and `/openapi.json` | Available locally and return `404` in `share` mode | Keep framework discovery local-only; add remote opt-in only for a deliberate integration need | Implemented policy |
| `/health` | Returns a small unauthenticated response | Keep `share-public`, limited to minimal reachability/readiness status with no configuration, dependency, or secret detail | Policy gap requiring a decision |
| Share-mode authentication override | `ESM_API_AUTH_ENABLED=false` is rejected before startup; rate limiting remains independently configurable | Preserve mandatory share-mode authentication; decide later whether rate limiting also becomes mandatory | Implemented share-mode guarantee |
| HTTP limiter scope | In-memory and per process | Keep for the current single-process runtime; require shared enforcement only before multi-worker or distributed deployment | Later deployment concern |
| MCP tools | Four read-only alert tools run over trusted local `stdio`, without HTTP auth or HTTP rate limiting | Keep `MCP-local-read-only` and `disabled-remotely`; do not add a network transport in this branch | Acceptable local-first limitation |
| Future remote MCP | No network transport exists | Treat remote MCP as a new security boundary requiring separate authentication, authorization, request/result bounds, and error review | Later deployment concern |

The immediate implementation backlog is therefore bounded to minimal health
output and proportionate HTTP resource controls. Bind/mode enforcement and
framework-doc availability are implemented in the supported CLI/application
path.
Distributed throttling and remote MCP remain deployment-stage work rather than
defects in the current local transport model.

### Policy And Regression Ownership

This document owns the HTTP route, run-mode, and share-mode security policy,
including the enforced matrix and its open decisions. The MCP transport and
tool policy belongs in [mcp-server.md](./mcp-server.md#current-tool-inventory).
`contracts.md`, `architecture.md`, testing guidance, and the root README
should link here rather than repeat the matrix.

| Guarantee to protect after implementation | Regression-test owner |
| --- | --- |
| Host classification, loopback-only local mode, and safe share startup | `tests/test_api_bind_policy.py`, `tests/test_api_server_cli_runtime.py` |
| Share-mode admission, `401` envelopes, and intentional public-route classification | `tests/test_api_server_cli_routes.py` |
| Alert-specific auth logging and limiter ordering | `tests/test_api_alert_route_auth_policy.py` |
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
- route tests keep the public-surface split explicit: protected session,
  alert, and playback operations versus open `/health` and `/detectors`, with
  framework docs available locally but hidden in share mode
- representative session, alert, and playback routes prove the shared policy
  in both modes: local calls need no key, share calls without a key return
  `401`, and share calls with a generated or configured key reach normal route
  handling

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

The supported Electron and CLI paths now have focused startup-policy coverage.
Raw Uvicorn remains a documented backend-development escape hatch rather than
a network-sharing path.

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

If neither `--api-key` nor `ESM_API_AUTH_ALLOWED_KEYS` is set in `share` mode,
the CLI generates one API key and prints it once together with `X-API-Key`
usage guidance.

The backend still uses the current flat `src/` module layout, so
`PYTHONPATH=src` remains the intended raw-checkout startup path for this CLI.

The Electron desktop runtime can also start the local FastAPI process as part
of its owned startup/readiness flow. Running `uvicorn` manually is mainly
useful for backend-focused development and debugging.

[`src/session_cli.py`](../src/session_cli.py) also remains available for
tooling and debugging, but it is not a peer startup path to Electron. It is a
shared-service adapter for backend-focused workflows.

In local mode, open the interactive docs at:

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
