# Contracts

This document defines the current shared contracts between the Python backend,
the Electron bridge, and the frontend.

The project is still in an advanced prototype stage, so these contracts are
kept intentionally compact.

The goal is:

- make important interfaces explicit
- reduce accidental contract drift
- prepare later `api_stream` and service/API evolution

Use this doc for stable payload and seam contracts. Do not use it as the main
architecture narrative, session-semantics guide, migration inventory, or
validation-command reference; see [architecture.md](./architecture.md),
[session-model.md](./session-model.md),
[session-persistence-audit.md](./session-persistence-audit.md), and
[testing-and-validation.md](./testing-and-validation.md).

## At a glance

Use this document when you need to know:

- what the frontend is allowed to send
- what the backend promises to return
- which fields should be treated as stable by tests, tools, and UI code

The closest code-level sources are:

- [`src/analyzer_contract.py`](../src/analyzer_contract.py)
- [`src/detectors/registry.py`](../src/detectors/registry.py)
- [`src/api/routers/detectors.py`](../src/api/routers/detectors.py)
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

- backend session snapshot contract:
  - [`src/session_store.py`](../src/session_store.py)
  - [`src/session_store_runtime.py`](../src/session_store_runtime.py)
  - [`src/session_service.py`](../src/session_service.py)
  - [`src/session_models.py`](../src/session_models.py)
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
- detector catalog and detector-result contract source of truth:
  - [`src/analyzer_contract.py`](../src/analyzer_contract.py)
  - [`src/detectors/registry.py`](../src/detectors/registry.py)
  - [`src/processor.py`](../src/processor.py)
  - [`src/alert_rules.py`](../src/alert_rules.py)
  - [`src/api/routers/detectors.py`](../src/api/routers/detectors.py)

Current persistence contract, kept short here:

- `SessionStore` owns the durable session read model used by the API, CLI,
  bridge, and tests.
- That durable contract includes:
  session metadata, latest progress, ordered detector results, snapshot reads,
  known-session checks, and cancel intent.
- The public snapshot shape stays:
  `session`, `progress`, `alerts`, `results`, and derived `latest_result`.
- A metadata-only snapshot is still valid:
  `session` may exist while `progress` is `null`.
- `progress` is latest-state only, not append-only progress history.
- `results` are append-ordered history, and `latest_result` comes from the
  final valid ordered row rather than detector timestamp sorting.
- Low-level cancel intent is part of the broader durable coordination
  contract, but it stays outside the public snapshot payload.
- File-backed session storage is still the runtime default.
- Unsupported backend values still normalize to the file-backed default.
- PostgreSQL session storage turns on only when
  `ESM_SESSION_STORE_BACKEND=postgres` is explicitly selected and valid
  PostgreSQL bootstrap settings are present.
- Alert persistence has its own stable backend contract:
  file-backed storage remains the default, and
  `ESM_ALERT_STORE_BACKEND=postgres` explicitly selects PostgreSQL.
- PostgreSQL alert storage is forward-only: it stores newly produced alerts
  after explicit selection and does not automatically backfill historical
  `alerts.jsonl` data.
- Alert reads use the selected backend only. There is no automatic dual-read
  or cross-store history merge; raw, summary, incident, and snapshot readers
  must agree on the normalized alerts from that selected backend.
- An explicit PostgreSQL alert selection that cannot be built fails clearly;
  it never silently changes the active alert store back to file mode.
- Runtime reads and cancel requests follow the active backend selection too.
  Explicit PostgreSQL mode is intentionally single-backend:
  older file-backed sessions stay outside that backend's known-session
  universe unless a later backfill or deliberate dual-read policy is added.
  Parent reads, cancel checks, and session-exists lookups do not silently fall
  back to file-backed session directories.
- Missing or invalid PostgreSQL configuration should fail clearly only after
  explicit selection; it should not poison the file-backed default.
- The detached worker and the parent process must resolve the same session
  store backend.
- Alerts, replay keys, worker logs, temp media, and other runtime artifacts
  remain separate seams rather than part of the durable session snapshot.
- Alert stores may ask the active `SessionStore` whether durable session
  metadata exists for a session. They should not read backend-specific storage
  details directly.
- Rollout readiness, default-switch blockers, forward-only/backfill policy,
  failure and rollback behavior, and PostgreSQL bootstrap or migration detail
  are owned by the [persistence readiness scorecard](./session-persistence-audit.md#current-persistence-readiness-scorecard).
  For field meaning and lifecycle semantics, use
  [session-model.md](./session-model.md).

## Do Not Drift These Together By Accident

When changing one of these, review the others too:

- [`src/analyzer_contract.py`](../src/analyzer_contract.py)
- [`src/detectors/registry.py`](../src/detectors/registry.py)
- [`src/processor.py`](../src/processor.py)
- [`src/alert_rules.py`](../src/alert_rules.py)
- [`src/api/routers/detectors.py`](../src/api/routers/detectors.py)
- [`src/api/schemas.py`](../src/api/schemas.py)
- [`frontend/src/bridge/contract.ts`](../frontend/src/bridge/contract.ts)
- [`frontend/src/bridge/contractErrors.ts`](../frontend/src/bridge/contractErrors.ts)
- [`frontend/src/bridge/transport.ts`](../frontend/src/bridge/transport.ts)
- [`frontend/src/types.ts`](../frontend/src/types.ts)
- [`frontend/src/bridge/contract.testSupport.ts`](../frontend/src/bridge/contract.testSupport.ts)
- [`docs/session-model.md`](./session-model.md)
- [`tests/test_api_boundary_contracts.py`](../tests/test_api_boundary_contracts.py)
- [`tests/test_analyzer_registry.py`](../tests/test_analyzer_registry.py)
- [`tests/test_processor.py`](../tests/test_processor.py)
- [`tests/test_alert_rules.py`](../tests/test_alert_rules.py)
- [`tests/test_session_cli_tooling.py`](../tests/test_session_cli_tooling.py)
- [`tests/test_export_detector_catalog.py`](../tests/test_export_detector_catalog.py)
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
- this section describes enforced behavior today; the full current-versus-
  intended share-mode policy is owned by
  [fastapi-boundary.md](./fastapi-boundary.md#http-route-security-matrix)
- the current stdio MCP server remains a local-trust transport and is not
  authenticated by this contract
- API-key authentication protects the operational routes marked enforced in
  the [FastAPI route matrix](./fastapi-boundary.md#http-route-security-matrix)
- alert reads, session control, and playback resolution use separate
  route-family budgets

Current credential shape:

- clients send one API key in the `X-API-Key` request header
- missing or invalid credentials should be treated as authentication failures
- blank or whitespace-only `X-API-Key` values are treated as missing credentials
- when FastAPI auth is disabled in local configuration, protected router
  dependencies accept a local principal without a credential

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
- [`src/api/http_auth_policy.py`](../src/api/http_auth_policy.py) owns HTTP
  header extraction, route-path plus fixed-reason-code failure logging, and
  `401` mapping; it never logs the presented or configured key
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
- session and playback route policies compose shared authentication with their
  own budgets; alerts do the same without app-wide middleware

## FastAPI Rate Limiting Contract v1

This contract applies only to FastAPI HTTP. `local` mode leaves authentication
and route-family budgets off by default; `share` enables both. The current MCP
server is a separate local `stdio` boundary and does not inherit HTTP controls.

The default limiter identifies an authenticated caller by a safe API-key
fingerprint. With local authentication disabled it uses one deterministic local
identity; the optional `ip` strategy uses the request host. The exact protected
route set, budgets, input/output limits, and deferred safeguards are owned by
the [FastAPI route matrix and resource-control contract](./fastapi-boundary.md#rate-limit-and-resource-controls).

Current rate-limit failure shape:

```json
{
  "detail": "Rate limit exceeded",
  "error_code": "rate_limit_exceeded",
  "status_reason": "rate_limit_exceeded",
  "status_detail": "Too many requests for the configured window."
}
```

Every implemented family returns this `429` envelope plus a coarse
`Retry-After` header. Shared services remain unaware of request counting.
The limiter is local, in-memory, and per process: suitable for the current
desktop-backed and demo runtime, but not a multi-worker or distributed-security
guarantee. A remote MCP transport requires its own authentication, bounds, and
rate-limit design.

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

Implementation note:

- detector catalog entries are declared explicitly in
  [`src/detectors/registry.py`](../src/detectors/registry.py)
- the shared detector/result types live in
  [`src/analyzer_contract.py`](../src/analyzer_contract.py)
- FastAPI exposes the catalog through
  [`src/api/routers/detectors.py`](../src/api/routers/detectors.py)
- CLI and export surfaces should stay aligned with the same registry-owned
  shape rather than defining parallel detector metadata contracts

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
- `progress` is a latest-only read model, not a progress-history stream
- `alerts` and `results` are append-oriented event views
- `alerts` represents the backend-raised alert history for the session
- frontend playback-aware filtering is a presentation concern and must not
  change the persisted snapshot alert list
- playback state is not part of this contract
- `api_stream` sessions use the same snapshot contract as local modes
- timestamp formatting may vary slightly across producers, but the field stays
  a string and must not change the rest of the progress shape

### Stable backend promise

The storage backend may change, but the public session snapshot should keep
the same outer shape and lifecycle meaning unless the project deliberately
versions the contract.

For the current migration stage, snapshot parity is the promise. That means
file-backed and PostgreSQL-backed session storage must produce the same
frontend-facing snapshot shape and field relationships for the same durable
session state. It does not mean the wider session-storage migration is
finished or that every backend-owned runtime artifact has moved behind the
same store.

Outer keys are stable:

- `session`
- `progress`
- `alerts`
- `results`
- `latest_result`

Null-vs-empty behavior is stable:

- `session` is `null` only when durable session metadata is missing or cannot
  be returned as a valid session payload
- `progress` is `null` when no valid latest-progress payload is currently
  available
- `alerts` is always a list and falls back to `[]`
- `results` is always a list and falls back to `[]`
- `latest_result` is either the final valid ordered result row or `null`

Field relationship rules are stable:

- `results` is append-ordered history, not timestamp-sorted history
- `latest_result` is derived from the final valid row in `results`
- `progress` is latest-only state, not progress history
- snapshot `alerts` follow the active alert-read backend, but they still keep
  the same public snapshot field
- tolerant degraded reads may drop malformed `progress` or malformed result
  rows, but they must still preserve the same outer snapshot shape and keep
  `latest_result` aligned with the final valid ordered result row

### State-specific snapshot promise

| Session state | Backend promise |
| --- | --- |
| Missing session | Route/service layers treat it as missing-session behavior. At the low-level store/helper layer, the stable empty snapshot shape remains: `session = null`, `progress = null`, `alerts = []`, `results = []`, `latest_result = null`. |
| Running session | `session` is present, `progress` should usually be present, `results` keeps all committed ordered rows so far, `latest_result` matches the last committed result or `null`, and `alerts` is the alert history currently visible through the active alert backend. |
| Completed session | The snapshot remains readable after work stops. `session.status` and usually `progress.status` are `completed`; ordered `results`, derived `latest_result`, and `alerts` remain available for later reads. |
| Failed session | The snapshot remains readable after failure. `session.status` and usually `progress.status` are `failed`; `progress.status_reason` stays compact, `progress.status_detail` may carry the more specific cause, and committed `results` / `alerts` remain readable. |
| Cancelled session | The snapshot remains readable after terminal cancellation. `session.status` and usually `progress.status` are `cancelled`; `progress.status_reason` may explain the terminal settlement, and committed `results` / `alerts` remain readable. |
| Partially populated session | This is valid during startup, recovery, or tolerant degraded reads. `session` may be present while `progress` is `null`; `alerts` and `results` still stay list-shaped; `latest_result` stays aligned with committed ordered `results`, not inferred from progress fields. |

Practical read-model notes:

- repeated missing-session reads should still produce the same empty snapshot
  shape
- tolerant degraded reads may drop malformed progress or result rows, but they
  should keep `alerts` and `results` list-shaped and `latest_result` aligned
  with the final valid result row

Storage-backend freedom is still intentionally preserved:

- the contract does not freeze file names, table names, SQL layout, or worker
  implementation details
- it does freeze the public payload shape, list/null behavior, lifecycle
  meaning, result ordering, and `latest_result` derivation

### Compact snapshot examples

These examples are intentionally small. They are meant to catch contract drift
in the public payload shape, not to mirror every detector or backend detail.

Missing session:

```json
{
  "session": null,
  "progress": null,
  "alerts": [],
  "results": [],
  "latest_result": null
}
```

Running session:

```json
{
  "session": {
    "session_id": "session-running-1",
    "mode": "video_files",
    "input_path": "/tmp/input.mp4",
    "selected_detectors": ["video_metrics"],
    "status": "running"
  },
  "progress": {
    "session_id": "session-running-1",
    "status": "running",
    "processed_count": 2,
    "total_count": 10,
    "current_item": "clip.mp4 @ 00:02",
    "latest_result_detector": "video_metrics",
    "latest_result_detectors": ["video_metrics"],
    "alert_count": 0,
    "last_updated_utc": "2026-07-02 10:00:00",
    "status_reason": "running",
    "status_detail": null
  },
  "alerts": [],
  "results": [],
  "latest_result": null
}
```

Completed session:

```json
{
  "session": {
    "session_id": "session-completed-1",
    "mode": "video_segments",
    "input_path": "/data/segments",
    "selected_detectors": ["video_metrics"],
    "status": "completed"
  },
  "progress": {
    "session_id": "session-completed-1",
    "status": "completed",
    "processed_count": 4,
    "total_count": 4,
    "current_item": null,
    "latest_result_detector": "video_metrics",
    "latest_result_detectors": ["video_metrics"],
    "alert_count": 1,
    "last_updated_utc": "2026-07-02 10:05:00",
    "status_reason": "completed",
    "status_detail": null
  },
  "alerts": [
    {
      "session_id": "session-completed-1",
      "timestamp_utc": "2026-07-02 10:04:59",
      "detector_id": "video_metrics",
      "title": "Black screen detected",
      "message": "Black segment exceeded threshold.",
      "severity": "warning",
      "source_name": "segment_004.ts"
    }
  ],
  "results": [
    {
      "session_id": "session-completed-1",
      "detector_id": "video_metrics",
      "payload": {
        "source_name": "segment_004.ts",
        "window_index": 3
      }
    }
  ],
  "latest_result": {
    "session_id": "session-completed-1",
    "detector_id": "video_metrics",
    "payload": {
      "source_name": "segment_004.ts",
      "window_index": 3
    }
  }
}
```

Failed session:

```json
{
  "session": {
    "session_id": "session-failed-1",
    "mode": "api_stream",
    "input_path": "https://example.test/live.m3u8",
    "selected_detectors": ["video_metrics"],
    "status": "failed"
  },
  "progress": {
    "session_id": "session-failed-1",
    "status": "failed",
    "processed_count": 3,
    "total_count": 3,
    "current_item": null,
    "latest_result_detector": "video_metrics",
    "latest_result_detectors": ["video_metrics"],
    "alert_count": 0,
    "last_updated_utc": "2026-07-02 10:08:00",
    "status_reason": "source_unreachable",
    "status_detail": "Retry budget exhausted while refreshing playlist."
  },
  "alerts": [],
  "results": [],
  "latest_result": null
}
```

Cancelled session:

```json
{
  "session": {
    "session_id": "session-cancelled-1",
    "mode": "video_files",
    "input_path": "/tmp/input.mp4",
    "selected_detectors": ["video_metrics"],
    "status": "cancelled"
  },
  "progress": {
    "session_id": "session-cancelled-1",
    "status": "cancelled",
    "processed_count": 1,
    "total_count": 10,
    "current_item": null,
    "latest_result_detector": "video_metrics",
    "latest_result_detectors": ["video_metrics"],
    "alert_count": 0,
    "last_updated_utc": "2026-07-02 10:09:00",
    "status_reason": "cancel_requested",
    "status_detail": null
  },
  "alerts": [],
  "results": [],
  "latest_result": null
}
```

Partially populated session:

```json
{
  "session": {
    "session_id": "session-partial-1",
    "mode": "video_files",
    "input_path": "/tmp/input.mp4",
    "selected_detectors": ["video_metrics"],
    "status": "pending"
  },
  "progress": null,
  "alerts": [],
  "results": [],
  "latest_result": null
}
```

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

### Cancellation Contract v1

Purpose:

- define cancellation as cooperative runtime control, not durable session
  history
- keep public cancel behavior stable while the storage backend evolves
- make later PostgreSQL-backed cancellation possible without forcing the worker
  into heavy database chatter

Current semantics are intentionally split between the public request boundary
and the low-level runtime-control helper:

- public cancel request
  - `cancel-session` for a known non-terminal session is accepted
  - the immediate response is a transient `cancelling` summary or `null`
  - the public request path rejects missing sessions and already-terminal
    sessions as structured failures
- low-level cancel intent write
  - the helper records stop intent only
  - it is idempotent for repeated requests on the same session
  - it does not own lifecycle validation or missing-session errors
- low-level cancel intent read
  - readers need only a boolean answer: cancel requested or not
  - no marker or no known runtime-control row reads as `false`
  - worker and loader polling should not need to parse full session snapshots
- clear/reset behavior
  - there is no ordinary public "uncancel" operation
  - for one session run, cancel intent is write-once and remains set until the
    worker settles the session
  - reset belongs to test cleanup, fixture setup, or a fresh session id, not to
    the normal runtime control flow

Current design rule:

- keep durable terminal truth in session metadata/progress
- keep cancel-request state on the same small `SessionStore` contract as runtime control,
  while leaving it outside the durable snapshot read model
- route cancel writes and reads through `SessionStore.request_cancel(...)` and
  `SessionStore.is_cancel_requested(...)`
- keep the file-backed store as the active default until PostgreSQL is
  explicitly selected
- treat cancel intent as bounded durable coordination
  - durable enough to survive the parent process, detached worker, and short
    runtime gaps
  - not durable session history and not part of the public snapshot payload
- in file mode, preserve the existing `cancel_requested.json` marker shape
  behind `SessionStore`
- in PostgreSQL mode, preserve the same semantics with one lightweight
  current-state record rather than append-only cancel history
- if a backend-specific reset helper is ever added, keep it test/bootstrap
  scoped and out of the public API contract

Current coverage emphasis:

- `tests/test_session_store_contract.py`, `tests/test_session_store_file.py`,
  `tests/test_session_store_postgres.py`, and
  `tests/test_session_store_parity.py` protect backend-level cancel semantics
  plus metadata-only snapshots, latest-only progress, append-ordered results,
  and storage-neutral snapshot parity
- `tests/test_session_service.py` and
  `tests/test_session_service_read_cancel.py` protect shared-service allow,
  reject, and transient-summary behavior
- `tests/test_api_boundary_sessions_cancel.py`,
  `tests/test_session_runner_execution*.py`, and
  `tests/test_stream_loader_http_hls*.py` protect route mapping, worker
  settlement, and live-loader polling behavior

## Result Event v1

Purpose:

- represent one durable detector output row for a session
- preserve append order for snapshot reads and `latest_result`
- keep detector-specific metrics flexible without changing the outer row shape

Current durable row shape:

```json
{
  "session_id": "session-20260402-abc123",
  "detector_id": "video_blur",
  "payload": {
    "timestamp_utc": "2026-04-02 12:35:02",
    "source_name": "segment_0206.ts",
    "window_index": 206,
    "window_start_sec": 206.0,
    "blur_score": 0.91,
    "blur_detected": true
  }
}
```

Notes:

- the outer durable contract is intentionally small:
  - `session_id`
  - `detector_id`
  - raw `payload` JSON
- append order is a store contract, not a public payload field:
  - file mode uses JSONL append order
  - PostgreSQL mode must use a monotonic row/sequence order
- equal or out-of-order `timestamp_utc` values must not reorder durable result
  history; timestamps are detector hints, not the storage tie-breaker
- `latest_result` is derived from the final valid ordered row rather than
  persisted separately
- shared timing/source hints may appear inside `payload` when they are useful:
  - `timestamp_utc`
  - `detector_name`
  - `source_name`
  - `window_index`
  - `window_start_sec`
- when these shared hints are present, they should keep simple scalar types so
  file-backed and PostgreSQL-backed validation stays aligned
- alert-like context may also appear inside `payload` when a detector exposes
  it for later rule/debug interpretation:
  - `title`
  - `message`
  - `severity`
- detector display naming is not required as a separate durable top-level
  field; the stable durable identity is `detector_id`
- detector-specific metrics stay inside `payload` so the contract does not need
  a schema change every time a detector gains a new measurement
- the PostgreSQL storage row may project a few nullable query fields for
  durability and future filtering:
  - monotonic `id` as the append-order key
  - `detector_name`
  - `event_timestamp_utc`
  - `payload_json` for the raw detector payload
- that projection is a storage detail, not a wider public payload contract:
  reads still return the compact `session_id` / `detector_id` / `payload`
  shape above
- current behavior:
  - result append/read and snapshot assembly are now store-backed
  - the file-backed default remains the runtime default
  - broader session persistence migration is still in progress

This keeps the row stable for storage and parity testing without freezing the
internal detector payload catalog too early.

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
- `counts_by_detector` and alert rows keep stable detector ids such as
  `video_blur`; user-facing relabeling belongs in presentation layers, not in
  the API contract

Current `video_blur` detector-output semantics:

- persisted blur rows may include `sample_count`, `sharpness_p10`,
  `sharpness_p90`, `motion_mean`, `motion_p90`, `blur_score`,
  `blur_detected`, and `threshold_used`
- `sample_count` may be `0` when extraction fails cleanly or when all sampled
  frames are excluded as effectively black
- `threshold_used` is the configured detector threshold captured at analysis
  time so later readers do not need to guess which calibration produced the row
- `motion_mean` and `motion_p90` are detector-side motion summaries for the
  analyzed clip; they exist so the default blur rule can suppress
  moving-camera softness without rewriting the persisted blur score
- short local one-second windows may be sampled above the baseline blur fps so
  these motion summaries still carry useful information in `video_files` mode
- black or near-black sampled frames are excluded from blur scoring so
  black-screen failures do not inflate blur metrics for the wrong reason
- bounded aspect-preserving sampling is an implementation detail, but the
  resulting payload shape stays stable across local files and segment-style
  analysis

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

Current built-in rule behavior notes:

- `video_metrics.default_rule`
  - enters on either long continuous black intervals or a full rolling window
    with a high weighted black ratio
  - suppresses duplicate alerts until rolling recovery is observed
- `video_blur.default_rule`
  - requires a full rolling window plus a minimum total sample warm-up
  - uses detector-side motion summaries to treat moderate motion as ambiguous
    and high motion as suppressive
  - keeps recovery and re-entry policy in the rule layer rather than mutating
    detector output

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
- repeated negative cancel checks inside the live HTTP/HLS hot path are
  throttled by `API_STREAM_CANCEL_CHECK_SKIP_COUNT`, while reconnect/sleep
  boundaries still force a fresh cancel read

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
the current `api_stream` runtime a clear failure model without expanding the
transport surface too early.

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
- an upstream HTTP 404 during playlist refresh is currently treated as
  reconnect-eligible rather than as an immediate terminal stop
- when a later playlist refresh succeeds, the loader clears any stale terminal
  failure reason instead of carrying the old 404 into later healthy snapshots
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

- define acceptable remote-source shapes for the current `api_stream` runtime
- prevent local-first development from expanding into arbitrary remote or
  internal-network probing
- keep reconnect and fetch safety limits explicit at the transport boundary

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

This normalization is intentionally compatible with the backend snapshot
promise above. Storage can move, but the bridge should not need a different
session-shape contract just because the backend changed from files to
PostgreSQL.

Current session-storage boundary:

- `src/session_store.py` owns durable metadata, latest progress, ordered
  results, snapshot reads, and known-session checks.
- `src/session_store_runtime.py` and `src/session_store_runtime_config.py`
  centralize the current file-backed default and rollback-safe runtime
  selection.
- `src/session_store_file.py` is the current file-backed implementation.
- `src/session_store_postgres_config.py` owns the PostgreSQL session env
  surface:
  - `ESM_SESSION_STORE_BACKEND`
  - `ESM_POSTGRES_SESSION_DATABASE_URL`
  - `ESM_POSTGRES_SESSION_AUTO_CREATE_TABLES`
  - `POSTGRES_SESSION_STORE_REAL_SMOKE`
- `src/session_store_postgres.py` owns the PostgreSQL bootstrap seam:
  driver loading, connection creation, schema initialization, the concrete
  PostgreSQL session-store adapter, and opt-in schema reset helpers for live
  smoke tests.
- Default behavior remains intentionally conservative:
  - `file` stays the active runtime default
  - invalid or missing backend config falls back to `file`
  - explicit `postgres` builds the PostgreSQL-backed `SessionStore`
  - PostgreSQL session storage is available now, but only on deliberate opt-in
- Bootstrap policy is explicit, not automatic:
  - session tables do not auto-create by default
  - app bootstrap may run `CREATE TABLE IF NOT EXISTS` only when
    `ESM_POSTGRES_SESSION_AUTO_CREATE_TABLES=1`
  - schema/bootstrap/migration detail is owned by
    `docs/session-persistence-audit.md`
  - normal PR and local validation should not require a live PostgreSQL server
  - `POSTGRES_SESSION_STORE_REAL_SMOKE=1` is reserved for optional live store
    and runtime smoke lanes
  - exact live-lane commands and scope belong in
    `docs/testing-and-validation.md`
- `src/session_service.py` and the session runner helpers consume that store
  contract instead of choosing backend details themselves.
- FastAPI, CLI, and frontend-facing readers depend on snapshot meaning and
  route behavior, not file names such as `session.json` or `results.jsonl`.
- Worker storage invariant:
  - parent process session reads and cancel writes, and detached-worker lifecycle
    writes, must resolve the same `SessionStore` backend for one session run
  - this is a behavior rule, not a transport rule; env inheritance, explicit
    worker env, or another future mechanism are all acceptable if they keep
    parent and worker on the same backend
- Worker logs, temp media, and HTTP/HLS replay keys are outside the durable
  snapshot unless a new public contract is introduced deliberately. Cancel
  intent is store-backed runtime control and is still not part of the public
  snapshot.

Current focused validation ownership for this boundary:

- `tests/test_session_store_runtime.py`
  - runtime backend selection, file fallback, rollback safety, and explicit
    proof that PostgreSQL is built only on deliberate opt-in
- `tests/test_session_store_postgres_config.py`
  - PostgreSQL env parsing, cache behavior, and URL/auto-create validation
- `tests/test_session_store_postgres.py`
  - bootstrap/config guards, missing-driver behavior, idempotent schema setup,
    adapter behavior/parity coverage, and opt-in live PostgreSQL smoke isolation
- `tests/test_session_store_file.py`
  - file-backed parity for the active runtime default

Update this contract doc when payload meaning or missing-session behavior
changes.

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

The complete MCP tool inventory, transport policy, result bounds, and MCP
error contract are maintained in [mcp-server.md](./mcp-server.md#current-tool-inventory).

Shared filter inputs:

- `session_id`
- optional `detector_id`
- optional `severity`
- optional `start_time_utc`
- optional `end_time_utc`

Raw alert lists and grouped timelines also accept `limit` and `offset` on both
FastAPI and MCP. `limit` defaults to 100 and is capped at 250; `offset`
defaults to 0. Paging preserves the existing alert or grouped-entry order.
Session snapshot reads keep their complete payload meaning and fail with a
structured `422` if the serialized HTTP response would exceed 2 MiB; they are
not silently truncated.

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
    malformed-timestamp error contract and hide unexpected storage diagnostics
- `tests/mcp_fastapi_parity_test_support.py`
  - tiny shared setup and meaning-assertion helpers for the split FastAPI/MCP
    parity suites
  - intentionally limited to protected-route setup, file-backed parity
    fixture setup, and cross-surface meaning helpers
- `tests/test_mcp_fastapi_boundary_split.py`
  - FastAPI-versus-stdio MCP local-trust boundary behavior for the current
    project stage
  - keeps all four tools outside FastAPI auth/rate-limit state and verifies
    they do not modify persisted session data
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
- shared CI ownership now centers on `.github/ci_test_targets.json`
- `.github/scripts/check_ci_target_drift.py` keeps workflow, policy, and
  CI-facing docs aligned through the shared manifest model
- protected CI consistency lanes run manifest validation, CI-owned test-path
  existence, drift checking, then manifest-backed main-PR policy validation
- the contract-relevant lane and policy details above are intentionally brief;
  use [ci-maintainer-guide.md](./ci-maintainer-guide.md) for the short CI
  ownership handoff and [testing-and-validation.md](./testing-and-validation.md)
  for the full CI lane, filter, split-suite, and validation model
- `tests/test_mcp_server_incidents_behavior.py`
  - grouped MCP no-alert behavior, filtered-data behavior, and stable empty
    grouped results for known sessions whose filters match nothing
  - keeps grouped output-shaping expectations separate from grouped MCP-facing
    error translation
- `tests/test_mcp_server_incidents_errors.py`
  - grouped MCP-facing error mapping over the shared grouped incident seam
  - includes the expectation that grouped timeline and grouped summary tools
    keep the same invalid-range and malformed-timestamp error contracts while
    hiding unexpected storage diagnostics

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
- unexpected MCP storage failures must not disclose backend diagnostics; use
  the detailed tool error policy in [mcp-server.md](./mcp-server.md)

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

- missing durable session metadata means the session is treated as not found
- missing alert rows for a known session means `[]`
- malformed alert rows are ignored rather than failing the whole query
- time filters use the existing persisted UTC timestamp format
- `counts_by_detector` uses stable detector ids such as `video_blur` and
  `video_metrics`, not human-facing alert titles
- these raw and summary response shapes stay the same regardless of whether
  the active alert backend is the default file store or the PostgreSQL store
- alert storage may validate known-session state through
  `SessionStore.session_exists(...)`, but it must not depend on the
  file-backed session layout or PostgreSQL session schema
- during migration, the alert backend and the session backend may differ; the
  stable rule is that session existence still comes from the active
  `SessionStore`, not from alert rows or storage-specific probing

### Compact Session Alert Report v1

The compact session alert report is a normalized read model for manual checks,
CLI output, and test assertions. It is derived from one persisted session
snapshot and keeps the snapshot as the source of truth.

Current report semantics:

- `session_id` and `input_path` come from the session snapshot metadata
- each report entry represents one raised alert row from the snapshot `alerts`
  list
- `segment` mirrors the alert `source_name`
- `detector_id`, `title`, `window_index`, `timestamp_utc`, and `message`
  preserve the same meaning they have in the raw alert-query contract
- the report may be rendered as JSON or as a small human-readable table, but
  the normalized field meanings stay the same
- the compact report is a local tooling/read-model helper; it does not define a
  new FastAPI or MCP transport contract

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

The grouped MCP tool inventory and transport policy are maintained in
[mcp-server.md](./mcp-server.md#current-tool-inventory). This section owns the
shared grouped response semantics used by both HTTP and MCP clients.

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

Near-term contract work:

- add explicit `api_stream` contract cases
- document reconnect and failure-state semantics
- keep these same contracts stable across future transport changes

That way the transport can change later without redefining the meaning of the
data.
