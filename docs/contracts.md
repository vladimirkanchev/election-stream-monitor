# Contracts

This document defines the current shared contracts between the Python backend,
the Electron bridge, and the frontend.

The project is still in an advanced prototype stage, so these contracts are
kept intentionally compact.

The goal is:

- make important interfaces explicit
- reduce accidental contract drift
- prepare later `api_stream` and service/API evolution

Use this doc for stable payload and seam contracts.
Do not use it as the main architecture narrative or as the detailed explanation
of persisted session files; see [architecture.md](./architecture.md) and
[session-model.md](./session-model.md) for those.

## At a glance

This is the document to use when you need to know:

- what the frontend is allowed to send
- what the backend promises to return
- which fields should be treated as stable by tests, tools, and UI code

For code-level truth, the closest sources are:

- [`src/source_validation.py`](../src/source_validation.py)
- [`src/stream_loader.py`](../src/stream_loader.py)
- [`src/stream_loader_contracts.py`](../src/stream_loader_contracts.py)
- [`src/stream_loader_http_hls.py`](../src/stream_loader_http_hls.py)
- [`frontend/src/bridge/contract.ts`](../frontend/src/bridge/contract.ts)
- [`frontend/src/bridge/contractErrors.ts`](../frontend/src/bridge/contractErrors.ts)
- [`frontend/src/bridge/contractDetectors.ts`](../frontend/src/bridge/contractDetectors.ts)
- [`frontend/src/bridge/contractSessionSnapshot.ts`](../frontend/src/bridge/contractSessionSnapshot.ts)
- [`frontend/src/bridge/transport.ts`](../frontend/src/bridge/transport.ts)
- [`frontend/src/types.ts`](../frontend/src/types.ts)

## Current Source Of Truth

For the current project stage:

- backend session snapshot source of truth:
  - [`src/session_io.py`](../src/session_io.py)
  - [`src/session_models.py`](../src/session_models.py)
  - [`src/session_runner.py`](../src/session_runner.py)
  - [`src/session_runner_progress.py`](../src/session_runner_progress.py)
- frontend bridge normalization source of truth:
  - [`frontend/src/bridge/contract.ts`](../frontend/src/bridge/contract.ts)
  - [`frontend/src/bridge/contractErrors.ts`](../frontend/src/bridge/contractErrors.ts)
  - [`frontend/src/bridge/contractDetectors.ts`](../frontend/src/bridge/contractDetectors.ts)
  - [`frontend/src/bridge/contractSessionSnapshot.ts`](../frontend/src/bridge/contractSessionSnapshot.ts)
  - [`frontend/src/bridge/contractShared.ts`](../frontend/src/bridge/contractShared.ts)
  - [`frontend/src/bridge/transport.ts`](../frontend/src/bridge/transport.ts)
  - [`frontend/src/types.ts`](../frontend/src/types.ts)
- FastAPI request/response contract source of truth:
  - [`src/api/schemas.py`](../src/api/schemas.py)
  - [`src/api/routers/`](../src/api/routers)

## Do Not Drift These Together By Accident

When changing one of these, review the others too:

- [`src/api/schemas.py`](../src/api/schemas.py)
- [`frontend/src/bridge/contract.ts`](../frontend/src/bridge/contract.ts)
- [`frontend/src/bridge/contractErrors.ts`](../frontend/src/bridge/contractErrors.ts)
- [`frontend/src/bridge/transport.ts`](../frontend/src/bridge/transport.ts)
- [`frontend/src/types.ts`](../frontend/src/types.ts)
- [`frontend/src/bridge/contract.testSupport.ts`](../frontend/src/bridge/contract.testSupport.ts)
- [`docs/session-model.md`](./session-model.md)
- [`tests/test_api_boundary_contracts.py`](../tests/test_api_boundary_contracts.py)
- [`tests/test_api_boundary_sessions_read.py`](../tests/test_api_boundary_sessions_read.py)
- [`tests/test_api_boundary_sessions_start.py`](../tests/test_api_boundary_sessions_start.py)
- [`tests/test_api_boundary_sessions_cancel.py`](../tests/test_api_boundary_sessions_cancel.py)
- [`frontend/src/bridge/contract.success.test.ts`](../frontend/src/bridge/contract.success.test.ts)
- [`frontend/src/bridge/contract.errors.test.ts`](../frontend/src/bridge/contract.errors.test.ts)
- [`frontend/src/bridge/contract.session-snapshot.shape.test.ts`](../frontend/src/bridge/contract.session-snapshot.shape.test.ts)
- [`frontend/src/bridge/contract.session-snapshot.malformed.test.ts`](../frontend/src/bridge/contract.session-snapshot.malformed.test.ts)
- [`frontend/src/bridge/contract.session-snapshot.collections.test.ts`](../frontend/src/bridge/contract.session-snapshot.collections.test.ts)
- [`frontend/src/bridge/transport.test.ts`](../frontend/src/bridge/transport.test.ts)
- [`frontend/src/hooks/useMonitoringSession.lifecycle.test.tsx`](../frontend/src/hooks/useMonitoringSession.lifecycle.test.tsx)
- [`frontend/src/hooks/useMonitoringSession.apiStream.test.tsx`](../frontend/src/hooks/useMonitoringSession.apiStream.test.tsx)
- [`frontend/src/hooks/usePlaybackSource.test.tsx`](../frontend/src/hooks/usePlaybackSource.test.tsx)
- [`frontend/src/components/SessionStatusPanel.test.tsx`](../frontend/src/components/SessionStatusPanel.test.tsx)
- [`frontend/src/presenters/alertFeed.test.ts`](../frontend/src/presenters/alertFeed.test.ts)
- [`frontend/src/uiErrors.test.ts`](../frontend/src/uiErrors.test.ts)

For `main` pull requests, the CI drift gate expects contract changes to move
with nearby tests and the owning docs update rather than landing as silent
shape changes.

## FastAPI Authentication Contract v1

Purpose:

- define the first authentication seam for the HTTP API
- keep request authentication explicit at the FastAPI boundary
- leave shared backend services auth-agnostic
- make a later move from API keys to JWT-backed principals easier

Current scope:

- this contract applies to the FastAPI HTTP API only
- the current stdio MCP server remains a local-trust transport and is not
  authenticated by this contract
- the current protected FastAPI scope is the alerts router:
  - `GET /sessions/{session_id}/alerts`
  - `GET /sessions/{session_id}/alerts/summary`
  - `GET /sessions/{session_id}/alerts/timeline`
  - `GET /sessions/{session_id}/alerts/incident-summary`
- other FastAPI routers are not yet protected by this contract

Current credential shape:

- clients send one API key in the `X-API-Key` request header
- missing or invalid credentials should be treated as authentication failures
- blank or whitespace-only `X-API-Key` values are treated as missing credentials
- when FastAPI auth is disabled in configuration, the alerts router currently
  accepts requests without credentials

Current authenticated caller shape:

```json
{
  "auth_type": "api_key",
  "subject": "api-key:<fingerprint>",
  "key_id": "<fingerprint>"
}
```

Notes:

- the authenticated caller object is intentionally auth-neutral
- API-key principals expose only a short fingerprint derived from the matched
  configured key rather than the raw API key itself
- later JWT support should populate the same principal concept with a different
  credential-validation path rather than changing shared service code
- business logic modules such as [`src/session_alerts.py`](../src/session_alerts.py)
  should not validate headers or inspect credentials directly

Current authentication failure shape:

```json
{
  "detail": "Authentication failed",
  "error_code": "authentication_failed",
  "status_reason": "authentication_failed",
  "status_detail": "Missing or invalid credentials."
}
```

Implementation note:

- the FastAPI auth seam lives in [`src/api_auth.py`](../src/api_auth.py)
- the alerts-router HTTP protection composition lives in
  [`src/api/alert_route_policy.py`](../src/api/alert_route_policy.py)
- auth settings are centralized in
  [`src/api_boundary_config.py`](../src/api_boundary_config.py) under a small
  auth-neutral settings object rather than being parsed inline in route code
- the FastAPI app now validates the current auth and rate-limit settings
  during startup so invalid enabled configuration fails before the first
  protected request
- when FastAPI auth is enabled in configuration, the auth seam validates the
  presented `X-API-Key` against configured allowed API keys and returns an
  authenticated principal rather than exposing the raw key downstream
- the current alerts router enforces that seam through a router dependency
  rather than FastAPI middleware

## FastAPI Rate Limiting Contract v1

Purpose:

- define the first rate-limiting seam for the HTTP API
- keep request throttling explicit at the FastAPI boundary
- reuse authenticated caller identity instead of raw API keys where possible
- make a later move from local in-memory counting to a shared backend store easier

Current scope:

- this contract applies to the FastAPI HTTP API only
- FastAPI run mode now selects the default protected-boundary posture:
  - `local` defaults auth and rate limiting off
  - `share` defaults auth and rate limiting on
- `share` mode can auto-generate one process-local API key at startup when no
  manual key is configured
- the current stdio MCP server remains outside this rate-limiting contract
- the current protected FastAPI scope matches the alerts router:
  - `GET /sessions/{session_id}/alerts`
  - `GET /sessions/{session_id}/alerts/summary`
  - `GET /sessions/{session_id}/alerts/timeline`
  - `GET /sessions/{session_id}/alerts/incident-summary`
- when FastAPI rate limiting is enabled in configuration, the alerts router
  enforces this contract through the same router boundary that already owns
  authentication

Current caller identity rule:

- when FastAPI auth is enabled, rate limiting should identify callers by the
  authenticated principal rather than the raw presented API key
- the current default strategy is principal-based and prefers
  `principal.key_id` as the stable caller identity
- when FastAPI auth is disabled, the limiter falls back to one deterministic
  local identity for the current process
- the alternate `ip` strategy is also supported and uses the request host
  rather than authenticated principal identity

Current limit model:

- one fixed-window limit model
- one maximum request count in one configured time window
- current settings live in
  [`src/api_boundary_config.py`](../src/api_boundary_config.py):
  - `enabled`
  - `strategy`
  - `window_seconds`
  - `max_requests`
- current default intended values are:
  - `strategy = "principal"`
  - `window_seconds = 60`
  - `max_requests = 100`

Current rate-limit failure shape:

```json
{
  "detail": "Rate limit exceeded",
  "error_code": "rate_limit_exceeded",
  "status_reason": "rate_limit_exceeded",
  "status_detail": "Too many requests for the configured window."
}
```

Notes:

- `429` responses also include a coarse `Retry-After` header based on the
  configured fixed-window size so clients can back off without parsing limiter
  internals
- the same structured `429` plus `Retry-After` contract is expected across the
  protected alerts route family, not only on the raw `/alerts` route
- the rate-limit subject is intentionally defined in auth-neutral terms so a
  later JWT-backed principal can reuse the same boundary contract
- the current limiter store is local, in-memory, and per-process
- that makes the current behavior a good fit for local development, demos, and
  single-process backend runs, but not a distributed or multi-worker contract
- the current FastAPI security and limiter seams are therefore safe to treat
  as local/demo readiness features, not as a production-distributed security
  model
- shared service modules such as
  [`src/session_alerts.py`](../src/session_alerts.py) and
  [`src/session_alert_incidents.py`](../src/session_alert_incidents.py) should
  remain unaware of request counting

Current readiness summary:

- safe current use:
  - local development
  - demos
  - single-process backend runs
- not yet ready as a distributed boundary:
  - multi-worker shared rate limiting
  - shared-store request budgets
  - remote MCP auth or limiter enforcement
  - broader production-distributed guarantees

Implementation note:

- the current limiter mechanics live in [`src/api_rate_limit.py`](../src/api_rate_limit.py)
- the alerts-router HTTP protection composition lives in
  [`src/api/alert_route_policy.py`](../src/api/alert_route_policy.py)
- structured run-mode, auth, and rate-limit settings live in
  [`src/api_boundary_config.py`](../src/api_boundary_config.py)
- compatibility re-exports still exist in [`src/config.py`](../src/config.py)
- the stable `429` error vocabulary lives in
  [`src/api/errors.py`](../src/api/errors.py) and
  [`src/api/schemas.py`](../src/api/schemas.py)
- the current alerts router enforces the limiter through a router dependency
  rather than pushing counting logic into route bodies or shared alert services
- invalid configured auth or limiter settings now fail during FastAPI startup
  rather than waiting for the first protected request
- unrelated public routes such as `/health`, `/docs`, and `/openapi.json`
  intentionally stay outside the alerts-router auth/rate-limit boundary

Future remote MCP note:

- the current FastAPI authentication and rate-limit contracts do not secure the
  current `stdio` MCP server
- if MCP later gains a remote transport, it should reuse the auth-neutral
  principal concept, the same general machine-readable error style, and
  possibly the limiter service concepts
- that future work should still be designed at the MCP transport boundary
  rather than assuming the current FastAPI dependency model already applies
- until then, keep the current `stdio` MCP server documented as a local-trust
  transport rather than a protected remote API surface

## API Stream Source Contract v1

Purpose:

- define the current accepted shape for live remote inputs
- keep validation, bridge payloads, playback resolution, and live loading in sync

Current source shape:

```json
{
  "kind": "api_stream",
  "path": "https://example.com/live/playlist.m3u8",
  "access": "api_stream"
}
```

Current rules:

- `path` must be a non-empty URL
- only `http` and `https` are accepted
- only direct `.m3u8` and `.mp4` paths are accepted
- credentials in URLs are rejected
- local/private-network targets are rejected by default in local mode
- optional allowlisting may narrow accepted hosts further
- webpage URLs such as video platform pages are rejected early

The backend is the source of truth for this validation.

Implementation note:

- [`src/stream_loader.py`](../src/stream_loader.py) remains the stable facade
  for the live-loader surface and the default loader-selection entry point
  while staying intentionally thin
- [`src/stream_loader_contracts.py`](../src/stream_loader_contracts.py) keeps
  the current `api_stream` source, start-session, and playback contract
  builders and the detailed contract helpers on one shared validation path so
  those three surfaces do not drift from each other
- [`src/stream_loader_http_hls.py`](../src/stream_loader_http_hls.py) owns the
  concrete HTTP/HLS transport behavior, including playlist parsing,
  reconnect handling, and temp-file materialization
- [`src/stream_loader_fakes.py`](../src/stream_loader_fakes.py) keeps the
  deterministic seam loaders used by tests and no-session contract-only paths
- when no `session_id` is present, the facade returns an empty deterministic
  seam loader rather than a separate placeholder class so test-time and
  contract-only call paths stay simpler

Trust-policy notes:

- local mode remains strict by default:
  - private and loopback hosts are rejected unless explicitly enabled
  - optional allowlists may narrow accepted public hosts further
- service mode is stricter:
  - an explicit host allowlist is required
  - private and loopback hosts remain rejected by default
  - only direct media manifests/files should be fetched remotely
  - webpage extraction, credentialed URLs, and arbitrary remote browsing are
    outside the allowed service-mode fetch boundary

This policy keeps future service deployments closer to a deliberate media-ingest
allowlist than to a general-purpose remote fetcher.

## API Stream Start-Session Contract v1

Purpose:

- define the current bridge payload shape for starting live sessions
- keep frontend request meaning stable while live loading evolves behind the seam

Current request shape:

```json
{
  "mode": "api_stream",
  "input_path": "https://example.com/live/playlist.m3u8",
  "selected_detectors": ["video_blur", "video_metrics"]
}
```

Current response shape from `start-session`:

```json
{
  "session_id": "session-20260405-abc123",
  "mode": "api_stream",
  "input_path": "https://example.com/live/playlist.m3u8",
  "selected_detectors": ["video_blur", "video_metrics"],
  "status": "pending"
}
```

Notes:

- this keeps live start-session semantics aligned with local modes
- remote URL validation happens before the detached session process is spawned
- runtime loader failures later surface through normal session status and
  snapshot reads, not through a separate live-only session model
- the same backend validation seam is reused for the playback-resolution
  contract, so live start and live playback stay aligned on allowed input URLs

## Why version them now

These contracts already exist in code and tests.

Naming them as `v1` does not mean they are frozen forever. It means changes to
them should be conscious rather than accidental.

## Detector Catalog v1

Purpose:

- describe detectors to the frontend
- drive detector selection UI
- communicate detector role and ownership

Current shape:

```json
{
  "id": "video_blur",
  "display_name": "Blur Check",
  "description": "Flags blurry video using rolling frame samples and normalized blur scoring.",
  "category": "quality",
  "origin": "built_in",
  "status": "optional",
  "default_rule_id": "video_blur.default_rule",
  "default_selected": false,
  "produces_alerts": true,
  "supported_modes": ["video_segments", "video_files", "api_stream"],
  "supported_suffixes": [".ts", ".mp4"]
}
```

Notes:

- `origin` describes ownership:
  - `built_in`
  - `user`
- `status` describes product role or maturity:
  - `core`
  - `optional`
  - `experimental`
- `default_rule_id` points to the bundled default alert policy for this detector
  when one exists

### Bundled default rule concept

The project keeps detector execution and alert policy as separate concepts.

At the same time, a detector can declare a `default_rule_id` so one installable
capability can still come with a sensible built-in rule.

This supports a future model where:

- a plugin may ship both a detector and a default rule
- the runtime still treats detectors and rules as separate contracts
- later project or user overrides can replace the bundled default rule without
  replacing the detector itself

## Session Snapshot v1

Purpose:

- give the frontend one read model for session state
- combine stable metadata, live progress, alerts, and results

Current shape:

```json
{
  "session": {
    "session_id": "session-20260402-abc123",
    "mode": "video_segments",
    "input_path": "/data/streams/segments",
    "selected_detectors": ["video_blur"],
    "status": "running"
  },
  "progress": {
    "session_id": "session-20260402-abc123",
    "status": "running",
    "processed_count": 12,
    "total_count": 42,
    "current_item": "segment_0012.ts",
    "latest_result_detector": "video_blur",
    "latest_result_detectors": ["video_metrics", "video_blur"],
    "alert_count": 2,
    "last_updated_utc": "2026-04-02 12:34:56"
  },
  "alerts": [],
  "results": [],
  "latest_result": null
}
```

Notes:

- `session` may be `null` before a session exists
- `progress` may be `null` before initialization or after lookup failure
- `alerts` and `results` are append-oriented event views
- playback state is not part of this contract
- `api_stream` sessions use the same snapshot contract as local modes

### Route failures vs session state

The current project intentionally uses two different failure channels:

- immediate request failure
  - returned as a structured API error payload
- ongoing or terminal session lifecycle state
  - returned through the session snapshot

Important snapshot progress fields are:

- `progress.status`
- `progress.status_reason`
- `progress.status_detail`

This keeps request-level problems distinct from the state of an already-running
session.

### Current monitoring lifecycle expectations

For the current branch state, frontend and bridge consumers should assume:

- `status` remains the top-level lifecycle outcome:
  - `pending`
  - `running`
  - `cancelling`
  - `completed`
  - `cancelled`
  - `failed`
- `status_reason` stays intentionally compact and stable
- `status_detail` carries the more specific loader/runtime explanation when one
  is needed

For `api_stream`, the currently important operator-facing distinctions are:

- transient polling/read failures may temporarily surface as reconnecting in
  the frontend without clearing the last good session snapshot
- reconnect-budget exhaustion is terminal and should be presented as a failed
  live run
- runtime safety limits are terminal and should be presented as a safety stop,
  not as a source-shape validation problem
- idle polling exhaustion persists as:
  - `status = completed`
  - `status_reason = idle_poll_budget_exhausted`
  - `status_detail = "Idle poll budget exhausted"`
- the frontend may still present that idle-completed case with warning-like
  wording so operators can distinguish it from an ordinary clean completion

The bridge/frontend layer should reflect these meanings, not invent a separate
degraded-state lifecycle model on its own.

### Current `api_stream` recovery and terminal expectations

For the current bridge/frontend contract:

- transient live polling failures may surface as reconnecting UI messaging
  while the frontend keeps the last good session snapshot
- terminal live failures still come through the ordinary session snapshot
  contract rather than a separate live-only failure channel
- failed live sessions intentionally keep a compact stable
  `progress.status_reason = "source_unreachable"` while the more specific
  runtime cause remains in `progress.status_detail`
- idle-bounded live completion now persists as:
  - `progress.status = "completed"`
  - `progress.status_reason = "idle_poll_budget_exhausted"`
  - `progress.status_detail = "Idle poll budget exhausted"`

Current frontend operator wording is expected to distinguish:

- reconnecting while recovery is still plausible
- retry-budget exhaustion as terminal
- runtime safety stop as terminal
- unsupported live source as validation/configuration issue
- completed live run with idle-budget warning as distinct from ordinary local
  success messaging

This keeps the frontend aligned with the compact backend contract: the UI may
be more explanatory, but it should not invent a separate live-only lifecycle
state model.

### Lifecycle edge contract notes

The current lifecycle hardening makes these edge rules explicit:

- terminal session reads remain successful snapshot reads
  - `completed`, `failed`, and `cancelled` states are returned through the
    normal session snapshot contract
- invalid lifecycle actions fail at the request boundary
  - for example, `cancel-session` against a terminal session returns a
    structured route failure rather than a synthetic success
- missing-session route failures stay distinct from snapshot normalization
  - backend persistence helpers may degrade missing files to a stable empty
    shape internally
  - API and bridge layers turn missing-session route lookups into structured
    failures such as `session_not_found`
- frontend bridge normalization preserves structured lifecycle failures
  - typed bridge errors keep `backend_error_code`, `status_reason`, and
    `status_detail` instead of flattening them into generic failures
- cancel success still allows `null`
  - a successful cancel request may return either an updated `SessionSummary`
    or `null` when no immediate summary payload is available

Frontend lifecycle behavior now also depends on two intentionally stable
consumer rules:

- polling reads are tolerant of transient failures and keep the last good
  session state in the UI instead of immediately clearing it
- duplicate in-flight cancel requests are suppressed so the frontend keeps one
  active stop request rather than fanning out repeated cancels
- once the UI has already settled into terminal `completed`, the app suppresses
  a late extra stop request instead of issuing a cancel action that can no
  longer change the session outcome

## Alert Event v1

Purpose:

- represent one alert raised by the backend
- support frontend list rendering and playback-aligned reveal

Current shape:

```json
{
  "session_id": "session-20260402-abc123",
  "timestamp_utc": "2026-04-02 12:35:02",
  "detector_id": "video_blur",
  "title": "Blur warning",
  "message": "segment_0206.ts entered a blurry state.",
  "severity": "warning",
  "source_name": "segment_0206.ts",
  "window_index": 206,
  "window_start_sec": 206.0
}
```

Notes:

- `timestamp_utc` is backend detection time, not playback display time
- `source_name` is the detector-side item identity
- `window_index` and `window_start_sec` are optional but important for temporal
  playback alignment

### Current built-in rule metadata preparation

The rule layer now also has lightweight internal metadata with stable ids such
as:

- `video_metrics.default_rule`
- `video_blur.default_rule`

Current rule metadata includes:

- `id`
- `detector_id`
- `display_name`
- `description`
- `origin`
- `status`

This is preparation for future user-extensible rule registration. It is not yet
a full rule-plugin loading system.

## Plugin Security Rules v1

Purpose:

- make future plugin loading safer before dynamic loading exists
- keep built-in and user-owned extension bundles distinct
- prevent silent detector or rule id takeover

Current intended manifest rules:

- every plugin manifest must declare:
  - `plugin_id`
  - `display_name`
  - `origin`
  - `detector_ids`
  - `rule_ids`
  - `enabled_by_default`
- `origin` must be explicit:
  - `built_in`
  - `user`
- detector ids and rule ids must be non-empty strings
- detector ids and rule ids must not contain duplicates within one manifest
- detector ids and rule ids must not conflict with existing built-in
  registrations
- user plugins are disabled by default until explicitly enabled by the runtime
  or operator

Why this matters now:

- manifest validation becomes a correctness and security boundary before plugin
  loading is introduced
- explicit ownership helps the runtime distinguish shipped capabilities from
  later user- or agent-authored extensions

## Notes For Agents

- If you change a bridge payload, update this file and the corresponding tests.
- If you change validation rules, update this file and
  [`src/source_validation.py`](../src/source_validation.py).
- If a field is described here as stable, do not silently rename or repurpose
  it inside frontend or backend code.
- duplicate-id rejection prevents silent override of built-in detectors or
  rules
- disabled-by-default user plugins keeps future extension trust explicit

## Playback Source Resolution v1

Purpose:

- define what the frontend can ask the bridge to resolve for playback
- keep playback-source behavior explicit across local and future remote sources

Request shape:

```json
{
  "source": {
    "kind": "video_segments",
    "path": "/data/streams/segments",
    "access": "local_path"
  },
  "currentItem": "segment_0012.ts"
}
```

Response shape:

```json
{
  "source": "local-media://media/repo/data/streams/segments/index.m3u8"
}
```

Current behavior:

- local files and playlists resolve to `local-media://...`
- already-remote sources may later resolve to direct `https://...`
- `currentItem` is optional context for playback resolution

### API Stream playback behavior

For `api_stream`, playback resolution currently returns the validated original
remote URL directly:

```json
{
  "source": "https://example.com/live/playlist.m3u8"
}
```

This keeps playback transport simple while live monitoring is still
file-backed-and-polled elsewhere.

Important architectural rule:

- playback resolution is intentionally separate from live monitoring ingestion
- the player only needs a playable source URL
- stream loading, reconnect behavior, and chunk iteration belong to the
  backend loader seam

Why this matters:

- playback can stay simple while monitoring evolves
- player issues do not need to share logic with loader retry/failure behavior
- `api_stream` can feel like a new source mode, not a second architecture

## API Stream Session Snapshot Semantics v1

Purpose:

- keep live-session reads compatible with the existing session snapshot model
- avoid introducing a second frontend state model for remote monitoring

Current snapshot semantics for `api_stream`:

- `session.mode` is `api_stream`
- `session.input_path` keeps the validated remote URL
- `progress.current_item` is the latest live slice/chunk identity
- `progress.processed_count` is the number of slices processed so far
- `progress.total_count` is the loader-provided bounded slice count in current
  tests and deterministic seam flows
- `alerts`, `results`, and `latest_result` keep the same meaning as local modes

Important current limitation:

- the project does not implement an open-ended live session model yet
- the current seam loaders and tests use bounded, deterministic slice sets so
  the existing snapshot contract stays stable

Open-ended live default for the upcoming real loader:

- while a live session is still `running`, `progress.total_count` means the
  latest known number of collected chunks so far
- `progress.total_count` stays a non-null integer in the current snapshot
  model
- before the first chunk arrives, `progress.total_count` may be `0`
- the frontend should treat `api_stream` progress as live activity, not as a
  stable completion percentage, until the session reaches a terminal status
- the current UI expectation is live wording such as "Live, N chunks
  analyzed", with optional debug-only "N analyzed, M discovered" detail rather
  than `N/M` batch-style progress

## API Stream Loader Seam v1

Purpose:

- define one backend component responsible for future live loading
- keep stream connection and chunk iteration separate from session orchestration

Current seam responsibilities:

- connect to one validated live source
- fetch and materialize chunk/segment work units
- yield normalized `AnalysisSlice` values
- close and release loader resources

Current non-responsibilities:

- session status transitions
- persistence
- detector execution
- alert rule evaluation

Why this separation matters:

- `session_runner` can stay focused on lifecycle and persistence
- `processor` can stay focused on running detectors and collecting alerts
- `alert_rules` can stay focused on policy, not transport behavior
- tests can use deterministic fake loaders today
- the first bounded HTTP/HLS loader now fits behind the same seam without
  changing detector or session snapshot contracts
- playback resolution can remain a simple remote-URL passthrough while the
  loader grows more sophisticated

## API Stream HTTP/HLS Loader Contract v1

Purpose:

- define the exact return shape expected from the first real remote loader
- keep future HTTP/HLS implementation work narrow, deterministic, and testable

Current decided contract:

- the loader returns normalized `AnalysisSlice` values only
- every yielded slice is backed by one session-scoped temp media file on disk
- the first real loader accepts:
  - direct media playlist URLs
  - master playlist URLs
- the default polling cadence is `API_STREAM_POLL_INTERVAL_SEC`

Current master-playlist policy:

- if the validated source resolves to a master playlist, the first version of
  the loader chooses the first listed variant
- it does not yet apply bandwidth, resolution, or codec heuristics

Why this matters:

- the first implementation stays deterministic and easy to test
- loader behavior becomes explicit before network code exists
- later improvements can change one named policy instead of silently changing
  runtime behavior

Current implementation note:

- the first concrete loader now supports bounded HTTP/HLS flows
- it fetches the initial playlist, resolves master playlists to the first
  listed variant, polls media playlists for new segments, downloads those
  segments to temp files, and yields normalized analysis slices
- master-playlist selection intentionally stays on the first listed variant
  even if later variants advertise higher bandwidth or resolution
  - this keeps first-run behavior deterministic on real feeds and avoids
    hidden quality-selection heuristics in v1
- open-ended live monitoring is still constrained by the current
  slice-collection session runner
- sliding playlist windows are allowed
  - older segments may disappear from later playlist refreshes without causing
    failures
  - replayed surviving segments are skipped by de-duplication
  - if the live window has advanced past some not-yet-seen segments, the
    loader resumes from the next visible segment instead of trying to recreate
    missing history
- target-duration drift is tolerated
  - the loader treats the configured poll interval as an upper bound
  - if the playlist later advertises a shorter target duration, the next poll
    uses that shorter cadence
- every playlist and segment fetch is bounded by `API_STREAM_FETCH_TIMEOUT_SEC`
  and `API_STREAM_MAX_FETCH_BYTES`
- session-scoped temp media is bounded by `API_STREAM_TEMP_MAX_BYTES`
  before a newly downloaded segment is written to disk

## API Stream Local HTTP Integration Harness v1

Purpose:

- define the smallest realistic integration-test shape for the future real
  HTTP/HLS loader
- keep real-loader tests local, deterministic, and controllable

Current planned harness:

- one small local HTTP test server
- serves HLS fixtures from the checked-in fixture tree
- entrypoint playlist is `index.m3u8`
- serves both:
  - playlist responses
  - segment responses

Current fixture-serving strategy:

- use checked-in HLS fixture folders as static source material
- serve one playlist and its referenced `.ts` files through local HTTP instead
  of direct filesystem loading
- keep fixture content deterministic so loader behavior, reconnect handling,
  and slice identity can be asserted cleanly

Current controllable failure plan:

- scripted timeout
- scripted disconnect
- scripted `503` response
- scripted playlist replay of already seen segments

Why this matters:

- the first real-loader integration tests can stay offline and reproducible
- failure/reconnect behavior can be exercised without unstable external
  dependencies
- the test harness mirrors real transport shape while keeping fixture control
  local

Current implementation note:

- the test suite now includes a small local HTTP harness for:
  - direct media playlists
  - master-playlist selection
  - low-quality but still playable first-variant selection
  - malformed master-playlist entries that still expose a later valid variant
  - playlist refresh with newly discovered segments
  - longer multi-refresh local HLS runs
  - temporary segment outage handling
  - retryable playlist failures and reconnect-budget exhaustion
  - duplicate segment replay during playlist refresh
  - sliding-window playlist histories
  - repeated refreshes with no new segments
  - target-duration drift
  - media playlists missing optional tags such as `#EXT-X-TARGETDURATION`

Frontend transport note for the current stage:

- the real loader does not require a transport upgrade to exist
- current frontend polling is still sufficient for bounded live-session
  snapshots
- SSE, WebSocket, or FastAPI-style transport upgrades are optional later
  improvements, not prerequisites for the first real loader

## API Stream Failure Semantics v1

Purpose:

- define the intended failure contract for future `api_stream` support before
  the runtime is implemented
- keep live-stream behavior explicit instead of letting retry/reconnect rules
  leak into unrelated layers

Current intended failure classes:

- `temporary failure`
  - one chunk/window cannot be fetched, decoded, or analyzed
  - the session remains `running`
  - no result or alert is emitted for that failed live slice
  - failure is logged with session and item context
- `retryable failure`
  - the upstream stream or playlist refresh fails in a way that may recover
  - the session remains `running` while reconnect attempts are still allowed
  - reconnect attempts should be bounded and visible in logs
- `terminal failure`
  - the source is invalid, permanently unavailable, or exceeds the reconnect
    budget
  - the session transitions to `failed`
  - final persisted progress must also be `failed`

Reconnect behavior:

- reconnect should only apply to `retryable failure`
- reconnect should use bounded retries with backoff
- reconnect should not duplicate already persisted results or alerts
- once reconnect succeeds, processing resumes from the next not-yet-persisted
  live slice/window
- once reconnect budget is exhausted, the failure becomes `terminal`

Current HLS parsing resilience:

- incomplete live refreshes such as a dangling `#EXTINF` without a following
  segment URI are tolerated and treated as "no new work yet"
- temporarily malformed live refreshes, such as a non-HLS body returned during
  a transient upstream glitch, are treated as retryable live noise instead of
  immediate terminal failure
- the first runtime also tolerates one common master-playlist quirk by
  resolving nested master playlists until it reaches a media playlist, up to a
  small bounded depth
- malformed numeric playlist tags such as invalid `MEDIA-SEQUENCE`,
  `TARGETDURATION`, or `EXTINF` values still fail clearly instead of being
  guessed

Live playlist idle behavior:

- for non-`#EXT-X-ENDLIST` playlists, "keep waiting" currently means:
  - continue polling while consecutive refreshes with no newly discovered
    segments stay below `API_STREAM_MAX_IDLE_PLAYLIST_POLLS`
  - stop the current bounded live run cleanly once that idle poll budget is
    exhausted
- `#EXT-X-ENDLIST` remains an explicit stop signal and completes the bounded
  live run immediately once the visible playlist segments are exhausted,
  without falling back to idle polling
- an explicit session cancel remains an immediate stop signal owned by the
  session runner; the runner stops after the in-flight chunk finishes and
  persists a `cancelled` snapshot
- the concrete HTTP/HLS loader also checks for cancel safely during:
  - idle polling waits
  - reconnect backoff waits
  - segment download/read loops
  - the gap between download completion and temp-file materialization
- this is intentionally a local-first bounded-live policy, not a claim of
  permanent endless monitoring yet

Current status expectations:

- `temporary failure`:
  - session status remains `running`
  - progress status remains `running`
- `retryable failure`:
  - session status remains `running`
  - progress status remains `running`
  - reconnect budget decreases
- `terminal failure`:
  - session status becomes `failed`
  - progress status becomes `failed`

Current reconnect budget:

- the runtime policy exposes `max_reconnect_attempts`
- this is the upper bound for retryable reconnect attempts before the runtime
  must treat the problem as terminal
- duplicate persisted results and duplicate alerts are not allowed after
  reconnect

What is intentionally not introduced yet:

- no extra frontend session status beyond the current `running` / `failed`
  model
- no SSE/WebSocket-specific semantics
- no plugin-specific retry policies

This contract is intentionally lightweight for the current stage, but it gives
`api_stream` a clear failure model before the implementation work begins.

## API Stream Reconnect De-Dup Policy v1

Purpose:

- define where replay protection lives before a real upstream reconnect loop
  exists
- prevent duplicate persisted results or alerts after chunk replay

Current decided policy:

- reconnect de-dup uses both loader/runtime memory and persisted session state
- replayed chunks are skipped before they reach persistence
- the reconnect-safe identity key remains:
  - `source_group`
  - `window_index`
  - `source_name`

Why this matters:

- the first implementation stays simple and local-first
- duplicate prevention is still explicit and testable
- later persistent de-dup can be added as an intentional upgrade instead of
  an accidental coupling to session storage

## API Stream Loader Exception Policy v1

Purpose:

- define exactly which live-loader failures the loader seam absorbs and which
  ones become session-fatal
- keep reconnect ownership explicit before the real HTTP/HLS loader exists

Current decided policy:

- the loader seam owns reconnect attempts
- the session runner does not implement its own reconnect loop for
  `api_stream`
- `temporary_failure` is skipped inside the loader seam and the session keeps
  running
- `retryable_failure` is handled inside the loader seam while reconnect budget
  remains
- `terminal_failure` escapes the loader seam and should fail the session
  immediately

Current runner behavior:

- if a terminal loader error happens before live slice discovery completes, the
  runner persists a failed session snapshot and re-raises the error
- if the loader seam skips temporary or retryable failures, the runner sees
  only valid `AnalysisSlice` values and keeps existing result/alert semantics

Current implementation note:

- the concrete HTTP/HLS loader retries playlist fetches internally using the
  configured reconnect budget and backoff
- accepted live-slice identity keys are persisted session-side so a replayed
  segment can be skipped even after reconnect or repeated loader startup
- if reconnect or playlist sliding means some missed segments are no longer in
  the playlist window, the loader resumes from the next visible segment and
  logs the gap instead of failing the whole run
- segment-download network failures are downgraded to per-segment temporary
  failures so one bad chunk can be skipped without failing the whole bounded
  run

Why this matters:

- reconnect logic stays in one place
- the runner keeps one clear responsibility: lifecycle and persistence
- failed live startup attempts become visible to the frontend as real failed
  sessions instead of disappearing before persistence

## API Stream Observability v1

Purpose:

- make live-ingestion decisions inspectable before full remote loading exists
- reduce silent failures during future retry/reconnect work

Current logging expectations at the loader seam:

- log when live-slice collection starts
- log selected master-playlist variant when one is chosen
- log accepted slices with:
  - `source_group`
  - `current_item`
  - `chunk_index`
- log playlist refresh stats with:
  - `playlist_refresh_count`
  - `new_segment_count`
  - `skipped_replay_count`
- log temporary failures with:
  - redacted source URL
  - current item when known
  - failure kind
- log retryable failures with:
  - reconnect attempt
  - reconnect budget
- log reconnect-budget exhaustion as an error
- log invalid/replayed/malformed slices that are skipped before persistence
- log live-window advancement when some missed segments are no longer visible
  after reconnect or playlist sliding

Why this matters:

- future `api_stream` problems will usually be ingestion and retry problems,
  not detector bugs
- these logs make it easier to debug live behavior without changing session
  snapshot semantics
- resume-gap logs make reconnect edge cases easier to understand when a real
  live playlist has already moved on

## API Stream Operator Messages v1

Purpose:

- define frontend-safe language for common live-stream failure states
- keep operator-facing messaging stable before richer live UI states exist

Current intended messages:

- `stream unavailable`
  - "The selected live stream is unavailable right now."
- `reconnecting`
  - "The live stream is temporarily unavailable. Monitoring is reconnecting."
- `reconnect budget exhausted`
  - "The live stream could not be reconnected. Monitoring stopped after the retry budget was exhausted."
- `unsupported source`
  - "The selected live stream source is not supported by the current monitoring runtime."

Notes:

- the current frontend maps these from bridge-safe error details
- this keeps the UI understandable without exposing low-level transport
  language directly to operators

## API Stream Temp-File Lifecycle v1

Purpose:

- define where fetched live chunks should live before HTTP/HLS downloading is
  implemented
- make cleanup, failure handling, and disk guardrails explicit

Current decided policy:

- downloaded chunks live under:
  - `API_STREAM_TEMP_ROOT / <session_id>`
- temp media is session-scoped so one live session can be cleaned up without
  touching another
- temp media is deleted on:
  - successful completion
  - explicit cancel
  - terminal failure
- the first implementation should respect a shared disk guardrail exposed as
  `API_STREAM_TEMP_MAX_BYTES`

Why this matters:

- temp media ownership is clear before the loader exists
- cleanup behavior does not have to be invented during failure handling
- disk usage gets one named guardrail early instead of growing accidentally

## API Stream Trust Policy v1

Purpose:

- define acceptable remote-source shapes before `api_stream` is implemented
- prevent local-first development from expanding into arbitrary remote or
  internal-network probing
- name the reconnect and fetch safety limits before transport code exists

Current allowlist rules:

- allowed URL schemes:
  - `https`
  - `http`
- URLs must include a host
- URLs must not include embedded credentials
- obvious local-network targets are rejected by default in local mode:
  - `localhost`
  - `localhost.localdomain`
  - literal loopback or private IP addresses

## API Stream Slice Identity Rules v1

Purpose:

- make live chunks addressable across progress updates, alerts, and reconnects
- prevent duplicate persistence after upstream replay or reconnect
- keep rolling rule state tied to one stable live source

Current rules:

- `source_group` must stay stable for the whole live source
  - today the default stable identity is the validated source URL
- `window_index` must be monotonic
  - each next live slice must have a strictly larger index than the previous one
- `current_item` must be readable and stable
  - if the upstream loader has no better name yet, a fallback such as
    `live-chunk-000007` is used
- persistence should treat the tuple below as the reconnect-safe identity key:
  - `source_group`
  - `window_index`
  - `source_name`

Why this matters:

- stable `source_group` keeps rolling detector/rule state attached to one live
  stream instead of leaking across sources
- monotonic chunk indexes make progress and replay handling predictable
- readable current-item names improve debugging and UI progress clarity
- a stable identity key is the foundation for "no duplicate results/alerts
  after reconnect"
- optional `API_STREAM_ALLOWED_HOSTS` can restrict allowed domains further

Current intended runtime limits:

- `API_STREAM_MAX_RECONNECT_ATTEMPTS`
  - maximum reconnect attempts before the failure becomes terminal
- `API_STREAM_RECONNECT_BACKOFF_SEC`
  - backoff between retryable reconnect attempts
- `API_STREAM_FETCH_TIMEOUT_SEC`
  - upper bound for one remote fetch or refresh operation
- `API_STREAM_MAX_FETCH_BYTES`
  - upper bound for one fetched playlist or media chunk payload
- `API_STREAM_TEMP_MAX_BYTES`
  - upper bound for temp media materialized by live loading

Implementation note:

- host validation intentionally does not perform DNS resolution during input
  validation
- this keeps validation deterministic and avoids turning validation itself into
  a network probe

## API Stream Flow Example v1

Purpose:

- show the intended end-to-end live flow without introducing a second
  monitoring architecture

Current planned flow:

1. frontend starts an `api_stream` session with a validated remote URL
2. session runner creates the session and initial pending progress
3. loader connects to the live source and yields normalized `AnalysisSlice`
   values
4. processor runs detectors on each slice
5. alert rules evaluate detector output
6. results, alerts, and progress are persisted in the same snapshot model as
   local sources
7. frontend polls the same session snapshot contract used by local modes

Why this matters:

- `api_stream` stays a new source mode, not a second architecture
- detectors, rules, persistence, and frontend snapshot reading keep the same
  meaning across local and remote inputs

## Electron Bridge Contract v1

Purpose:

- define the frontend-facing operations exposed through `window.electionBridge`
- keep Electron/CLI transport details separate from the meaning of the bridge API
- make later transport replacement easier without changing frontend behavior

Transport envelope shape:

```json
{
  "ok": true,
  "data": {}
}
```

or

```json
{
  "ok": false,
  "error": {
    "code": "SESSION_READ_FAILED",
    "message": "Session read request failed",
    "details": "No such session"
  }
}
```

Current bridge error codes:

- `DETECTOR_CATALOG_FAILED`
- `SESSION_START_FAILED`
- `SESSION_READ_FAILED`
- `SESSION_CANCEL_FAILED`
- `PLAYBACK_SOURCE_RESOLUTION_FAILED`
- `INVALID_BRIDGE_RESPONSE`

Current operations:

### `listDetectors`

Request:

```json
{
  "mode": "video_segments"
}
```

Response:

```json
[
  {
    "id": "video_blur",
    "display_name": "Blur Check",
    "description": "Flags blurry video using rolling frame samples and normalized blur scoring.",
    "category": "quality",
    "origin": "built_in",
    "status": "optional",
    "default_rule_id": "video_blur.default_rule",
    "default_selected": false,
    "produces_alerts": true,
    "supported_modes": ["video_segments", "video_files", "api_stream"],
    "supported_suffixes": [".ts", ".mp4"]
  }
]
```

Current bridge normalization:

- malformed detector entries are filtered out
- invalid detector lists normalize to `[]`
- explicit transport failures are raised as typed bridge errors

### `startSession`

Request:

```json
{
  "source": {
    "kind": "video_segments",
    "path": "/data/streams/segments",
    "access": "local_path"
  },
  "selectedDetectors": ["video_blur"]
}
```

Response:

```json
{
  "session_id": "session-20260402-abc123",
  "mode": "video_segments",
  "input_path": "/data/streams/segments",
  "selected_detectors": ["video_blur"],
  "status": "running"
}
```

Current bridge normalization:

- malformed responses are rejected as bridge errors
- hooks no longer validate `startSession` payloads themselves
- explicit transport failures are raised with `SESSION_START_FAILED`

### `readSession`

Request:

```json
{
  "sessionId": "session-20260402-abc123"
}
```

Response:

```json
{
  "session": {
    "session_id": "session-20260402-abc123",
    "mode": "video_segments",
    "input_path": "/data/streams/segments",
    "selected_detectors": ["video_blur"],
    "status": "running"
  },
  "progress": {
    "session_id": "session-20260402-abc123",
    "status": "running",
    "processed_count": 12,
    "total_count": 42,
    "current_item": "segment_0012.ts",
    "latest_result_detector": "video_blur",
    "latest_result_detectors": ["video_metrics", "video_blur"],
    "alert_count": 2,
    "last_updated_utc": "2026-04-02 12:34:56"
  },
  "alerts": [],
  "results": [],
  "latest_result": null
}
```

Current bridge normalization:

- invalid `session` or `progress` payloads become `null`
- missing or malformed `alerts` / `results` become `[]`
- malformed top-level payloads become the stable empty snapshot shape
- explicit transport failures are raised with `SESSION_READ_FAILED`

### Session Alert Query Surfaces

The backend now exposes a read-only, session-scoped alert query surface through
both FastAPI and MCP adapters over the same shared service seam.

Ownership split:

- `src/session_alerts.py`
  - read, filter, and summarize persisted alert events
- `src/api/routers/alerts.py`
  - HTTP binding and API error mapping
- `src/esm_mcp/`
  - MCP tool registration and MCP-facing error mapping

Current HTTP routes:

- `GET /sessions/{session_id}/alerts`
- `GET /sessions/{session_id}/alerts/summary`

Current MCP tools:

- `query_session_alerts`
- `summarize_session_alerts`

Shared filter inputs:

- `session_id`
- optional `detector_id`
- optional `severity`
- optional `start_time_utc`
- optional `end_time_utc`

Current shared-service validation expectations:

- missing sessions raise the shared not-found contract before filtering or
  summarization continues
- invalid `start_time_utc` or `end_time_utc` values raise field-specific
  validation errors
- unknown detector/severity filters degrade safely to empty query results
- time bounds are inclusive when provided

Current split test ownership:

- `tests/test_alert_query_service_read.py`
  - persisted alert-log reads, corrupt/unreadable input tolerance, and
    missing/orphaned session handling
- `tests/test_alert_query_service_filter.py`
  - raw filtered-row behavior, time-range validation, ordering, and safe empty
    results for unknown filters
- `tests/test_alert_query_service_summary.py`
  - numeric aggregation, timestamp-bound behavior, empty-summary behavior, and
    summary-specific validation
- `tests/test_mcp_server_alerts_behavior.py`
  - raw MCP no-alert behavior, filtered-data behavior, and stable empty results
    for known sessions whose filters match nothing
  - keeps raw payload-shaping expectations separate from MCP-facing error translation
- `tests/test_mcp_server_alerts_errors.py`
  - raw MCP-facing error mapping over the shared raw alert query seam
  - includes the expectation that raw MCP list and summary tools keep the same
    malformed-timestamp error contract
- `tests/mcp_fastapi_parity_test_support.py`
  - tiny shared setup and meaning-assertion helpers for the split FastAPI/MCP
    parity suites
  - intentionally limited to protected-route setup, file-backed parity
    fixture setup, and cross-surface meaning helpers
- `tests/test_mcp_fastapi_boundary_split.py`
  - FastAPI-versus-stdio MCP local-trust boundary behavior for the current
    project stage
  - includes the expectation that raw MCP list and summary tools stay outside
    direct FastAPI auth/rate-limit state together
  - keeps the current raw MCP boundary checks grouped together and the grouped
  MCP boundary checks grouped together so trust-boundary regressions are easy
    to localize
  - includes the expectation that grouped MCP tools remain outside the HTTP
    trust boundary even if both CLI `share` prep and direct FastAPI protection
    env are applied before the MCP read
- `tests/test_mcp_fastapi_parity_behavior.py`
  - one shared-fixture parity expectation for normal reads: protected FastAPI
    routes and local MCP tools should preserve equivalent raw alert totals and
    grouped incident totals for unfiltered, filtered, empty-session,
    unknown-filter no-match, and time-bounded reads
- `tests/test_mcp_fastapi_parity_edges.py`
  - one shared-fixture parity expectation for validation and ordering edges:
    protected FastAPI routes and local MCP tools should preserve equivalent
    invalid time-filter behavior, inverted-range behavior,
    inclusive/open-ended time-bound behavior, and deterministic
    same-timestamp grouped ordering
- `.github/ci_test_targets.json`
  - owner of the duplicated CI-critical explicit target groups for the current
    CI/CD hardening work
  - owner of the shared CI target groups consumed by workflows and by the
    manifest-backed part of the main PR policy
  - now also records the current path-owning CI consumers for the live
    path-existence self-check:
    workflow manifest groups, the one inline smoke path, policy manifest
    groups, and the policy-only test paths
  - the existence check boundary stays intentionally narrow:
    it validates CI-owned test paths, not source-path ownership or docs rules
- `.github/scripts/validate_ci_test_targets.py`
  - structural and boundary validation for the manifest owner
  - also protects the explicit path-existence inventory and scope boundary for
    the CI-owned test-path guard
- `.github/scripts/ci_target_manifest.py`
  - shared manifest model and loading seam for the reader, validator, drift
    check, and manifest-backed consistency policy
  - also owns the shared manifest-group access seam used by the consistency
    policy script
- `.github/scripts/read_ci_test_targets.py`
  - reader seam used by workflow shell consumers
- `.github/scripts/check_ci_target_drift.py`
  - final drift pass across workflow, policy, and doc consumers
  - verifies that the main PR consistency policy consumes the same stable
    manifest groups as the main workflow contract lane
  - protects the ownership split: manifest owns shared target groups, policy
    script owns narrower PR enforcement
  - reads one explicit protected-lane alignment model from
    `.github/scripts/ci_target_manifest.py`
- `.github/scripts/check_ci_test_paths_exist.py`
  - validates the current CI-owned test-path inventory from one place
  - covers manifest-backed workflow groups, inline workflow test exceptions,
    and policy-only test paths
  - reuses the shared manifest-loading seam instead of parsing manifest data
    ad hoc
  - keeps the `integration-smoke` inline exception explicit instead of letting
    it hide behind manifest-backed coverage
  - validates policy-only and local-only gate expectations against
    `check_main_pr_consistency.py`, which is their real owner
  - checks that the manifest policy-only inventory still matches that owner
  - now runs before broader drift and policy checks in the protected CI lanes
  - that protected-lane order currently covers `main-pr-consistency`,
    `test-and-build`, and `docs-consistency`
  - in those lanes, broader policy or contract work now starts only after the
    manifest, CI-owned path inventory, and drift alignment checks pass
  - the same manifest now also records the guarded split-suite registration
    surface for the live CI registration guard:
    backend contract/session-service areas, `api_stream` and HLS boundary
    suites, frontend bridge/hook contract suites, and local-only Electron
    policy suites
  - the registration rule stays narrow:
    shared-group additions update the manifest,
    policy-owned additions update `check_main_pr_consistency.py`,
    and docs update only when ownership meaning changes
  - the registration guard inspects changed files in protected PR
    CI instead of doing full historical repo inference or broad repo-wide
    policing
  - the shared registration-check command is:
    `.github/scripts/check_split_suite_registration.py <diff-range>`
  - most guarded areas accept `shared_manifest` or `policy_owned`
    registration, while the Electron local-only area requires
    `local_only_policy`
  - docs changes are required only when the ownership model changes, a new
    guarded category appears, or the policy-boundary meaning changes
  - when the guard fails:
    update `.github/ci_test_targets.json` for shared manifest ownership or
    `.github/scripts/check_main_pr_consistency.py` for policy ownership
  - use `docs/testing-and-validation.md` for the full guarded-area patterns,
    accepted registration surfaces, and the complete fix path
  - the guard reuses the current owner seams instead of re-parsing raw files:
    `shared_manifest_test_paths()` from
    `.github/scripts/ci_target_manifest.py`,
    plus `policy_owned_test_paths()` and
    `local_only_policy_test_paths()` from
    `.github/scripts/check_main_pr_consistency.py`
  - protected PR lanes now run that registration guard after drift alignment
    and before broader policy or contract work
  - intentionally does not replace:
    `validate_ci_test_targets.py` for manifest shape/scope or
    `check_ci_target_drift.py` for manifest-consumer alignment
- together, the three CI helper roles are:
  - manifest shape and scope
  - CI-owned test-path existence
  - manifest-consumer drift
- `tests/test_ci_test_target_scripts.py`
  - keeps the CI-owned test-path inventory seam, the current success-path
    existence guard, focused drift-check outcomes, and split-suite
    registration outcomes covered from normal project tests
- `.github/scripts/check_main_pr_consistency.py`
  - reuses manifest-backed groups where practical, while keeping a smaller
    policy-only layer for expectations that are narrower than the manifest
  - owns the narrower main-PR policy logic:
    gate activation rules, docs expectations, and policy-only test
    expectations
  - each gate now reads as:
    label, changed paths, manifest groups, policy-only tests, and docs
    expectations
  - the policy stays intentionally narrower than the workflow lanes it
    references, so it does not become a second target manifest
  - backend policy reads `backend_contract` and `mcp_fastapi_parity`
  - frontend bridge policy reads `frontend_contract`
  - shared `frontend_contract` ownership now covers the bridge, transport, and
    `uiErrors` contract suites, while the narrower hook monitoring/playback
    expectations stay policy-only
  - `tests/test_ci_test_target_scripts.py` regression-covers that split
  - electron trust/playback policy stays local-only for now
- the stable CI target-group language is now:
  `backend_contract`, `mcp_fastapi_parity`, `frontend_contract`,
  `weekly_slow_media`, `weekly_api_stream_deep`, and `weekly_lifecycle`
- the protected contract lane and the weekly heavy-validation lanes resolve
  those groups through the shared reader seam
- `integration-smoke` remains the intentional inline exception because it is a
  tiny local smoke path
- the `changes` job in `ci.yml` owns branch-level path-filter trigger scope
- current path-filter summary:
  `contract` covers the refined backend/frontend boundary files,
  `frontend` excludes the docs-only `frontend/README.md`, and downstream
  trigger intent in `ci.yml` now matches that split
- focused regression coverage for those high-signal `changes` assumptions
  lives in `tests/test_ci_test_target_scripts.py`
- keep the full path-filter contract, intent, and current review results in
  `docs/testing-and-validation.md`
- CI lane ownership now uses the canonical vocabulary
  `fast_synthetic`, `contract_boundary`, and `weekly_slow_real_media`
- `.github/ci_test_targets.json` owns that lane model, including the
  `group_lane_categories` mapping exposed through
  `.github/scripts/ci_target_manifest.py`
- `ci_target_manifest.py` is the Python access seam for lane-category lookup
  and lane-to-group queries
- `docs/testing-and-validation.md` is the primary explanation path for the
  full lane split and enforcement rules
- `tests/test_ci_test_target_scripts.py` provides the focused project-side
  coverage for the lane-helper seam, the current lane split, and split-suite
  registration owner-seam coverage
- the current lane owners are only: `backend-tests`, `test-and-build`,
  `integration-smoke`, `slow-e2e`, `api-stream-deep`, and `lifecycle-deep`
- lint, typecheck, security-audit, docs-consistency, and summary/filter jobs
  support those lanes but are not lane owners themselves
- the drift check treats the reader-backed `test-and-build` contract lane as
  the workflow alignment target for shared `ci.yml` groups
- the protected alignment contract is exposed through
  `.github/scripts/ci_target_manifest.py`, and policy-side group extraction
  comes from `manifest_policy_groups()` in
  `.github/scripts/check_main_pr_consistency.py`
- docs-side drift checking is now limited to high-signal ownership
  references instead of repeating every CI detail in every doc
- that means this doc keeps the contract-relevant ownership facts, not a full
  duplicate of every CI helper detail
- that equality rule is intentionally narrow:
  `backend_contract`, `mcp_fastapi_parity`, and `frontend_contract`
- weekly-only groups and the inline smoke path stay outside that equality
  contract on purpose
- that keeps the alignment guard focused on the shared contract lane instead
  of forcing unrelated workflow behavior into the same rule
- the `main-pr-consistency` contract gate now reuses the same stable manifest
  groups where practical, while keeping only a smaller gate-local set of extra
  policy expectations
- `validate_ci_test_targets.py` protects the manifest itself
- protected CI consistency lanes run manifest validation, CI-owned test-path
  existence, drift checking, then manifest-backed main PR gate policy
  validation
- `tests/test_mcp_server_incidents_behavior.py`
  - grouped MCP no-alert behavior, filtered-data behavior, and stable empty
    grouped results for known sessions whose filters match nothing
  - keeps grouped output-shaping expectations separate from grouped MCP-facing
    error translation
- `tests/test_mcp_server_incidents_errors.py`
  - grouped MCP-facing error mapping over the shared grouped incident seam
  - includes the expectation that grouped timeline and grouped summary tools
    keep the same invalid-range and malformed-timestamp error contracts

Current MCP tool expectations:

- the stdio MCP raw alert tools should expose the same empty and filtered-data
  contracts as the FastAPI raw alert routes
- for one shared persisted session fixture, the FastAPI and MCP alert-query
  surfaces should preserve equivalent raw alert counts, summary totals,
  grouped timeline entry counts, and grouped incident-summary totals even when
  the transport wrappers differ
- that parity expectation currently also applies to filtered queries, known
  empty sessions, unknown-filter no-match queries, one shared time-bounded
  query slice, invalid time-filter validation, inclusive/open-ended time
  bounds, and deterministic same-timestamp grouped ordering
- enabling FastAPI auth/rate limiting or preparing FastAPI `share` mode must
  not pull stdio MCP tools into the HTTP trust boundary

Current alert query response shape:

```json
{
  "session_id": "session-20260402-abc123",
  "alerts": [
    {
      "session_id": "session-20260402-abc123",
      "timestamp_utc": "2026-04-02 12:34:56",
      "detector_id": "video_blur",
      "title": "Blur increased",
      "message": "Blur threshold exceeded.",
      "severity": "warning",
      "source_name": "segment_0012.ts",
      "window_index": 12,
      "window_start_sec": 12.0
    }
  ]
}
```

Current alert summary response shape:

```json
{
  "session_id": "session-20260402-abc123",
  "total_alerts": 2,
  "counts_by_detector": {
    "video_blur": 2
  },
  "counts_by_severity": {
    "warning": 2
  },
  "first_alert_timestamp_utc": "2026-04-02 12:34:56",
  "last_alert_timestamp_utc": "2026-04-02 12:35:12"
}
```

Current query semantics:

- missing `session.json` means the session is treated as not found
- missing `alerts.jsonl` for a known session means `[]`
- malformed alert rows are ignored rather than failing the whole query
- time filters use the existing persisted UTC timestamp format

### Session Alert Timeline and Incident Summary v1

The incident-oriented alert surface is now live and stays structured first so
both FastAPI and MCP clients can consume it without parsing prose.

Recommended output split:

- timeline responses stay pure structured JSON
- incident summary responses stay structured JSON and may include one optional
  short `narrative_summary` field

This keeps the stable contract in the structured fields while still giving
operators and agent workflows one convenient short explanation.

Current HTTP routes:

- `GET /sessions/{session_id}/alerts/timeline`
- `GET /sessions/{session_id}/alerts/incident-summary`

Current MCP tools:

- `query_session_alert_timeline`
- `summarize_session_alert_incidents`

Shared filter inputs:

- `session_id`
- optional `detector_id`
- optional `severity`
- optional `start_time_utc`
- optional `end_time_utc`

Current timeline response shape:

```json
{
  "session_id": "session-20260506-abc123",
  "entries": [
    {
      "start_time_utc": "2026-05-06 10:00:00",
      "end_time_utc": "2026-05-06 10:00:45",
      "detector_id": "video_metrics",
      "severity": "warning",
      "title": "Black screen detected",
      "alert_count": 3,
      "source_names": ["segment_0001.ts", "segment_0002.ts"],
      "sample_message": "Black segment."
    }
  ]
}
```

Timeline notes:

- each entry is a grouped incident, not a raw alert row
- grouping should remain deterministic and session-scoped
- timeline ordering is chronological, with persisted row order acting as the
  stable tie-break when distinct incidents share the same timestamp
- grouped incidents should split whenever `detector_id`, `severity`, or
  `title` changes, even if adjacent timestamps would otherwise merge
- v1 grouping stays intentionally simple:
  - ordered alerts with a fixed gap threshold
  - matching `detector_id`, `severity`, and `title`
  - no coarse time buckets as the primary rule
  - no detector-specific or ML-style incident reconstruction yet
- `start_time_utc` and `end_time_utc` describe the grouped incident window
- `source_names` should preserve first-seen unique values inside one grouped
  incident
- `sample_message` is descriptive only and should not be treated as a stable
  identifier
- invalid timeline filter timestamps should fail before grouping begins
- inverted timeline ranges should fail before grouping begins
- unknown grouped timeline filters should degrade to an empty timeline rather
  than inventing grouped incidents
- grouped timeline filtering should reuse the raw alert-query filter semantics
  before incident grouping begins
- timeline grouping should remain stable when one or more persisted rows are
  malformed or unusable for grouping
- the grouped timeline MCP tool should expose the same empty and filtered-data
  contracts as the FastAPI grouped timeline route

Current incident summary response shape:

```json
{
  "session_id": "session-20260506-abc123",
  "total_alerts": 5,
  "total_incidents": 2,
  "counts_by_detector": {
    "video_metrics": 3,
    "video_blur": 2
  },
  "counts_by_severity": {
    "warning": 4,
    "info": 1
  },
  "top_incident_categories": {
    "Black screen detected": 1,
    "Blur increased": 1
  },
  "first_alert_timestamp_utc": "2026-05-06 10:00:00",
  "last_alert_timestamp_utc": "2026-05-06 10:02:10",
  "narrative_summary": "Session session-20260506-abc123 had 2 grouped incidents across 5 alerts, mostly from video_metrics, led by black screen detected."
}
```

Incident summary notes:

- structured fields remain the source of truth
- `top_incident_categories` counts grouped incidents by their stable `title`
  field rather than introducing a second incident taxonomy
- `narrative_summary` is a convenience field for operators and agents, not a
  wording-stable primary contract
- `narrative_summary` is optional convenience text for operators and agents
- grouped incident summaries preserve raw alert totals even when some rows
  cannot form incidents
- when grouped detector/category counts tie, the convenience narrative should
  still be deterministic even though clients must not depend on its wording
- clients must not depend on exact wording of `narrative_summary`
- this summary is incident-oriented and should stay distinct from the existing
  raw alert-count summary surface
- invalid summary filter timestamps should fail before grouping begins
- inverted summary filter ranges should fail before grouping begins
- unknown grouped-summary filters should degrade to the stable empty summary

### `cancelSession`

Request:

```json
{
  "sessionId": "session-20260402-abc123"
}
```

Response:

```json
{
  "session_id": "session-20260402-abc123",
  "mode": "video_segments",
  "input_path": "/data/streams/segments",
  "selected_detectors": ["video_blur"],
  "status": "cancelling"
}
```

Current bridge normalization:

- `null` remains a valid `cancelSession` result
- malformed non-null responses are rejected as bridge errors
- explicit transport failures are raised with `SESSION_CANCEL_FAILED`

### `resolvePlaybackSource`

Request:

```json
{
  "source": {
    "kind": "api_stream",
    "path": "https://example.com/live/playlist.m3u8",
    "access": "api_stream"
  },
  "currentItem": null
}
```

Response:

```json
"https://example.com/live/playlist.m3u8"
```

Current bridge normalization:

- non-string values normalize to `null`
- blank strings normalize to `null`
- non-empty strings are trimmed before reaching the hooks
- explicit transport failures are raised with `PLAYBACK_SOURCE_RESOLUTION_FAILED`

## Current contract boundaries

These contracts are currently enforced by a mix of:

- Python dataclasses and typed dicts
- TypeScript interfaces
- bridge wiring
- integration and App-level tests

They are not yet full API schemas, and that is acceptable at the current stage.

## Logging Redaction Policy v1

Purpose:

- keep structured logs useful for debugging
- avoid leaking full source locations or future payload metadata unnecessarily

Current redaction rules:

- full source URLs should not be logged in structured context
  - keep only scheme + host + optional port
- full local paths should not be logged in structured context
  - keep only the basename
- payload-like detector or rule objects should be redacted in structured
  context if they are logged in the future

Why this matters:

- reduces accidental leakage of signed URLs, private filesystem locations, or
  future detector payload metadata
- preserves the debugging value of session id, source kind, detector id, and
  current item

## Expected next evolution

Most likely next steps:

- add explicit `api_stream` contract cases
- document reconnect and failure-state semantics
- keep these same contracts when introducing a future HTTP/FastAPI layer

That way the transport can change later without redefining the meaning of the
data.
