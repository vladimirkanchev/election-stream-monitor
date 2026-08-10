# Contracts

This document defines stable shared payloads and boundary behavior between the
Python backend, Electron bridge, and frontend. It supports the local-first
prototype by making cross-layer promises explicit without becoming the
architecture narrative, lifecycle guide, migration inventory, or command
reference. Use [architecture.md](./architecture.md),
[session-model.md](./session-model.md),
[session-persistence-audit.md](./session-persistence-audit.md), and
[testing-and-validation.md](./testing-and-validation.md) for those owners.

## At a glance

Use this document for what callers may send, what they receive, and which
fields remain stable for tests, tools, and UI code.

| Need | Contract route |
| --- | --- |
| HTTP auth, rate limits, request errors, or source input | [FastAPI boundaries](#fastapi-authentication-contract-v1) and [API-stream start](#api-stream-start-session-contract-v1) |
| Detector catalog or durable runtime rows | [Detector catalog](#detector-catalog-v1), [session snapshot](#session-snapshot-v1), [result event](#result-event-v1), and [alert event](#alert-event-v1) |
| Playback, live loading, retries, or source trust | [Playback and API-stream contracts](#playback-source-resolution-v1) |
| Bridge calls and normalized frontend errors | [Electron bridge](#electron-bridge-contract-v1) |
| Plugin or structured-log safety | [Plugin security](#plugin-security-rules-v1) and [logging redaction](#logging-redaction-policy-v1) |

## Boundary Sources

- detector rows and catalog: [`src/analyzer_contract.py`](../src/analyzer_contract.py), [`src/detectors/registry.py`](../src/detectors/registry.py), [`src/processor.py`](../src/processor.py), and [`src/alert_rules.py`](../src/alert_rules.py)
- HTTP boundary: [`src/api/schemas.py`](../src/api/schemas.py) and [`src/api/routers/`](../src/api/routers)
- API-stream boundary: [`src/source_validation.py`](../src/source_validation.py), [`src/stream_loader_contracts.py`](../src/stream_loader_contracts.py), and [`src/stream_loader.py`](../src/stream_loader.py)
- session snapshot: [`src/session_store.py`](../src/session_store.py), [`src/session_store_runtime.py`](../src/session_store_runtime.py), and [`src/session_models.py`](../src/session_models.py)
- bridge normalization: [`frontend/src/bridge/contract.ts`](../frontend/src/bridge/contract.ts), [`frontend/src/bridge/transport.ts`](../frontend/src/bridge/transport.ts), and [`frontend/src/types.ts`](../frontend/src/types.ts)

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

When a change crosses a contract boundary, review the corresponding source
group above, the nearest backend or bridge boundary tests, and
[session-model.md](./session-model.md) when lifecycle meaning changes. The
protected `main` policy expects contract-sensitive code to move with nearby
tests and this owning document rather than landing as a silent shape change.

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

## FastAPI Request Boundary And Error Contract v1

The FastAPI application accepts at most 16 KiB for a `POST`, `PUT`, or `PATCH`
request body. A larger body is rejected before route validation or service
work with this stable `413` envelope:

```json
{
  "detail": "Request body exceeds the supported size",
  "error_code": "request_body_too_large",
  "status_reason": "request_body_too_large",
  "status_detail": "Maximum request body size is 16384 bytes."
}
```

An unexpected backend failure returns the standard `500` error envelope with
the stable status detail `The server could not complete the request.` It must
not reflect exception text, PostgreSQL diagnostics, SQL, filesystem paths, or
credentials. Route-specific field, page, response, and rate limits are owned
by the [FastAPI resource-control contract](./fastapi-boundary.md#rate-limit-and-resource-controls).
An eventual hosted deployment must apply equivalent or stricter ingress limits
before requests reach the application.

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
  - the current remote-analysis loader fetches direct HTTP/HLS playlists only
  - direct `.mp4` URLs remain valid for source validation and playback, not
    remote analysis loading
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
    "last_updated_utc": "2026-04-02 12:34:56",
    "status_reason": "running",
    "status_detail": null
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

### Snapshot meaning handoff

The null/list/order rules above define the public shape. The
[session model](./session-model.md#snapshot-population-rules) owns how that
shape is interpreted during startup, active work, terminal settlement, and
tolerant degraded reads. In particular, terminal snapshots stay readable and
a known session may temporarily have `progress = null`.

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

### Lifecycle meaning handoff

This contract owns the `status`, `status_reason`, and `status_detail` fields,
plus structured route and bridge errors. The
[session model](./session-model.md#session-lifecycle) owns transitions, startup
tolerance, terminal readability, `api_stream` recovery interpretation, and UI
handling. Request failures remain distinct from the state of an already-running
session; see [Route Failures Vs Session State](./session-model.md#route-failures-vs-session-state).

### Cancellation Contract v1

Purpose:

- keep the public cancellation request and response stable
- keep cooperative cancel intent outside durable session history

Public boundary rules:

- `cancel-session` accepts a known non-terminal session
- success returns a transient `cancelling` `SessionSummary` or `null`
- missing and terminal sessions return structured failures
- bridge errors preserve `backend_error_code`, `status_reason`, and
  `status_detail`; malformed non-null success payloads are rejected

Runtime-control rules:

- `SessionStore.request_cancel(...)` records idempotent stop intent but does not
  own lifecycle validation
- `SessionStore.is_cancel_requested(...)` returns a boolean; absent state is
  `false`
- cancel intent is write-once for one run, has no public "uncancel" operation,
  and remains outside the snapshot payload
- file and PostgreSQL backends preserve these semantics without exposing their
  marker or table representation

The [session model](./session-model.md#lifecycle-truth-table) owns cancellation
transitions, worker settlement, terminal readability, and frontend duplicate
request suppression. Store parity, service, API-boundary, runner, loader, and
bridge tests remain the behavioral evidence for this contract.

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

Current `video_metrics` failure handling:

- unavailable or malformed FFprobe duration metadata yields `duration_sec: 0.0`
  and `black_ratio: 0.0`; valid FFmpeg black-detection intervals remain
  reportable

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

This contract resolves one already-validated source for renderer playback; it
does not start monitoring or own live-loader retries.

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
- `currentItem` is optional context
- the backend returns an accepted remote `api_stream` URL unchanged

### API Stream playback behavior

For `api_stream`, playback resolution currently returns the validated original
remote URL directly:

```json
{
  "source": "https://example.com/live/playlist.m3u8"
}
```

The Electron main process adapts that value for the renderer: direct remote
media can remain remote, while remote HLS may use its opaque `local-media://`
proxy when browser CORS behavior requires it. The renderer never selects a
remote source or bypasses backend validation.

## API Stream Session Snapshot Semantics v1

`api_stream` uses the ordinary session snapshot shape:

- `session.mode` is `api_stream`
- `session.input_path` keeps the validated remote URL
- `progress.current_item` identifies the latest accepted slice
- `progress.processed_count`, alerts, results, and `latest_result` retain their
  normal meaning

The present HTTP/HLS runtime is bounded by its idle, refresh, and session
limits. It is not an open-ended live-service contract. Lifecycle, terminal
readability, and UI interpretation are owned by
[session-model.md](./session-model.md#session-lifecycle).

## API Stream Loader Seam v1

The loader owns remote ingestion for one validated source:

- connect, fetch, materialize, and yield normalized `AnalysisSlice` values
- apply transport retry, replay protection, and temporary-file limits
- release session-scoped resources on close

It does not own session transitions, persistence policy, detector execution, or
alert decisions. `session_runner` owns lifecycle and persistence; the
processor and rule layer own detector and alert behavior.

### Current source and trust contract

`api_stream` builders accept direct `http` or `https` `.m3u8` and `.mp4` URLs
for shared validation and playback. They reject blank URLs, embedded
credentials, webpage paths, and local/private targets by default. An optional
allowlist can narrow local mode; service mode requires an explicit allowlist.
DNS-backed private-host checks are opt-in.

The concrete remote-analysis loader currently implements HTTP/HLS media and
master playlists. Accepting a direct remote `.mp4` for validation or playback
does not promise HTTP/MP4 analysis loading; that would require a separately
reviewed loader contract.

## API Stream HTTP/HLS Loader Contract v1

The current HTTP/HLS loader is an implemented, bounded contract:

- it returns normalized `AnalysisSlice` values backed by session-scoped temp
  media
- media and master playlists are supported; a master playlist selects its first
  listed variant without bandwidth, resolution, or codec heuristics
- media playlists are polled; sliding windows, repeated segments, target
  duration drift, and incomplete transient refreshes are handled explicitly
- fetches, temp media, idle polls, refreshes, and overall session runtime have
  configured bounds
- cancellation is checked while waiting, backing off, reading, and materializing

Local HTTP fixtures keep HTTP/HLS coverage deterministic and offline. Their
exact test ownership and validation lanes belong in
[testing-and-validation.md](./testing-and-validation.md).

## API Stream Failure Semantics v1

- `temporary_failure`: one slice is skipped; no result or alert is emitted.
- `retryable_failure`: reconnect work is bounded by the configured budget and
  backoff; a recovered playlist continues from visible unseen segments.
- `terminal_failure`: the runner persists a failed snapshot.

Incomplete transient playlist refreshes are tolerated, while invalid numeric
playlist data fails clearly. `#EXT-X-ENDLIST`, the idle-poll budget, explicit
cancellation, and terminal failure stop the bounded run.

## API Stream Replay and Resource Policy v1

The loader owns reconnect attempts. Replayed slices are deduplicated before
persistence with `(source_group, window_index, source_name)`; the source group
is the validated URL and indexes are monotonic. Segment-download failures can
remain temporary while playlist failures consume the reconnect budget.

Temporary media lives under `API_STREAM_TEMP_ROOT / <session_id>` and is
cleaned on completion, cancellation, and terminal failure. Fetch size and
timeout, temporary-media size, playlist refreshes, and session runtime are all
bounded by configuration.

## API Stream Diagnostics and Deferred Evolution

The loader logs redacted source context, slice and playlist counters, replay
skips, and reconnect exhaustion. Those diagnostics are not a second public
session payload.

Open-ended monitoring, alternate-variant selection, specialized operator
messages, and SSE/WebSocket transport are deferred evolution, not current
contracts. They require an explicit product and runtime change rather than an
interpretation of this bounded HTTP/HLS behavior.

## Electron Bridge Contract v1

`window.electionBridge` is the renderer's narrow, typed transport boundary. It
does not expose raw IPC, backend process control, or filesystem access.

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

The error envelope can also carry sanitized `backend_error_code`,
`status_reason`, and `status_detail` when the backend supplied them. The
preload exposes exactly these operations:

- `listDetectors`
- `startSession`
- `readSession`
- `cancelSession`
- `resolvePlaybackSource`

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

The bridge preserves this snapshot shape across the file-backed default and
deliberately enabled PostgreSQL storage. Storage selection, worker-store
consistency, bootstrap policy, and rollout readiness belong to
[session-model.md](./session-model.md) and
[session-persistence-audit.md](./session-persistence-audit.md). Worker logs,
temporary media, replay keys, and cancel intent are not public snapshot fields.

Bridge and persistence behavior are covered by their focused contract and
parity suites; use [testing-and-validation.md](./testing-and-validation.md) to
choose the appropriate lane.

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

At the FastAPI and MCP boundaries, outer whitespace is trimmed and blank
values are rejected. Session and detector IDs are limited to 128 characters;
timestamp filters are limited to 64 characters.

Raw alert lists and grouped timelines also accept `limit` and `offset` on both
FastAPI and MCP. `limit` defaults to 100 and is capped at 250; `offset`
defaults to 0. Paging preserves the existing alert or grouped-entry order.
Each shared alert or incident read has a 5,000-row storage-work ceiling and
fails rather than returning a partial page or summary. The detailed local MCP
error and transport policy is owned by [mcp-server.md](./mcp-server.md).
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
"https://example.com/archive/recording.mp4"
```

Current bridge normalization:

- non-string values normalize to `null`
- blank strings normalize to `null`
- non-empty strings are trimmed before reaching the hooks
- explicit transport failures are raised with `PLAYBACK_SOURCE_RESOLUTION_FAILED`

For a remote HLS source, Electron may return an opaque `local-media://` proxy
URL instead of the backend's direct remote URL. This is a renderer transport
adaptation, not a second source-validation path.

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

## Deferred contract evolution

New transport capabilities, public stream states, and bridge operations require
an explicit contract and matching boundary tests. They must not be inferred
from current loader diagnostics or Electron implementation details.
