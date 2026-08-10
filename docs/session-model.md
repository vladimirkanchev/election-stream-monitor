# Session Model

This document defines persisted session meaning and lifecycle semantics for
contributors and coding agents. It is not end-user documentation, the full
payload catalog, or the migration inventory; use [architecture.md](./architecture.md),
[contracts.md](./contracts.md), and
[session-persistence-audit.md](./session-persistence-audit.md) for those.

## At a glance

- sessions give the backend and frontend one durable read model
- snapshots read through storage-neutral `SessionStore`; file storage is the
  default and PostgreSQL is explicit opt-in
- the snapshot `alerts` field follows the selected alert backend
- session and playback state are related but intentionally separate

## Why sessions exist here

The local desktop runtime persists session state and reads it through the
Electron bridge and local FastAPI boundary. This keeps a stable read model
without making the frontend depend on worker internals.

[`src/session_service.py`](../src/session_service.py) owns shared start, read,
and cancel behavior. FastAPI is the desktop runtime entrypoint; the CLI is
tooling over the same service. Change lifecycle mechanics there rather than
duplicating them in routes, CLI code, or the worker.

For a lifecycle change, read the shared service first, then the FastAPI route,
CLI adapter, and detached runner. That separates request ownership from the
worker path that produces the artifacts below.

## Session files

Each session currently writes these file-backed artifacts:

- `session.json`
- `progress.json`
- `alerts.jsonl`
- `results.jsonl`
- `api_stream_seen_chunks.jsonl` for `api_stream` de-duplication state
- `worker.log` as a backend-owned detached worker diagnostic trace

These are the file-backed representation under the configured `data/sessions/`
folder, not the full contract. The durable contract is the session snapshot
and the `SessionStore` semantics below.

Even with explicit PostgreSQL session mode, some runtime artifacts still stay
filesystem-backed in the current project stage:

- `worker.log` stays a local detached-worker diagnostic artifact
- `api_stream_seen_chunks.jsonl` stays a replay/de-dup coordination artifact
- HTTP/HLS temp media files stay session-scoped processing inputs on disk
- other temp-file and cleanup artifacts stay runtime-local rather than part of
  the durable session snapshot

## What each file means

### `session.json`

Stable session metadata:

- session id
- input mode
- input path
- selected detectors
- current or final session status

### `progress.json`

Incremental progress during a run:

- processed count
- total count
- current item
- latest result detector
- alert count
- status
- optional terminal `status_reason`
- optional terminal `status_detail`

Durable progress is a latest-only read model. Store only the fields needed by
session polling, terminal diagnostics, and backend/frontend contract tests:

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

Do not persist worker-only telemetry in this progress payload. Transport
refresh counters, reconnect counters, cleanup counts, replay keys, temp-file
paths, and verbose log context belong to worker diagnostics, HTTP/HLS runtime
state, or explicit result/alert rows. If a value is not needed to rebuild the
public session snapshot or explain the terminal state, keep it out of
`SessionProgress`.

Behavior depends a bit on mode:

- for `video_segments`, progress moves naturally segment by segment
- for `video_files`, one `.mp4` is expanded into one-second-like analysis slices
- for `api_stream`, progress moves accepted live slices/chunks and may stay
  open-ended while playback is still live

So `current_item` and `processed_count` for `video_files` are now slice-based,
not whole-file based.

Progress writes go through `SessionStore`: the default `FileSessionStore`
writes `progress.json`, while explicit
`ESM_SESSION_STORE_BACKEND=postgres` preserves the same semantics in
PostgreSQL. Timestamp-only refreshes are no-op writes so durable progress
remains meaningful while polling stays fresh.

### `alerts.jsonl`

Append-only alert events for the default file-backed alert backend.

These rows are still the source format for the default mode, but the code no
longer assumes that all alert reads come directly from this file. Alert reads
and writes now go through one internal seam, so the same session can also use
the PostgreSQL alert backend when explicitly selected.

### `results.jsonl`

Append-only detector result events for the session.

These durable detector outputs become snapshot `results` and derived
`latest_result`. The [result-event contract](./contracts.md#result-event-v1)
owns row shape and payload fields. File mode preserves JSONL append order;
PostgreSQL preserves monotonic row order. Timestamp order never changes that
history, and detector-specific metrics remain in `payload`.

Useful payload hints include source/timing context such as `timestamp_utc`,
`detector_name`, `source_name`, `window_index`, and `window_start_sec`, plus
alert context such as `title`, `message`, and `severity` when a detector
provides it. These remain payload fields so new detector metrics do not require
a storage-schema change.

### `worker.log`

Append-style worker process diagnostics for the detached `run-session`
background process.

This file is intentionally:

- backend-owned
- session-scoped
- useful for debugging startup/runtime failures
- not part of the frontend polling snapshot contract
- not currently returned by FastAPI as a public API field

That means the current session payload contract intentionally excludes
`worker_log_path`-style metadata. If the product later needs UI-facing
diagnostics, add that through a deliberate diagnostics field or endpoint
rather than growing the core session snapshot ad hoc.

For the current runtime, keep the file after success, failure, or cancel.
Do not auto-delete it as part of normal session cleanup.

FastAPI accepts start/read/cancel requests; the detached `run-session` worker
performs monitoring and leaves this trace. Parent reads and cancel writes must
resolve the same `SessionStore` backend as the worker's metadata, progress,
and result writes. Otherwise an accepted session can later look missing or
stale.

The worker inherits runtime store configuration. Newly created sessions, later
reads, and cancel requests therefore use one selected backend. Explicit
PostgreSQL mode reads only PostgreSQL-backed sessions; it does not silently
discover historical file-backed data. Backfill, dual-read, bootstrap, and
rollback decisions belong to the
[persistence readiness scorecard](./session-persistence-audit.md#current-persistence-readiness-scorecard).

## Persistence contract

The current persistence layer is intentionally simple, but it still has a
useful contract.

### Durable SessionStore contract

`SessionStore` owns durable metadata, latest progress, ordered results,
snapshot reads, known-session checks, and cancel intent. It is storage-neutral:

- file storage is the default; unsupported backend values resolve to it
- PostgreSQL requires explicit selection and valid bootstrap settings
- progress is latest state rather than history, and a metadata-only snapshot is
  valid
- results remain append ordered, and `latest_result` comes from the final valid
  row
- logs, replay keys, and temporary media are runtime artifacts, not snapshot
  data

Cancel intent is bounded durable coordination. `request_cancel(...)` and
`is_cancel_requested(...)` must work across the parent and worker but remain
outside the public snapshot and append-only history. Explicit PostgreSQL
failures stay visible rather than falling back to file storage.

For module ownership, schema/bootstrap, forward-only history, rollback, and
default-switch readiness, use [session-persistence-audit.md](./session-persistence-audit.md).
Use [testing-and-validation.md](./testing-and-validation.md) to choose a
validation lane.

### Alert storage boundary

`src/session_alert_store.py` owns validated raw alert rows; its file backend is
the default. `src/session_io.py::append_alert(...)` remains the compatibility
write entrypoint and reads snapshot alerts through the active alert backend.
`session_alerts.py` owns filtering and numeric summaries;
`session_alert_incidents.py` owns grouped timelines and summaries.

Alert storage may depend on the session model only for the known-session
question:

- allowed:
  - ask `SessionStore.session_exists(session_id)` before returning alert rows
  - treat a known session with no alert rows as empty alert history
- not allowed:
  - read session files or PostgreSQL session tables directly from alert code
  - infer session existence from an alert folder, alert table row, progress row,
    result row, cancel marker, worker log, or temp media file
  - depend on backend-specific session metadata shape inside alert filtering,
    grouping, or HTTP/MCP adapters

Practical effect:

- writes and reads now go through the same alert seam
- the dedicated alert routes/tools and the general session snapshot now agree
  on the active alert backend
- file remains the default alert backend; PostgreSQL is an explicit opt-in
  without moving filtering or grouping into the storage layer
- mixed runtime selection is still possible during migration; when alert and
  session backends differ, the alert side must keep treating the active
  `SessionStore` as the source of truth for whether a session is known

The PostgreSQL alert backend preserves the same alert-reader, snapshot, and
CLI semantics after explicit selection. For alert history, rollback,
cross-store reads, failure policy, and default-readiness evidence, use the
[persistence readiness scorecard](./session-persistence-audit.md#current-persistence-readiness-scorecard).

### Important field semantics

Some fields are especially important to interpret consistently:

- `current_item`
  - latest backend-analyzed item or slice, not necessarily the current playback item
  - for `video_files`, this is usually a `filename @ mm:ss` slice label
- `timestamp_utc` on alerts
  - backend detection time, not playback display time
- `window_index` and `window_start_sec`
  - optional temporal hints used for playback-aligned alert presentation
- `latest_result`
  - the last valid result event in `results.jsonl`, or `null`

## Session lifecycle

Typical flow:

1. session is created
2. initial files are written
3. status becomes `running`
4. progress/results/alerts are appended during processing
5. session ends as:
   - `completed`
   - `cancelled`
   - or `failed`

For `api_stream`, completion can happen because:

- the source reached `ENDLIST`
- idle polling budget was exhausted
- the session was cancelled
- a terminal loader/runtime failure occurred

For live sessions, `progress.json` now also carries:

- `status_reason`
  - machine-readable lifecycle reason such as `idle_poll_budget_exhausted`,
    `cancel_requested_after_iteration`, or `terminal_failure`
- `status_detail`
  - detailed failure text when the session failed terminally

### Current `api_stream` operational meaning

For the current runtime, `api_stream` sessions follow these operational rules:

- transient polling/read failures do not immediately clear the last good
  frontend session state
- retryable upstream failures remain recoverable until reconnect budget is
  exhausted
- reconnect-budget exhaustion and runtime safety limits are terminal outcomes
  for the run
- idle polling exhaustion persists as:
  - `status = completed`
  - `status_reason = idle_poll_budget_exhausted`
  - `status_detail = "Idle poll budget exhausted"`
- failed live runs intentionally keep a compact stable
  `status_reason = source_unreachable`, with the more specific loader/runtime
  cause preserved in `status_detail`
- frontend operator messaging may still surface idle exhaustion as a warning
  even though the persisted session outcome remains `completed`
- frontend live UX may also surface temporary reconnecting cues while the
  persisted session remains in its last good active state
- session summaries and diagnostics now intentionally distinguish:
  - reconnecting vs terminal failure
  - stopped by user vs failed
  - bounded completion vs bounded completion with idle-warning semantics

This is the current bridge between detailed backend observability and
operator-safe frontend wording.

Use [testing-and-validation.md](./testing-and-validation.md) for the current
frontend and runtime validation commands. The lifecycle guarantees here remain
the semantic owner; commands and lane selection do not.

Current lifecycle guarantees include:

- invalid lifecycle transitions are rejected centrally
- malformed persisted artifacts degrade to safe empty/null snapshot fields
- append-only event logs are preserved even when later lines are malformed

The backend also resets per-session rolling alert-rule state when a session
starts or ends.

### Backend Transition Rules

At the persistence-model layer, backend session metadata is the source of truth
for valid lifecycle transitions:

- `pending` may remain `pending` or move to `running`, `cancelled`, or `failed`
- `running` may remain `running` or move to `completed`, `cancelled`, or `failed`
- `cancelling` may remain `cancelling` or settle to `cancelled` or `failed`
- terminal states remain terminal and do not transition back into active work

The low-level cancel-request helper is intentionally narrower than the route
layer. It records store-backed cancel intent, while higher-level API and runner
behavior decide whether cancellation is valid for the current session state.

## Lifecycle Truth Table

This table defines the intended meaning of the current session lifecycle for the
local desktop runtime. It is the reference for backend behavior, FastAPI route
responses, Electron bridge mapping, and frontend session UX.

| Situation | Expected result | Notes |
| --- | --- | --- |
| start-session succeeds | return pending `SessionSummary` | The frontend may transition into active monitoring after later reads/polls. |
| start-session succeeds but the first read reports `session_not_found` | keep the started session active and retry on the next poll | The detached worker can lag briefly behind the accepted start request before the first persisted snapshot appears. |
| read/poll for an active session | return current persisted session snapshot | The persisted session snapshot is the source of truth, not inferred frontend state. |
| cancel-session for a running session | accept request and return `SessionSummary` or `null` | `null` is still a valid success when no updated summary is returned immediately. |
| cancel-session for a session already in a terminal state | return a structured failure | Do not silently treat an invalid cancel state as a normal success. |
| read/poll after a session completes | return terminal snapshot with `completed` status | Terminal state should remain readable after active processing stops. |
| read/poll after a session fails | return terminal snapshot with `failed` status and details | Failure reason should remain available through persisted progress fields. |
| read/poll while a session is cancelling | may temporarily return `cancelling` before terminal settlement | Frontend should tolerate short transition windows during shutdown. |
| read/poll after a session is cancelled | return terminal snapshot with `cancelled` status if persisted | `cancelled` is terminal once the backend settles there. |
| read/poll with a stale or missing session id | return a structured missing-session failure | Do not synthesize empty success payloads for missing sessions. |
| cancel-session with a stale or missing session id | return a structured missing-session failure | Do not silently succeed or fallback. |
| polling read fails transiently while the last good snapshot is still known | keep the last good session state in the UI and retry on the next interval | Polling failures are intentionally tolerant at the frontend session layer. |
| repeated cancel requests arrive while a previous cancel request is still pending | suppress duplicate cancel requests | The frontend should keep one in-flight cancel request rather than fan out repeated stop attempts. |
| the UI has already settled into terminal `completed` state before another stop attempt | suppress the extra stop request and keep the completed view | The app-level session UX prefers the settled terminal state over issuing a late cancel request that can no longer change the outcome. |
| read/poll reports `session_not_found` after a cancel request has already moved the UI into `cancelling` | keep the last good ending state rather than surface a new route error immediately | Current frontend behavior prefers a stable shutdown UX over replacing the ending state with a transient missing-session error. |

### Interpretation Rules

- Persisted session snapshots are the source of truth for lifecycle state.
- Route-level request failures and session lifecycle state are different things.
- Low-level missing-session shape and route-level missing-session errors are
  both intentional: the store contract keeps one stable empty snapshot shape,
  while service and route layers decide when that becomes a structured missing
  session failure.
- Metadata-only snapshots are valid during startup, recovery, or tolerant
  degraded reads; `progress` may be `null` without making the session itself
  invalid.
- Cancel intent is durable runtime coordination, not part of the public
  snapshot payload.
- Terminal states should remain readable after a session stops running.
- The parent process and detached worker must resolve the same backend so an
  accepted session does not later read as missing or stale.
- Invalid cancel requests should fail clearly rather than look like successful cancellation.
- Frontend transport normalization should preserve these meanings rather than reinterpret them.
- Frontend polling is intentionally tolerant of one-off read failures and keeps the last good session state instead of clearing the session immediately.
- Frontend stop behavior should suppress duplicate in-flight cancel requests and prefer a stable ending/terminal state over repeated stop churn.
- Once the UI has already settled into `completed`, the app suppresses another stop request rather than surfacing a late cancel-state failure from a request it no longer needs to send.

The matching minimum runtime integration boundary is documented in
[testing-and-validation.md](./testing-and-validation.md).

### Snapshot population rules

For the current project stage, these population rules are part of the session
meaning, not only of one backend implementation:

- a missing session is not the same thing as an empty but valid active session
- `session` is the anchor for "this session is known"
- `progress` may legitimately be `null` during startup, after tolerant
  degraded reads, or before a valid latest-progress payload exists
- `alerts` and `results` should stay list-shaped even when empty
- `latest_result` should always match the last valid ordered row in `results`
  when one exists
- low-level cancel intent stays outside the public snapshot payload
- committed `results` and `alerts` remain readable after terminal
  `completed`, `failed`, or `cancelled` settlement

This is a stable read-model promise across backends, not a claim that migration
is complete. Missing store reads degrade to the stable empty snapshot shape;
the API later turns that result into a structured missing-session failure when
appropriate.

## Route Failures Vs Session State

The current project intentionally uses two different failure channels:

- immediate request failure
  - returned as a structured API error payload
- ongoing or terminal session lifecycle state
  - returned through the persisted session snapshot

Important snapshot progress fields are:

- `progress.status`
- `progress.status_reason`
- `progress.status_detail`

This separation matters now that FastAPI route-level failures and persisted
session state are both part of the backend contract.

## Notes For Agents

Treat `src/session_store.py` as the durable-session boundary and snapshot
meaning as more stable than file layout. A changed field meaning requires this
document, [contracts.md](./contracts.md), and affected readers/tests to move
together. Update the persistence audit only when rollout readiness changes.

## Important design point

A session is not playback. Setup, session, and playback state remain separate
so bridge normalization, source resolution, and polling can handle their own
errors without redefining lifecycle meaning. Storage and transport can evolve
later, but should not change what a session, progress snapshot, alert, or
result means.

## Evolution boundary

Future storage or transport work may change file representation, backend
selection, or delivery mechanism. It must preserve the durable session read
model, progress and event meaning, lifecycle transitions, and the separation
between session and playback state. Use the persistence audit for rollout
decisions rather than treating this document as a migration plan.
