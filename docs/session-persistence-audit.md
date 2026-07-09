# Session Persistence Audit

This audit captures the current session persistence surface for the ongoing
session-store migration. Use it as the detailed storage inventory, ownership
map, and migration notebook.

Document split:

- keep [contracts.md](./contracts.md) short and focused on stable payload and
  seam contracts
- keep [session-model.md](./session-model.md) focused on session meaning and
  lifecycle semantics
- keep this file detailed, especially for module ownership, table mapping,
  runtime selection, and migration watchpoints

## Current Artifacts

| Artifact | Current owner | Write shape | Read path | Migration note |
| --- | --- | --- | --- | --- |
| `session.json` | `session_io.write_session_metadata(...)` through `session_runner_lifecycle` and terminal updates | Overwrite JSON | `session_io.read_session_snapshot(...)`, `session_io.session_exists(...)` | Current "known session" marker; alert reads still depend on it. |
| `progress.json` | `FileSessionStore.write_progress(...)` through lifecycle, execution, and terminal helpers | Overwrite JSON | `SessionStore.read_snapshot(...)` through the default file-backed store | Preserve frontend fields, latest-only semantics, and terminal `status_reason` / `status_detail` behavior. |
| `results.jsonl` | `session_io.append_result(...)` from `session_runner_execution.persist_bundle_events(...)` | Append-only JSONL | `session_io.read_session_snapshot(...)` | Keep append ordering and `latest_result` behavior stable. |
| `alerts.jsonl` | `session_alert_store.FileSessionAlertStore` through `session_io.append_alert(...)` | Append-only JSONL | Active alert-store contract and snapshot alert reads | Alerts already have file/PostgreSQL store selection. Known-session checks now route through the shared alert-side adapter backed by `SessionStore.session_exists(...)`. |
| `cancel_requested.json` | `FileSessionStore.request_cancel(...)` through `session_service.cancel_session(...)` and tests | Overwrite JSON marker | `SessionStore.is_cancel_requested(...)` in session execution and HTTP/HLS loader loops | Store-backed runtime control state, not historical data. Keep cancellation responsive. |
| `api_stream_seen_chunks.jsonl` | `session_io.append_api_stream_seen_chunk_key(...)` from `HttpHlsApiStreamLoader.persist_identity_key(...)` | Append-only JSONL | `session_io.read_api_stream_seen_chunk_keys(...)` during HTTP/HLS connect/restart | Live-stream replay/de-dup state; include in design, but do not treat as user-facing history. |
| `worker.log` | `session_service._spawn_session_worker(...)` | Append log file | Not part of the public snapshot; used for diagnostics | Keep file-backed for now unless a deliberate diagnostics surface is added. |
| API stream temp media files | `stream_loader_http_hls` materialization and cleanup helpers | Runtime files | Processed by detectors, then cleaned | Runtime artifact, not durable session data. Keep out of the session-store migration. |

## Current Ownership Map

- `src/session_service.py` owns start/read/cancel orchestration for FastAPI and CLI adapters.
- `src/session_runner.py` owns the worker-side execution flow and delegates persistence steps.
- `src/session_runner_lifecycle.py` owns pending and running metadata/progress transitions.
- `src/session_runner_execution.py` owns result/alert append calls and per-slice progress writes.
- `src/session_runner_terminal.py` owns terminal metadata/progress updates.
- `src/session_io.py` owns the file-backed persistence helpers used by the current default session store.
- `src/session_alert_store.py` owns the alert persistence seam and default file-backed alert log.
- `src/session_alert_store_postgres.py` owns the opt-in PostgreSQL alert table, while session metadata still decides whether a session is known.

## Session Snapshot Consumer Map

This is the current read-contract map for the public session snapshot:

- `session`
- `progress`
- `alerts`
- `results`
- `latest_result`

The main snapshot migration rule is simple: storage can change, but these
frontend-visible fields and their null-vs-empty behavior should stay stable
unless the project deliberately versions the contract.

### Primary runtime consumers

| Consumer layer | Main files | Snapshot dependency today | Migration watchpoint |
| --- | --- | --- | --- |
| Shared backend read service | `src/session_service.py`, `src/session_store.py`, `src/session_store_file.py`, `src/session_store_postgres.py` | Reads and returns the full public snapshot shape through `read_snapshot(...)` | The service layer is the canonical backend read boundary. Storage changes must preserve the same outer keys and missing-session shape. |
| FastAPI session route | `src/api/routers/sessions.py`, `src/api/schemas.py` | Exposes `session`, `progress`, `alerts`, `results`, and `latest_result` directly over `GET /sessions/{session_id}` | Pydantic validation will catch some drift, but route tests still matter because schema compatibility alone does not prove ordering or tolerant degradation. |
| Frontend bridge normalizer | `frontend/src/bridge/contractSessionSnapshot.ts` | Normalizes the full snapshot and fails closed on malformed nested payloads while keeping the outer shape stable | This is the most important frontend shape dependency. If nested payloads change, the UI may silently degrade to `null` or `[]` even when the backend still "works". |
| Frontend session hook | `frontend/src/hooks/useMonitoringSession.ts` | Polls snapshots, merges fallback `session`, preserves the last good snapshot on transient failures, and reads `progress.status_reason` / `status_detail` | Polling behavior depends on stable `session` and `progress` semantics, not only on type compatibility. |
| Frontend presentation layer | `frontend/src/components/SessionStatusPanel.tsx`, `frontend/src/components/SessionStatus.tsx`, `frontend/src/components/AlertFeed.tsx` | Reads session lifecycle, progress counts, latest detector fields, and alert collections for operator-facing UI | Small payload drift can change wording, counts, diagnostics, or empty-state behavior without breaking the backend route outright. |

### Contract-focused test consumers

| Test layer | Main files | What they currently protect |
| --- | --- | --- |
| API boundary regression | `tests/test_api_boundary_sessions_read.py`, `tests/test_session_service_read_cancel.py` | Populated/missing snapshot shape, ordered `results`, derived `latest_result`, and honest read/cancel behavior through the service and route layers |
| Store parity and backend-read tests | `tests/test_session_store_file.py`, `tests/test_session_store_postgres.py`, `tests/test_session_store_parity.py` | Missing-session shape, latest-only `progress`, append-ordered `results`, and `latest_result` derivation across file and PostgreSQL backends |
| Frontend bridge contract tests | `frontend/src/bridge/contract.session-snapshot.shape.test.ts`, `frontend/src/bridge/contract.session-snapshot.malformed.test.ts`, `frontend/src/bridge/contract.session-snapshot.collections.test.ts` | Outer snapshot keys, nested payload normalization, malformed-row tolerance, ordered `results`, and `latest_result` stability |
| Frontend polling and UI tests | `frontend/src/hooks/useMonitoringSession.lifecycle.test.tsx`, `frontend/src/hooks/useMonitoringSession.apiStream.test.tsx`, `frontend/src/components/SessionStatusPanel.test.tsx` | Polling tolerance, lifecycle wording, progress/status detail handling, and user-visible consequences of snapshot changes |

### Consumer-specific notes

- `latest_result` is a frontend-visible derived field, not an independent store.
  Tests and consumers expect it to follow the last valid row in ordered
  `results`, not a timestamp sort.
- `progress.latest_result_detector` and
  `progress.latest_result_detectors` are not a replacement for `latest_result`.
  The UI and bridge use both surfaces for different purposes.
- `alerts` are part of the session snapshot contract even though they come from
  the alert-store seam rather than the main session store.
- Missing-session behavior is a real contract:
  `session` and `progress` should degrade to `null`, while `alerts` and
  `results` should degrade to empty arrays and `latest_result` should degrade
  to `null`.

Snapshot migration rule:

- change storage behind `read_snapshot(...)`
- keep snapshot keys, null-vs-empty behavior, and ordered `results` stable
- keep bridge normalization and polling/UI assumptions true
- version the contract explicitly before changing any of those guarantees

## Durable Progress Contract

Progress persistence is the latest session read model, not a worker telemetry
dump and not an append-only history. Both file and PostgreSQL backends should
store the same stable fields:

- `session_id`
- `status`
- `processed_count`
- `total_count`
- `current_item`
- `latest_result_detector`
- `latest_result_detectors`
- `alert_count`
- `last_updated_utc`
- `status_reason`
- `status_detail`

These fields are durable because frontend polling, API/CLI reads, terminal
state, and contract tests depend on them. They are also enough to distinguish
pending, running, completed, cancelled, failed, and validation-failed states
without exposing backend internals.

Keep these values outside the progress contract unless a later product surface
intentionally promotes them:

- worker log paths and verbose log fields
- HTTP/HLS refresh, reconnect, cleanup, and replay-key telemetry
- temp media paths and cleanup details
- per-detector result payloads, which belong in ordered result rows
- alert payloads, which belong in the alert store

Migration rule: changing storage must preserve latest-only semantics,
null-vs-empty snapshot behavior, terminal `status_reason`/`status_detail`, and
the existing frontend polling shape.

Current progress behavior:

- progress persistence now goes through `SessionStore` in lifecycle,
  execution, and terminal helpers
- the file default is still active, so ordinary runs still
  produce `progress.json`
- explicit `ESM_SESSION_STORE_BACKEND=postgres` switches that same progress
  contract to PostgreSQL
- shared service reads, FastAPI reads, and frontend polling now consume that
  same progress contract through the store-backed snapshot path

Write-churn rule:

- progress writes remain latest-only
- timestamp-only refreshes should not create a new durable write
- real lifecycle, count, current-item, detector, or terminal-detail changes
  must still persist immediately so polling stays fresh

## Direct `session_io` Caller Inventory

This is the practical migration map for the current branch. The main
PostgreSQL session-store work should focus on callers that touch durable
session metadata, progress, results, or snapshot reads directly.

| Module | Direct `session_io` usage today | Durable-session concern | Migration priority | Keep out of this phase |
| --- | --- | --- | --- | --- |
| `src/session_service.py` | `read_session_snapshot(...)`, `SessionStore.request_cancel(...)` | Session snapshot read used by FastAPI and CLI read/cancel flows, plus cancel-intent writes | High | `get_worker_log_path(...)` is worker diagnostics, not part of the durable store. |
| `src/session_runner_lifecycle.py` | `initialize_session(...)`, `update_session_status(...)`, `write_session_progress(...)` | Pending and running metadata/progress writes | High | none in this module; these are core durable lifecycle writes. |
| `src/session_runner_execution.py` | `append_result(...)`, `write_session_progress(...)` | Ordered detector-result writes and latest progress updates | High | `append_alert(...)` and `is_session_cancel_requested(...)` should stay on the alert-store and runtime-control seams for now. |
| `src/session_runner_terminal.py` | `update_session_status(...)`, `write_session_progress(...)` | Terminal metadata/progress writes | High | none in this module; terminal persistence is part of the durable session read model. |
| `src/session_store_file.py` | file-backed adapter over `session_exists(...)`, `read_session_snapshot(...)`, `read_session_result_events(...)`, `write_session_metadata(...)`, `write_session_progress(...)` | Compatibility backend for the `SessionStore` contract | High | none; this adapter is the intentional bridge for parity and rollback. |
| `src/session_alert_store.py` | `get_session_dir(...)`, `session_exists(...)` | Alert-store known-session coupling | Medium | Alert rows stay on the alert-store contract; only the known-session check matters to the session-store migration. |
| `src/session_alert_store_postgres.py` | shared `require_known_session(...)` adapter | PostgreSQL alert reads now use the shared alert-side known-session adapter backed by `SessionStore.session_exists(...)` | Medium | Do not migrate alert persistence in this phase; keep the dependency limited to the known-session question. |
| `src/stream_loader_http_hls.py` | `append_api_stream_seen_chunk_key(...)`, `read_api_stream_seen_chunk_keys(...)`, `is_session_cancel_requested(...)` | Replay-key persistence and cooperative cancellation | Low for this phase | These are runtime coordination paths, not the first durable session-store surface. Keep them separate until the main session read model is stable. |

Practical migration rule:

- Rewire `session_service.py`, `session_runner_lifecycle.py`,
  `session_runner_execution.py`, and `session_runner_terminal.py` through the
  `SessionStore` seam first.
- Keep `session_alert_store*.py` on the alert seam and
  `stream_loader_http_hls.py` on the runtime-coordination seam until the
  durable session store has file/PostgreSQL parity.

## Alert / Session Coupling Audit

This inventory tracks how alert reads relate to the session-store migration
without letting alert behavior drift.

### Production coupling today

| Layer | Main files | Current coupling | Migration note |
| --- | --- | --- | --- |
| Raw alert file store | `src/session_alert_store.py` | Uses `get_default_session_store().session_exists(...)` to preserve unknown-session behavior, then resolves `alerts.jsonl` through `get_session_dir(...)` | The file backend is expected to stay file-shaped. The important rule is that "known session" should come from the session-store seam, not from alert-specific folder probing. |
| PostgreSQL alert store | `src/session_alert_store_postgres.py` | Calls the shared `require_known_session(...)` adapter before reading PostgreSQL alert rows | This is the most important coupling for the migration. PostgreSQL alert reads now validate against the active `SessionStore`, so explicit PostgreSQL session mode can answer the known-session question without a file-backed `session.json`. |
| Raw alert read model | `src/session_alerts.py` | No direct session-folder reads; depends only on `SessionAlertStore.read_session_alert_events(...)` and `SessionAlertsNotFoundError` | This layer is already in good shape. It should not need storage-aware changes beyond whatever the alert store does underneath. |
| Incident read model | `src/session_alert_incidents.py` | No direct session coupling; reuses the raw alert read model | Keep it storage-agnostic. |
| FastAPI alert routes | `src/api/routers/alerts.py` | No direct file/session coupling; maps shared service errors into HTTP responses | Route behavior should stay stable while storage changes below it. |

### Indirect coupling through tests and helpers

| Test surface | Main files | What is currently encoded |
| --- | --- | --- |
| File-backed alert-store tests | `tests/test_session_alert_store.py`, `tests/test_alert_query_service_read.py` | "Known session" still means persisted session metadata exists, while missing `alerts.jsonl` means empty alert history. |
| PostgreSQL alert-store tests | `tests/test_session_alert_store_postgres.py`, `tests/test_session_alert_store_parity.py` | PostgreSQL alert reads still perform a known-session pre-check before returning rows; several tests patch or compare that behavior explicitly. |
| API and MCP alert boundary tests | `tests/test_api_session_alerts.py`, `tests/test_api_session_alert_incidents.py`, `tests/test_mcp_server_alerts_behavior.py`, `tests/test_mcp_server_alerts_errors.py` | Public behavior depends on stable `SessionAlertsNotFoundError` mapping, not on storage details. |
| Alert test support | `tests/session_alert_test_support.py`, `tests/api_alert_test_support.py` | Helper builders still create file-backed session metadata plus `alerts.jsonl`, which is fine for file mode but should not become the only truth for PostgreSQL-backed alert/session combinations. |

### Audit conclusion

The coupling is real but fairly concentrated:

- the alert query services and FastAPI/MCP adapters are already backend-neutral
- the file-backed alert store is allowed to stay file-aware because that is its
  job
- the critical migration point is still the PostgreSQL alert-store known-session
  check, even after routing it through the shared adapter, because it assumes
  the active session-store backend describes the same session universe as the
  alert backend

### Ownership boundary decision

Alert storage owns alert events only. Session storage owns whether a session is
known.

Allowed dependency from alert storage to session storage:

- call `SessionStore.session_exists(session_id)` to preserve the public
  missing-session contract
- later, read a deliberately exposed session-metadata summary only if a real
  alert use case needs it and the contract is added explicitly

Disallowed dependencies:

- do not inspect `session.json`, `progress.json`, `results.jsonl`, cancel
  markers, worker logs, temp media, or PostgreSQL session tables from alert
  code
- do not infer known-session state from `alerts.jsonl` or PostgreSQL alert
  rows
- do not push storage-specific session fields into raw alert filtering,
  incident grouping, HTTP routes, or MCP tools

This keeps alert code allowed to answer "can this session have alerts?" while
keeping all session lifecycle, progress, result, and runtime-control details
inside the session-store contract.

Migration watchpoints:

- PostgreSQL alert reads must not stay tied to the old file-backed session
  marker. During migration, the active session store is the source of truth
  for "known session"; in PostgreSQL session mode that source of truth is
  PostgreSQL metadata, while file mode still preserves legacy behavior.
- File-backed alert storage remains the default runtime mode and the immediate
  rollback path. PostgreSQL-focused alert changes should not change legacy
  file behavior for missing sessions, empty `alerts.jsonl`, or append/read
  ordering through the default store.

### Watchpoints

- Keep the public rule stable:
  unknown session raises `SessionAlertsNotFoundError`, known session with no
  persisted alerts returns an empty list.
- Keep mixed-backend behavior explicit:
  PostgreSQL alerts with file-backed sessions are currently supported during
  migration, but only through the shared `SessionStore.session_exists(...)`
  check. Alert rows alone must never make a session look known.
- Update parity tests around behavior, not file paths or SQL details.
- Keep alert read models and HTTP/MCP adapters storage-agnostic while moving
  the existence check to the right shared seam.

## Session Store Injection Point Decision

Use the shared session layer as the default store boundary, with two explicit
entry points:

- `session_service.py` owns parent-process reads and cancel pre-checks for
  FastAPI and CLI adapters.
- `session_runner.run_local_session(...)` owns worker-process lifecycle writes
  and passes the store into lifecycle, execution, and terminal helpers.

`FileSessionStore` should remain the file default at both entry
points until the PostgreSQL store has parity coverage. API routers and CLI
handlers should keep calling `session_service` and `session_runner`; they
should not choose storage backends directly.

Why this point fits the current architecture:

- API-runtime wiring is too high because the detached worker is launched as a
  separate process through `session_cli.py run-session`. A FastAPI-only default
  would not cover worker-side metadata, progress, and result writes.
- Low-level helper wiring is too low because storage choice would spread across
  lifecycle, execution, terminal, and tests. Helpers can accept a store, but
  they should not decide the default backend.
- The shared service/runner boundary keeps tests practical: service tests can
  fake snapshot reads, runner/helper tests can pass an explicit store, and the
  default path still proves the current file-backed behavior.

Implementation rule: keep one small default-store access path, keep it
file-backed by default, and thread explicit stores only where tests or worker
helper calls need control. Do not put backend selection into FastAPI route
modules, CLI command handlers, alert stores, or HTTP/HLS loader code.

The default access path now lives in `src/session_store_runtime.py`.
`get_default_session_store()` returns the shared file-backed store by default,
and `src/session_store_runtime_config.py` owns the runtime selection rule for
`ESM_SESSION_STORE_BACKEND`. Missing, invalid, or explicit `file` config still
resolves to `FileSessionStore`, which keeps the rollback path obvious for the
later PostgreSQL cutover.

That runtime selection is now concrete for explicit PostgreSQL opt-in:
`ESM_SESSION_STORE_BACKEND=postgres` builds a `PostgresSessionStore` through
the same narrow bootstrap path, while ordinary runtime callers still stay on
the file default unless the backend is deliberately switched.

The PostgreSQL bootstrap surface now has one narrow owner:

- `src/session_store_postgres_config.py`
  - `ESM_POSTGRES_SESSION_DATABASE_URL`
  - `ESM_POSTGRES_SESSION_AUTO_CREATE_TABLES`
  - `POSTGRES_SESSION_STORE_REAL_SMOKE`
- `src/session_store_postgres.py`
  - driver loading
  - connection creation
  - idempotent schema bootstrap
  - a small `PostgresSessionStore` adapter over an injected connection
  - opt-in schema reset helpers for live smoke tests

The current live smoke stays deliberately narrow: it resets only the known
session-store tables, checks durable cancel intent, and confirms the public
snapshot shape through store reads.

That keeps runtime backend choice separate from PostgreSQL bootstrap settings
and test-only real-smoke toggles.

Its schema statements intentionally model the `SessionStore` contract, not the
old file inventory:

- one metadata table
- one latest-progress table
- one append-ordered results table
- `write_metadata` / `session_exists` own `session_metadata`
- `write_progress` owns `session_progress`
- `append_result` / `read_results` own `session_result_events`
- `read_snapshot` assembles the same read model from all three tables

Alerts, replay keys, logs, and temp media remain outside that first durable
session schema. Cancel intent uses a separate current-state table because it is
runtime coordination, not snapshot history.

Current PostgreSQL session tables, kept modestly:

| Table | Owns | Main contract use |
| --- | --- | --- |
| `session_metadata` | one authoritative metadata row per session | known-session checks, session summary reads, metadata writes |
| `session_progress` | one latest-only progress row per session | progress writes and snapshot reads |
| `session_result_events` | append-ordered detector result history | result appends, ordered result reads, derived `latest_result` through snapshot assembly |
| `session_cancel_requests` | one current-state cancel row per session | cooperative cancel polling through `request_cancel(...)` and `is_cancel_requested(...)` |

Keep this table as orientation, not as a full schema reference. Column-level
detail and bootstrap behavior stay owned by `src/session_store_postgres.py`.

That split is deliberate:

- it preserves the current durable session meaning
- it avoids creating one table per file artifact
- it keeps runtime-control and diagnostics state outside the durable snapshot
  model

Current adapter state:

- `write_metadata(...)` now upserts the authoritative metadata row
- `session_exists(...)` now follows metadata-row presence as the known-session
  marker
- `write_progress(...)` now upserts one latest-only progress row per session
- `append_result(...)` now persists ordered detector rows
- `read_results(...)` now returns detector rows in append order while skipping
  malformed rows
- `read_snapshot(...)` assembles metadata, latest progress, and ordered results
  into the same public shape as the file-backed store

The current bootstrap design stays intentionally small:

- one connection per explicit bootstrap/runtime store build
- no pooling yet
- no async DB path yet

That keeps cleanup and focused validation simple while the PostgreSQL
session-store adapter continues to mature.

For opt-in live PostgreSQL work, keep isolation explicit: the same bootstrap
module now supports dropping and recreating only the known session-store
tables, and test helpers keep those checks out of ordinary local and PR lanes.

The runtime validator now centralizes the branch rule:

- missing or invalid backend env still falls back to `file`
- explicit `postgres` selection keeps the parsed PostgreSQL settings attached
- missing or non-PostgreSQL URLs fail only for explicit `postgres` mode
- missing `psycopg` now fails only for explicit `postgres` mode and surfaces
  one actionable install message for local and CI environments
- session-table auto-create is now opt-in; the default is to require an
  explicit bootstrap helper or migration path rather than silently creating
  durable tables at runtime

Current callers now split cleanly:

- `session_service.py`, `session_alert_store.py`, and
  `session_alert_store_postgres.py` read known-session state through the
  default store path.
- `session_runner_lifecycle.py`, `session_runner_execution.py`, and
  `session_runner_terminal.py` accept the same store contract for metadata,
  progress, and result writes.
- `session_runner.run_local_session(...)` resolves the default store once and
  passes it through the worker flow.

That makes the migration boundary clearer:

- callers no longer need to know whether progress lands in `progress.json` or
  PostgreSQL
- backend selection stays in runtime config
- the remaining migration work is about finishing backend coverage, not about
  reintroducing direct progress-file ownership into runner code

## Cancellation Flow Audit

Cancellation now routes through narrow `SessionStore` runtime-control methods.
In the file default, those methods still persist the legacy marker file.
The public request path and worker observation path are deliberately separate:

| Stage | Current owner | Behavior to preserve |
| --- | --- | --- |
| API request | `src/api/routers/sessions.py` | `POST /sessions/{session_id}/cancel` delegates to `session_service.cancel_session(...)`; missing sessions map to `404`, terminal sessions map to `409`. |
| CLI request | `src/session_cli.py` | `cancel-session` uses the same service path, with a legacy missing-session fallback payload for CLI compatibility. |
| Service validation | `src/session_service.py` | Reads the current snapshot through the default store, rejects terminal sessions, then writes cancel intent. |
| Store-backed cancel write | `src/session_service.py` via `SessionStore.request_cancel(...)` | Writes idempotent cancel intent through the active store. In the file default this still produces `cancel_requested.json` with `{session_id, cancel_requested: true}`. |
| Local worker polling | `src/session_runner_execution.py` | Local slice loops check `SessionStore.is_cancel_requested(...)` before each slice and finalize to `cancelled` with `status_reason = cancel_requested`. |
| HTTP/HLS loader polling | `src/stream_loader_http_hls.py` | Live stream loading checks `SessionStore.is_cancel_requested(...)` during playlist polling, reconnect backoff, segment download, and temp-file materialization. |
| Terminal settlement | `src/session_runner_terminal.py` | Once the worker observes cancellation, metadata/progress settle to terminal `cancelled`; the transient `cancelling` summary is not the durable final state. |

Current tests protect both sides of the flow:

- `tests/test_session_io.py` keeps marker writes idempotent, tolerant, and
  path-safe.
- `tests/test_session_store_file.py`, `tests/test_session_store_postgres.py`,
  and `tests/test_session_store_parity.py` protect the shared cancel contract
  across file and PostgreSQL backends.
- `tests/test_session_service_read_cancel.py` and `tests/test_session_service.py`
  protect service-level allow/reject behavior and the transient cancel summary.
- `tests/test_api_boundary_sessions_cancel.py` protects FastAPI status mapping.
- `tests/test_session_runner_execution*.py` and
  `tests/test_session_runner_local.py` protect worker-side cancellation
  settlement.
- `tests/test_stream_loader_http_hls*.py` protects live HTTP/HLS cancellation
  during polling, reconnect, download, and cleanup paths.

Current cancellation contract:

- public request semantics stay in `session_service.cancel_session(...)`
  - missing session: structured not-found failure
  - terminal session: structured cancel-not-allowed failure
  - active session: accept and return transient `cancelling` summary
- low-level runtime-control semantics stay narrow
  - `request_cancel(session_id)`: idempotent write of cancel intent only
  - `is_cancel_requested(session_id)`: cheap boolean read only
  - missing runtime-control state reads as `false`
  - no normal "clear cancel" operation in production flow
- reset semantics should stay outside ordinary runtime behavior
  - new session id means fresh cancel state
  - explicit clear/reset is only for tests, isolated bootstrap helpers, or
    backend cleanup utilities

This keeps one useful separation: public cancel rules stay strict, while
worker/loader polling stays tolerant and cheap.

Current cancellation responsibility split:

- cancellation is both runtime coordination and bounded durable state
- it is runtime coordination because workers and live loaders poll it as an
  active stop signal
- it is bounded durable state because the parent process and detached worker do
  not share memory, and cancel intent must survive across that boundary
- it is not ordinary durable session history
  - do not expose it in the public snapshot
  - do not model it as append-only event history
  - do not move it into the main `SessionStore` read model

Current cancel-runtime note:

- worker and HTTP/HLS polling now read cancel intent through
  `SessionStore.is_cancel_requested(...)`, while the default file backend still
  preserves the legacy marker-file behavior underneath
- HTTP/HLS live polling now keeps a short in-memory negative-read cache so
  store-backed cancel checks stay cheap during bounded response reads, while
  reconnect/sleep boundaries still force a fresh read
- PostgreSQL mode now uses one lightweight runtime-control record per session
- keep worker reads cheap and direct; avoid full snapshot reads just to learn
  whether stop was requested
- avoid append-only cancel-event history unless product requirements later need
  audit trails separate from runtime stop behavior
- the detached worker now inherits the parent process runtime environment
  explicitly, so parent process reads/cancels and detached-worker writes
  resolve the same session-store backend by default

## Writer And Reader Map

| Persisted concern | Main writers | Main readers | Current coupling to preserve |
| --- | --- | --- | --- |
| Session metadata | `session_runner_lifecycle.initialize_pending_session(...)`, `session_runner_lifecycle.persist_pending_metadata(...)`, `session_runner_terminal.finalize_session_outcome(...)` | `session_io.read_session_snapshot(...)`, `session_service.read_session_snapshot_or_none(...)`, alert-store known-session checks | Public summary and current existence check. |
| Session progress | `session_runner_lifecycle.initialize_pending_session(...)`, `session_runner_lifecycle.start_running_session(...)`, `session_runner_execution.process_discovered_slices(...)`, `session_runner_execution.run_api_stream_session(...)`, `session_runner_terminal.finalize_session_outcome(...)` | `session_io.read_session_snapshot(...)`, FastAPI session reads, CLI session reads, frontend polling through the bridge | Progress is the latest snapshot, not a full history. Terminal reason/detail fields must survive storage changes. |
| Detector results | `session_runner_execution.persist_bundle_events(...)` through `SessionStore.append_result(...)`; file mode delegates to `session_io.append_result(...)` | `SessionStore.read_results(...)`, `SessionStore.read_snapshot(...)`, FastAPI/session-service reads, frontend/debug snapshot users | Append order matters because `latest_result` is derived from the last valid row. |
| Alerts | `session_runner_execution.persist_bundle_events(...)` through `session_io.append_alert(...)` and the active alert store | `session_io.read_session_snapshot(...)`, `session_alerts.py`, FastAPI alert routes, MCP alert tools | Snapshot alerts and dedicated alert surfaces must agree on the active backend. |
| Cancellation | `session_service.cancel_session(...)`, CLI cancel adapter, test helpers | `session_runner_execution` loops and `HttpHlsApiStreamLoader` runtime checks | Live stop signal; polling must stay cheap for local slices and live-stream loops. |
| API-stream replay keys | `HttpHlsApiStreamLoader.persist_identity_key(...)` | `HttpHlsApiStreamLoader.connect(...)`, reconnect/restart tests | These keys prevent replayed live chunks after reconnect or rerun. Ordering is less important than identity stability. |
| Worker diagnostics | `session_service._spawn_session_worker(...)` | Humans and tests that verify worker-log creation; not snapshot readers | Keep diagnostics out of the public session payload unless a later diagnostics API is intentionally added. |

## Runtime Entry Points

- FastAPI session routes call `session_service.start_session(...)`,
  `read_session_snapshot_or_none(...)`, and `cancel_session(...)`.
- The CLI uses the same session service for `start-session`, `read-session`,
  and `cancel-session`.
- The detached worker enters through `session_cli.py run-session`, then
  `session_runner.run_local_session(...)`.
- Local-file and local-segment execution use `process_discovered_slices(...)`.
- `api_stream` execution uses `run_api_stream_session(...)` plus
  `HttpHlsApiStreamLoader` for live chunk materialization, cancellation checks,
  and replay-key persistence.
- Snapshot reads are centralized behind `SessionStore.read_snapshot(...)`;
  the default file backend still delegates to `session_io`, but FastAPI and
  CLI callers should stay storage-neutral.

## Parent Vs Worker Config Path Audit

This is the current backend-selection path for one accepted start request:

1. FastAPI accepts `start-session` and calls `session_service.start_session(...)`.
2. `session_service.start_session(...)` validates input, builds the
   `session_cli.py run-session` command, and spawns a detached worker through
   `subprocess.Popen(...)`.
3. The parent process returns pending metadata immediately; it does not create
   the durable session record itself.
4. The detached worker enters through `session_cli.py _handle_run_session(...)`
   and calls `session_runner.run_local_session(...)`.
5. `run_local_session(...)` resolves the default store through
   `get_default_session_store()` and performs the durable metadata, progress,
   result, and terminal writes for the session.

Current storage-resolution observations:

- Parent process session reads and cancel writes already resolve through
  `get_default_session_store()` in `session_service.py`.
- Worker-side lifecycle writes resolve through the same
  `get_default_session_store()` call inside `session_runner.run_local_session(...)`.
- The worker command currently carries `mode`, `input_path`, `session_id`, and
  selected detectors only; it does not pass session-store backend or
  PostgreSQL settings as CLI flags.
- `subprocess.Popen(...)` now passes an explicit copy of the parent process
  environment, so the detached worker still inherits
  `ESM_SESSION_STORE_BACKEND` and any PostgreSQL session-store settings without
  introducing session-store-specific CLI flags.
- Store selection is cached per process, not shared across processes. That is
  fine for production, but it means parent process correctness does not prove
  worker-side correctness by itself.

Main failure mode to guard next:

- FastAPI can read or cancel against backend A while the detached worker writes
  to backend B if environment inheritance or runtime selection drifts.
- In that case, `start-session` still looks accepted, but later snapshot reads
  can look missing, stale, or split across backends.

Migration conclusion:

- The current architecture already has one good property: both parent and
  worker resolve storage through the same runtime-store helper.
- The weak point is process boundary transport, not store API shape.
- Validation should prove parent process / detached-worker backend agreement
  explicitly whenever runtime selection changes.

Worker storage invariant for the next implementation steps:

- for one session run, parent process reads and cancel writes, and detached-worker
  lifecycle writes, must resolve the same `SessionStore` backend
- this rule is intentionally behavior-level:
  - it does not require CLI flags instead of env inheritance
  - it does not require env inheritance instead of an explicit worker env map
  - it does require backend agreement across the process boundary
- any future runtime change that allows parent and worker to choose different
  session-store backends should be treated as a contract regression

Current worker-env decision:

- keep full parent-process environment inheritance for the detached worker
- pass it explicitly to `subprocess.Popen(...)` instead of relying on implicit
  default inheritance
- do not switch to a narrow env whitelist yet; the worker still depends on the
  same interpreter/runtime context as the parent process
- treat session-store backend settings as part of that inherited runtime
  contract, not as ad hoc CLI flags for now

## Lifecycle Transition Map

| Step | Persisted transition | Main owner | Notes for PostgreSQL migration |
| --- | --- | --- | --- |
| Start request accepted | none yet in the parent process; `start_session(...)` returns pending metadata after spawning the worker | `session_service.start_session(...)` | The worker creates durable session state. Avoid parent process durable claims unless reservation is deliberately designed. |
| Worker initialization | no session -> `pending` metadata and zero-count `pending` progress | `session_runner_lifecycle.initialize_pending_session(...)` | This creates the durable known-session marker and initial polling shape. |
| Source validation succeeds | `pending` metadata is rewritten with the validated input path | `session_runner_lifecycle.persist_pending_metadata(...)` | Preserve the normalized input path behavior so snapshots do not drift between parent request and worker execution. |
| Source validation or discovery fails | `pending` -> `failed` metadata and `failed` progress with `validation_failed` detail | `session_runner_terminal.finalize_validation_failure(...)` | Failed pending sessions must remain readable with a clear terminal reason. |
| Execution starts | `pending` -> `running`; progress is rewritten with the discovered total count | `session_runner_lifecycle.start_running_session(...)` | Local inputs know `total_count`; `api_stream` starts with `total_count = 0` and grows as chunks are accepted. |
| Slice/chunk processed | `running` remains `running`; append results/alerts; overwrite latest progress | `session_runner_execution.process_discovered_slices(...)` and `run_api_stream_session(...)` | Preserve result/alert order and latest-progress semantics. |
| Cancel requested | store-backed cancel intent is written; route/CLI may return transient `cancelling` summary | `session_service.cancel_session(...)`, `SessionStore.request_cancel(...)` | `cancelling` is a control response, not the durable settled state today. Workers poll the store-backed signal and then persist `cancelled` or `failed`. |
| Cancellation observed | `running` -> `cancelled`; terminal progress reason becomes `cancel_requested` | `session_runner_execution` through `session_runner_terminal.finalize_session_outcome(...)` | Keep cancellation checks cheap and frequent for local slices and live HTTP/HLS loops. |
| Normal finish | `running` -> `completed`; terminal progress is rewritten once | `session_runner_terminal.finalize_session_outcome(...)` | Completed local runs must report `processed_count == total_count`; live runs may complete because the loader stop reason is exhausted or complete. |
| Runtime failure | `pending` or `running` -> `failed`; terminal progress includes stable reason/detail | `session_runner_terminal.finalize_session_outcome(...)` | Keep failure reasons compact and avoid leaking transport internals into the main session contract. |

The durable state machine is defined by
`session_models.ALLOWED_SESSION_STATUS_TRANSITIONS`: `pending` may move to
`running`, `cancelled`, or `failed`; `running` may move to `completed`,
`cancelled`, or `failed`; terminal states only remain themselves. The
`cancelling` status exists for route/tooling summaries during shutdown, but
current file persistence normally uses `cancel_requested.json` until the worker
settles the session.

## Current Snapshot Contract

`session_io.read_session_snapshot(...)` is the current read-model contract for
the frontend bridge, FastAPI session reads, CLI reads, and lightweight tooling.
Storage can change, but this shape should not drift accidentally:

| Top-level field | Current meaning | Empty or missing behavior | Migration note |
| --- | --- | --- | --- |
| `session` | Session metadata: `session_id`, `mode`, `input_path`, `selected_detectors`, `status` | `null` when metadata is missing or malformed | This is both the public summary and the current known-session signal. FastAPI maps `null` to `404` through `session_service.read_session_snapshot_or_none(...)`. |
| `progress` | Latest progress snapshot: counts, current item, latest detector fields, alert count, status, `status_reason`, `status_detail` | `null` when progress is missing or malformed | Keep latest-snapshot semantics. Do not expose a progress history unless a separate contract is added. |
| `alerts` | Raw alert rows read through the active alert-store contract | `[]` when the session is unknown or has no alerts | Snapshot alerts must agree with dedicated alert routes and MCP alert tools for the selected backend. |
| `results` | Append-ordered detector result rows | `[]` when no valid results exist | Preserve append order because `latest_result` depends on the last valid row. |
| `latest_result` | Last valid item from `results` | `null` when `results` is empty | Keep this as a derived convenience field, not a separately writable source of truth. |

Compatibility rule: frontend and API readers depend on payload shape and field
meaning, not the storage backend. A PostgreSQL store can write correct rows and
still break the app if it changes null-vs-empty-list behavior, result ordering,
terminal progress fields, or route-level missing-session mapping.

Snapshot guardrails for the migration:

- keep the five top-level keys present on every successful snapshot payload
- preserve `session = null` as the low-level missing/corrupt metadata signal
- keep FastAPI responsible for turning a missing session into a structured
  route-level `404`, not a successful empty session read
- keep `alerts` and `results` as lists, even when empty
- keep `latest_result` derived from the last valid result row
- keep `worker.log`, replay keys, and temp media out of the public snapshot
  unless a deliberate new contract is added
- keep cancel intent out of the public snapshot even though it now uses the
  store-backed runtime-control methods

## Durable Data Vs Runtime Artifacts

PostgreSQL migration should not treat every session-directory file alike. Some
artifacts are durable read-model data, some are runtime coordination signals,
and some are local diagnostics.

| Concern | Category | Current artifact | First migration decision |
| --- | --- | --- | --- |
| Session metadata | Durable session data | `session.json` | Move behind `SessionStore`. This is the known-session marker and public summary. |
| Latest progress | Durable session data | `progress.json` | Move behind `SessionStore` while keeping latest-snapshot semantics. |
| Detector results | Durable session event data | `results.jsonl` | Move or abstract with append ordering preserved. `latest_result` remains derived from this stream. |
| Alerts | Durable alert event data | `alerts.jsonl` or PostgreSQL alert store | Keep aligned with the existing alert-store contract. Remove file-backed session-existence coupling only after session metadata has a PostgreSQL-backed existence check. |
| Cancel request | Runtime control state with durability needs | `cancel_requested.json` in file mode, `session_cancel_requests` in PostgreSQL mode | Do not expose in the public snapshot. Keep it as lightweight current state, not history. |
| API-stream replay keys | Runtime/restart coordination state | `api_stream_seen_chunks.jsonl` | Keep in scope for migration design because it affects reconnect/rerun correctness, but do not model it as user-facing session history. |
| Worker diagnostics | Local diagnostic artifact | `worker.log` | Keep file-backed for now. Move only if a separate diagnostics surface is designed. |
| API-stream temp media | Ephemeral processing artifact | temp `.ts` files under the stream temp directory | Keep filesystem-only. These are detector inputs during processing, not persisted session data. |

PostgreSQL session mode does not mean that every session-scoped artifact moves
into PostgreSQL. Worker diagnostics, replay/de-dup files, temp media, and
similar runtime-local artifacts still stay on disk in the current design.

Practical rule: migrate the data needed to rebuild the current snapshot and
alert/session query surfaces first. Treat cancellation and replay keys as
runtime coordination contracts with focused tests. Leave logs and temp media
local unless diagnostics or artifact retention become explicit product
features.

## Tests That Encode File Behavior

The suite protects two contracts: file-specific fallback behavior and
storage-independent public behavior. Keep both during the migration.

| Test area | Current examples | What the tests encode | Migration use |
| --- | --- | --- | --- |
| File-backed session helpers | `tests/test_session_io.py` | JSON/JSONL writes, malformed-file tolerance, empty snapshot shape, result ordering, `latest_result`, cancel marker files, worker-log path | Keep for the file default and any compatibility fallback. Add storage-neutral equivalents for `SessionStore`. |
| File-backed alert read behavior | `tests/test_alert_query_service_read.py`, `tests/test_session_alert_store.py` | Known-session checks through `session.json`, missing `alerts.jsonl` as empty alerts, corrupt-line tolerance | Keep while file alerts remain supported. Revisit known-session checks when PostgreSQL session metadata can answer existence. |
| PostgreSQL alert parity | `tests/test_session_alert_store_postgres.py`, `tests/test_session_alert_store_parity.py`, runtime alert route tests | Alert rows preserve fields, order, timestamp string shape, and file/PostgreSQL parity | Use as the pattern for the session-store migration: same public contract, different backend. |
| Shared session service | `tests/test_session_service_read_cancel.py`, `tests/test_session_service.py` | Missing snapshot -> `None`, cancel allowed/rejected states, transient `cancelling` summary, worker-log exclusion from public metadata | Expand around `SessionStore` so service behavior does not depend on raw files. |
| FastAPI session boundary | `tests/test_api_boundary_sessions_read.py`, `tests/test_api_boundary_sessions_start.py`, `tests/test_api_boundary_sessions_cancel.py`, `tests/test_api_boundary_contracts.py` | Stable route payloads, route-level `404`, validation errors, snapshot shape, null-vs-empty behavior, malformed nested payload handling, and store-backed progress reads during in-flight updates | Treat as high-value migration guards because the frontend depends on these shapes rather than storage files. |
| Runner and live-stream lifecycle | `tests/test_session_runner_lifecycle.py`, `tests/test_session_runner_terminal.py`, `tests/test_session_runner_execution*.py`, `tests/test_session_runner_api_stream*.py` | Pending/running/terminal writes, progress status reasons, cancellation timing, API-stream temp cleanup, de-dup state | Keep broad lifecycle assertions. Split any direct file assumptions from behavior that should work through both stores. |
| HTTP/HLS de-dup and cancel mechanics | `tests/test_stream_loader_http_hls*.py` | `api_stream` replay-key persistence and cooperative cancellation checks | Keep as runtime-coordination coverage. Cancel checks now read through the store; replay keys remain file-backed runtime state. |

Test migration rule: do not delete direct file tests when PostgreSQL arrives.
Add the storage seam and store-agnostic contract tests first, then keep file
tests scoped to the file backend. Public API/service tests should not assert raw
filenames such as `session.json` or `results.jsonl`; low-level file backend
tests may.

The file-backed parity lane now has a clear split:

- `tests/test_session_store_file.py` proves `FileSessionStore` matches
  `session_io` for missing-session shape, ordered result reads, and tolerant
  malformed-file behavior.
- `tests/test_session_store_contract.py` stays backend-neutral and checks only
  the durable store contract.
- Higher session-service and runner tests should keep asserting snapshot and
  lifecycle behavior, not the private file helper layout.
- Focused runtime integration tests now cover the default path too:
  `tests/test_session_runner_local.py` proves runner output is readable through
  `session_service`, and `tests/test_api_boundary_sessions_read.py` proves the
  FastAPI session route still reads a real file-backed snapshot end to end.
- `tests/test_session_store_runtime.py` now makes rollback intent explicit:
  runtime config stays centralized, invalid backend values degrade to file
  mode, and explicit `file` mode resolves to the same default store.
- `tests/test_session_runner_store_writes.py` keeps the helper-level write
  contract storage-neutral, so lifecycle/execution/terminal refactors do not
  silently fall back to raw file helpers.
- `tests/test_session_runner_progress.py` keeps timestamp-only progress
  refreshes from becoming extra durable writes.
- `frontend/src/bridge/contract.session-snapshot.shape.test.ts` and
  `frontend/src/hooks/useMonitoringSession.lifecycle.test.tsx` keep the
  frontend polling contract stable above the same store-backed snapshot path.

Current detached-worker runtime confidence is also intentionally split:

- `tests/test_api_boundary_sessions_runtime.py` covers the real FastAPI
  start/read/cancel path, but it keeps routine runtime confidence pinned to
  the default file-backed store on purpose.
- `tests/test_session_service_worker.py` covers detached-worker spawn,
  log-handle setup, and parent-to-worker session-store environment inheritance,
  including explicit PostgreSQL env propagation.
- `tests/test_session_store_runtime.py` covers runtime backend selection,
  explicit PostgreSQL validation, rollback-safe file defaults, and cache
  behavior.
- `tests/test_api_boundary_sessions_runtime.py` now has an opt-in live
  PostgreSQL start/read smoke proving FastAPI can accept a session and later
  read the first detached-worker snapshot from the selected PostgreSQL store.
- The same runtime file now also accepts honest early-read states before the
  detached worker catches up: route reads may still report a structured
  missing-session failure or a metadata-only snapshot before the first readable
  persisted snapshot appears.
- The opt-in live PostgreSQL runtime smoke now covers route-level cancel as
  durable store-backed intent: the route writes cancel intent, the worker
  observes it through the selected PostgreSQL store, and the session settles as
  `cancelled`.
- The same live runtime lane now also re-reads terminal `completed` and
  `cancelled` snapshots after settlement so the public session route keeps
  returning stable terminal data instead of a transient-only view.

Keep that live runtime contract intentionally small:

- FastAPI start accepts the session and returns pending metadata honestly.
- The detached worker later writes the first readable persisted snapshot.
- FastAPI read observes the persisted snapshot contract rather than local
  process guesses.
- FastAPI cancel reaches the worker through durable store-backed cancel intent.
- Terminal session state remains readable after worker settlement.
- Keep it opt-in behind the real DB env and explicit
  `ESM_SESSION_STORE_BACKEND=postgres`.

Leave these out of the live runtime smoke:

- store-parity details already owned by `tests/test_session_store_parity.py`
- runner-internal helper behavior already owned by focused runner tests
- detector, alert-rule, or frontend UX coverage
- broad failure-matrix or rollout coverage that belongs in later migration work

## Result Event Writer And Reader Audit

Detector result events now sit fully behind the session-store boundary.
The current code already has the right shape: runtime writers call
`SessionStore.append_result(...)`, file mode keeps the legacy `results.jsonl`
behavior through `FileSessionStore`, and PostgreSQL mode stores ordered rows in
`session_result_events`.

| Concern | Current owner | Migration risk |
| --- | --- | --- |
| Result production | `processor.run_enabled_analyzers_bundle(...)` returns bundle `results` rows | Detector payloads are intentionally JSON-shaped. Storage should not normalize every detector-specific key yet. |
| Runtime append | `session_runner_execution.persist_bundle_events(...)` converts bundle rows to `ResultEvent` and calls `SessionStore.append_result(...)` | This is the main write path. Keep alert writes separate on the alert-store path. |
| File-backed append | `FileSessionStore.append_result(...)` delegates to `session_io.append_result(...)` and `results.jsonl` | Keep JSONL tests as file-backend compatibility tests, not public API requirements. |
| PostgreSQL append | `PostgresSessionStore.append_result(...)` inserts into `session_result_events` | Ordering must come from a monotonic row id or sequence, not timestamp sorting. Project only shared query hints such as `detector_name` or `event_timestamp_utc`; keep detector-specific detail inside JSON. |
| Result reads | `SessionStore.read_results(...)` and `read_snapshot(...)` | Results must return only valid rows in append order and tolerate malformed backend rows where the file backend already does. |
| Latest result | `build_session_snapshot_payload(...)` and `session_io._build_session_snapshot(...)` derive `latest_result` from the final valid result row | Do not persist `latest_result` as an independent source of truth unless a later cache/invalidation design is added. |
| API/frontend shape | `session_service.read_session_snapshot(...)`, FastAPI reads, and bridge polling consume the snapshot | Keep `results` as a list and `latest_result` as either the final row or `null`; storage changes should not alter the payload shape. |

The important implicit dependency is append order. Existing tests assert that
`latest_result` is the last valid result row, not the newest timestamp. The
PostgreSQL path should therefore keep ordering explicit and deterministic, and
the parity tests should compare behavior rather than SQL internals. Equal or
reversed detector timestamps are not a durable tie-breaker; append sequence is.

Current migration note:

- result events are now store-backed on the main runtime path
- file mode remains the default and still materializes `results.jsonl`
- explicit PostgreSQL mode persists the same contract in
  `session_result_events`
- this is one session-store slice, not the end of the broader session
  persistence migration

For the current migration stage, the PostgreSQL row design should stay small:

- one monotonic durable row id for append order
- one stable `session_id`
- one stable `detector_id`
- optional projected shared hints for lightweight querying
- one raw JSON payload column for detector-specific structure

Do not normalize every detector metric into separate relational columns yet.

## Docs That Mention Session Persistence

Most docs match the current stage: file-backed session persistence is still the
default, the PostgreSQL session-store adapter now exists as an explicit opt-in,
and alerts stay file-backed by default with PostgreSQL opt-in. The risk is
future drift between the default path and the new backend.

| Doc area | Current claim style | Status now | Migration action |
| --- | --- | --- | --- |
| Root `README.md` | User-facing current state: session persistence defaults to the file-backed store; PostgreSQL session storage is available as explicit opt-in | Accurate for the current release stage | Keep README high-level and avoid schema/runbook detail. |
| `docs/session-model.md` | Canonical session semantics plus current file names and JSON/JSONL behavior | Accurate, intentionally file-specific | Keep semantic sections stable; keep file-specific wording under the file default now that `SessionStore` owns the storage contract. |
| `docs/contracts.md` | Snapshot contract and route behavior, with some file-backed implementation notes | Mostly storage-independent, with a few file examples | Preserve as the public contract reference. Replace implementation-specific "missing `session.json`" wording when known-session checks move behind a store. |
| `docs/data-models.md` and `docs/fastapi-boundary.md` | Snapshot/API shape rather than storage implementation | Low drift risk | Keep focused on payload shape. Avoid adding PostgreSQL implementation details here unless the API changes. |
| `docs/architecture.md` | Current runtime architecture: file-backed session state plus opt-in PostgreSQL alerts | Accurate but implementation-oriented | Update alongside the storage seam so architecture reflects file backend plus PostgreSQL backend rather than only files. |
| `docs/testing-and-validation.md` | Current lanes and test ownership, including session-store parity and optional live PostgreSQL session-store confidence | Accurate with recent adapter/test updates | Keep the fast-versus-live split explicit as coverage grows. |
| `docs/README.md` | Navigation to session model, contracts, and this audit | Aligned | Keep this audit linked while the migration is active. |

Docs migration rule: keep docs honest about the current default, but avoid
timeless phrasing that says "sessions are files" when the real contract is the
snapshot/read model. During implementation, update docs in this order:
`session-persistence-audit.md`, `session-model.md`, `contracts.md`,
`testing-and-validation.md`, `architecture.md`, then `README.md` only for
user-visible behavior.

For the current session-store migration slice, treat doc ownership this way:

- `docs/contracts.md`
  - public session snapshot contract, backend-selection promises, and what
    stays outside the public payload
- `docs/session-model.md`
  - lifecycle meaning, file-default runtime notes, and which artifacts still
    remain file-backed in the current local runtime
- `docs/testing-and-validation.md`
  - focused test ownership, file-default local lanes, and opt-in live
    PostgreSQL confidence
- `docs/session-persistence-audit.md`
  - PostgreSQL table mapping, migration notes, caller ownership, and
    implementation inventory
- `README.md`
  - short current-state summary only; no schema, table, or migration detail

## Migration Boundary Notes

Use this boundary as the guide for PostgreSQL session-store work.
The goal is storage parity, not a new session product surface.

The initial durable-session contract lives in `src/session_store.py` and is
intentionally narrow: metadata, latest progress, ordered detector results,
snapshot reads, and known-session checks. `src/session_store_file.py` proves
that contract against the current `session_io` behavior before runtime callers
are rewired.

The guard tests are split by purpose:

- `tests/test_session_store_contract.py` protects method shape and excluded
  runtime concerns.
- `tests/test_session_store_file.py` protects behavior through the store API:
  missing-session reads, snapshot round trips, ordered results, latest-only
  progress, and terminal progress.
- `tests/test_session_store_parity.py` compares file-backed and PostgreSQL-backed
  behavior for missing-session reads, lifecycle progress states, ordered result
  appends, and `latest_result` derivation.
  The explicit invariant is `latest_result == results[-1]` whenever ordered
  results are present.
- `tests/test_session_service_read_cancel.py` and
  `tests/test_api_boundary_sessions_read.py` protect the shared service and
  route consumers so ordered `results` and derived `latest_result` stay stable
  above the store layer.
- `frontend/src/bridge/contract.session-snapshot.shape.test.ts` protects the
  bridge-normalized snapshot shape so desktop polling consumers keep the same
  ordered `results`, derived `latest_result`, and latest-only progress fields.

Missing or malformed durable session data must keep the low-level empty
snapshot shape: `session = null`, `progress = null`, `alerts = []`,
`results = []`, and `latest_result = null`. FastAPI/service code remains
responsible for turning `session = null` into route-level not-found behavior.
Result rows read back in append order, with `latest_result` derived from the
final row. Progress remains latest-only. Cancellation now lives in
`SessionStore` only as a narrow runtime-control signal; HTTP/HLS replay keys
still stay out of the store boundary.

| Area | First migration decision | Reason |
| --- | --- | --- |
| Session metadata and existence | In scope | This is the current known-session marker and the base for route-level `404` behavior. |
| Latest progress snapshot | In scope | Frontend polling depends on the latest progress shape, counts, status, and terminal reason/detail fields. |
| Detector results | In scope | Snapshot `results` and derived `latest_result` must preserve append order. |
| Snapshot assembly | In scope | Readers should get the same five top-level keys regardless of backend. |
| Read/write split | In scope | Snapshot reads need stable shape; writes need lifecycle and ordering guarantees. |
| Missing-session behavior | In scope | Store reads return the empty snapshot shape; service/API layers map missing sessions to `None` and `404`. |
| Ordering and latest progress | In scope | Results need deterministic append order; progress is overwritten as the latest read model. |
| Store selection | In scope | Keep file-backed sessions as the default until PostgreSQL has parity tests and operational confidence. |
| Alert/session existence coupling | In scope as a design seam | PostgreSQL alert reads still need a backend-neutral known-session check. |
| Cancel requests | In `SessionStore` as narrow runtime-control methods, but out of the durable snapshot read model | Live control state. Keep it cheap to poll and do not model it as append-only history. |
| API-stream replay keys | Out of `SessionStore`; possible later runtime contract | Replay keys affect reconnect correctness, but they are runtime coordination rather than user-facing history. |
| Worker logs | Out of scope | `worker.log` is local diagnostics, not public session state. |
| API-stream temp media | Out of scope | Temporary `.ts` files are processing artifacts and should stay filesystem-only. |
| Frontend/API payload shape changes | Out of scope | Storage migration should not change the public session contract. |
| Making PostgreSQL the default | Out of scope for the first pass | Switch defaults only after parity, rollback, and operations are boring. |

Recommended implementation order:

1. Define a small session-store contract around metadata, progress, results, and snapshot reads.
2. Wrap the current file behavior behind that contract without changing defaults.
3. Reuse the store-contract tests for the PostgreSQL implementation before changing runtime callers.
4. Keep the PostgreSQL implementation and schema opt-in until parity and operations are proven.
5. Add file/PostgreSQL parity tests and focused FastAPI boundary tests.
6. Revisit replay keys and alert known-session checks after the durable read model is stable.

Hidden obstacles to keep visible:

- The parent FastAPI process returns pending metadata before the detached worker creates the durable session record.
- The detached worker and FastAPI process must resolve the same backend configuration.
- Rollback should mean one config decision, not code edits: when PostgreSQL
  session storage arrives, disabling it must still route both the parent
  process and detached worker back through `ESM_SESSION_STORE_BACKEND=file`.
- Result ordering and latest progress writes need clear transaction/consistency rules.
- Missing-session behavior has two layers: low-level empty snapshot and route-level `404`.
- Moving cancel or replay state too early can create slow polling, stale cancellation, or duplicate live chunks.
- File-specific tests should remain as backend tests; public API tests should stay storage-neutral.

## Migration Watchpoints

- Preserve the frontend snapshot shape: `session`, `progress`, `alerts`, `results`, and `latest_result`.
- Keep file-backed session persistence as the default until the PostgreSQL path is proven stable.
- Treat cancellation and `api_stream` de-dup keys as active runtime coordination, not passive history.
- Do not move `worker.log` or temporary media files into PostgreSQL in the first session-store migration.
- Remove the alert-store dependency on file-backed `session_exists(...)` only when PostgreSQL session metadata can answer the same known-session question.
- Update docs when backend defaults or known-session semantics change; do not
  leave file-specific wording in public contract docs after `SessionStore` owns it.
