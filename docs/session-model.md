# Session Model

This document explains the current session contract between the Python backend
and the frontend.

It is meant for contributors and coding agents working on the session layer,
not as end-user documentation.

Use this doc for persisted session meaning and lifecycle semantics.
Do not use it as the main architecture overview, the full payload catalog, or
the migration inventory; see [architecture.md](./architecture.md),
[contracts.md](./contracts.md), and
[session-persistence-audit.md](./session-persistence-audit.md).

## At a glance

- sessions are the persisted contract between backend and frontend
- session snapshots now read through the storage-neutral `SessionStore`
- file-backed session persistence is still the file default
- PostgreSQL session persistence is available only through explicit opt-in
- this document explains what session data means, not which module writes it
- alert storage stays file-backed by default for this branch phase and can now
  switch to PostgreSQL
- the snapshot `alerts` field now follows that same alert backend
- monitoring session state and playback state are related but intentionally
  separate

## Why sessions exist here

The frontend and backend do not talk through a full web service yet.

Instead, the backend persists session state locally and the frontend reads it
through the local bridge. That keeps the current project simple while still
giving a clear session lifecycle and a stable read model.

For start/read/cancel ownership, the shared application service now lives
in [`src/session_service.py`](../src/session_service.py).

In practice:

- FastAPI is the canonical runtime entrypoint for desktop session lifecycle work
- the CLI is tooling/debugging over the same shared session service
- session lifecycle mechanics should be changed once in that shared service,
  not reimplemented separately in route and CLI layers

Recommended reading order for start/read/cancel work:

1. [`src/session_service.py`](../src/session_service.py)
2. [`src/api/routers/sessions.py`](../src/api/routers/sessions.py)
3. [`src/session_cli.py`](../src/session_cli.py)
4. [`src/session_runner.py`](../src/session_runner.py)

That order separates request ownership from the worker execution path that
actually produces the persisted session artifacts described below.

## Session files

Each session currently writes these file-backed artifacts:

- `session.json`
- `progress.json`
- `alerts.jsonl`
- `results.jsonl`
- `api_stream_seen_chunks.jsonl` for `api_stream` de-duplication state
- `worker.log` as a backend-owned detached worker diagnostic trace

These files live under the configured session output folder in `data/sessions/`
when the default file-backed session store is active. They describe the
current file representation, not the whole contract by themselves. The durable
contract is the session snapshot plus the `SessionStore` semantics described
below.

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

Current progress behavior:

- progress writes now go through `SessionStore`
- the file default still persists them to `progress.json` through
  `FileSessionStore`
- explicit `ESM_SESSION_STORE_BACKEND=postgres` persists the same contract in
  PostgreSQL
- timestamp-only refreshes are treated as no-op writes so durable progress
  stays meaningful while polling remains fresh

### `alerts.jsonl`

Append-only alert events for the default file-backed alert backend.

These rows are still the source format for the default mode, but the code no
longer assumes that all alert reads come directly from this file. Alert reads
and writes now go through one internal seam, so the same session can also use
the PostgreSQL alert backend when explicitly selected.

### `results.jsonl`

Append-only detector result events for the session.

These are the durable detector outputs that later snapshot reads expose through
`results` and the derived `latest_result` field.

The durable row contract stays intentionally compact:

- top-level required fields:
  - `session_id`
  - `detector_id`
  - `payload`
- ordering is durable behavior, not a public row field:
  - file mode preserves JSONL append order
  - PostgreSQL mode must preserve monotonic row order
- matching or reversed detector timestamps do not change that history order
- `latest_result` remains a derived convenience value from the final valid row
- shared source/timing hints may appear inside `payload` when available:
  - `timestamp_utc`
  - `detector_name`
  - `source_name`
  - `window_index`
  - `window_start_sec`
- alert-like context may also appear inside `payload` when detectors expose it
  for later rule/debug interpretation:
  - `title`
  - `message`
  - `severity`

Detector-specific metrics still belong in `payload`, so detector evolution does
not require a schema change for every new measurement.

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

The current runtime split is:

- FastAPI owns start/read/cancel request handling
- the detached `run-session` worker owns actual monitoring execution
- `worker.log` is the per-session backend trace left by that worker-side
  execution path

Worker storage invariant for this split:

- the parent process may accept the request first, but parent process reads and
  cancel writes must still target the same session-store backend that the
  detached worker uses for durable metadata, progress, and result writes
- the contract is backend agreement, not a requirement to pass settings in one
  specific way
- if parent and worker drift onto different backends, accepted sessions can
  later look missing or stale even though both processes are individually
  working

Current runtime note:

- the detached worker inherits the same session-store runtime configuration as
  the parent process
- file-backed session storage remains the default runtime path
- PostgreSQL session storage is still explicit opt-in

## Persistence contract

The current persistence layer is intentionally simple, but it still has a
useful contract.

### Durable SessionStore contract

For the PostgreSQL migration path, treat durable session meaning as
storage-neutral even though the file-backed implementation is still the runtime
default.

- `SessionStore` owns durable session metadata, latest progress, ordered
  detector results, snapshot reads, known-session checks, and cancel intent.
- File-backed session storage is still the runtime default.
- PostgreSQL session storage is available only through explicit opt-in.
- Missing or invalid PostgreSQL bootstrap config should fail clearly only in
  explicit PostgreSQL mode; it should not silently replace or break the file default.
- Progress is a latest-only read model, not an event history.
- Results are append-ordered history, and `latest_result` is derived from the
  final valid ordered row.
- Cancel intent is bounded durable coordination state:
  the system must preserve it across the parent process and detached worker,
  but it is not part of the public session snapshot.
- Logs, replay keys, temp media, and other runtime artifacts stay outside the
  durable session contract unless a separate contract is added.
- The parent process and detached worker must resolve the same backend so
  accepted sessions do not later look missing or stale.

For the current migration stage, cancel-request state should be treated as
runtime coordination with bounded durability:

- runtime coordination because the worker and live loader poll it as an active
  stop signal
- bounded durability because cancel intent must cross the parent process /
  detached-worker boundary reliably
- the active contract is now `SessionStore.request_cancel(...)` and
  `SessionStore.is_cancel_requested(...)`
- file-backed storage remains the file default unless
  `ESM_SESSION_STORE_BACKEND=postgres` is explicitly selected
- not part of the durable session snapshot read model and not ordinary
  append-only session history

For module ownership, PostgreSQL table mapping, runtime selection, and focused
validation lanes, use [session-persistence-audit.md](./session-persistence-audit.md).

### Session-scoped files

These files belong to one session directory:

- `session.json`
- `progress.json`
- `alerts.jsonl`
- `results.jsonl`
- optional `worker.log`
- optional `api_stream_seen_chunks.jsonl`

That means one session directory still holds the current file-backed runtime
state for one monitoring run. Frontend and API callers should still treat the
session snapshot, not raw filenames, as the stable read contract.

### Write semantics

Current write behavior is:

- `session.json`
  - overwrite-style metadata snapshot
- `progress.json`
  - overwrite-style latest progress snapshot
- `alerts.jsonl`
  - append-only alert event log
- `results.jsonl`
  - append-only detector result event log

Alert writes now go through the same narrow seam as alert reads:
`src/session_io.py::append_alert(...)` remains the compatibility entrypoint,
while `src/session_alert_store.py` owns the default file-backed append/read
behavior for one session's raw alert rows.

### Meaning of the persisted data

- `session.json`
  - stable session identity and configuration
- `progress.json`
  - latest known runtime progress for the active or finished session
- `alerts.jsonl`
  - alert incidents raised by the backend rule layer
- `results.jsonl`
  - detector outputs before or alongside alert interpretation
- `api_stream_seen_chunks.jsonl`
  - persisted de-duplication keys so reconnects and reruns can skip replayed
    live chunks

### Alert storage boundary

Alert persistence now has one explicit internal boundary:

- `src/session_alert_store.py`
  - owns appending and reading validated raw alert rows for one session
  - defaults to the file-backed alert backend in this branch phase
- `src/session_io.py`
  - keeps `append_alert(...)` as the compatibility write entrypoint
  - keeps session snapshot assembly file-backed for metadata, progress, and results
  - reads the snapshot `alerts` field through the active alert backend
- `src/session_alerts.py`
  - owns raw alert filtering, timestamp handling, and numeric summaries
- `src/session_alert_incidents.py`
  - owns grouped incident timelines and grouped incident summaries

Practical effect:

- writes and reads now go through the same alert seam
- the dedicated alert routes/tools and the general session snapshot now agree
  on the active alert backend
- the default file-backed mode keeps the persisted `alerts.jsonl` contract
  unchanged
- the PostgreSQL alert store can be enabled without moving filtering or
  grouping into the storage layer
- the current rollout state is simple:
  - file is still the default backend
  - PostgreSQL is the supported opt-in backend

The current PostgreSQL alert path keeps that contract narrow too:

- the PostgreSQL alert table is `session_alert_events`
- the runtime backend mode now switches explicitly between `file` and
  `postgres` through `ESM_ALERT_STORE_BACKEND`
- each current alert field maps to its own column rather than a JSON payload
- `window_index` and `window_start_sec` remain nullable
- read order should preserve append order through `ORDER BY id ASC`
- `timestamp_utc` should be materialized back into the current
  `%Y-%m-%d %H:%M:%S` string contract on reads
- a concrete `PostgresSessionAlertStore` now exists behind the same seam, and
  runtime selection can opt into it without changing the alert readers,
  snapshot route, or CLI read path

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

### Current persistence split

The project currently uses:

- JSON / JSONL for session and event persistence
- CSV-backed stores for detector metric families

This is acceptable for the current local-first stage.

### Future evolution

The meaning of these persisted artifacts should stay stable even if the storage
implementation changes later.

For example, the project could later move from file-based persistence to
SQLite or a service-backed store without changing:

- what a session is
- what a progress snapshot means
- what an alert event means
- what a detector result event means

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

### Current validation baseline

At the end of this branch, the lifecycle behavior above is treated as settled
because it is covered by the current validation checks:

- frontend package:
  - `npm run test:electron-bridge`
  - `npm run test:frontend-checkpoint`

These are the baseline validation commands to rerun before further lifecycle
doc changes. They help keep the canonical docs tied to tested behavior rather
than to planning-only intent.

The session model is stricter now than in earlier iterations:

- invalid lifecycle transitions are rejected centrally
- malformed persisted artifacts degrade to safe empty/null snapshot fields
- append-only event logs are preserved even when later lines are malformed

The backend also resets any per-session rolling alert-rule state when a session starts or ends.

### Backend Transition Rules

At the persistence-model layer, backend session metadata is the source of truth
for valid lifecycle transitions:

- `pending` may remain `pending` or move to `running`, `cancelled`, or `failed`
- `running` may remain `running` or move to `completed`, `cancelled`, or `failed`
- `cancelling` may remain `cancelling` or settle to `cancelled` or `failed`
- terminal states remain terminal and do not transition back into active work

The low-level cancel-request helper is intentionally narrower than the route
layer. It records cancel intent as a file-backed marker, while higher-level API
and runner behavior decide whether cancellation is valid for the current
session state.

## Lifecycle Truth Table

This table defines the intended meaning of the current session lifecycle for the
local desktop runtime. It is the reference for backend behavior, FastAPI route
responses, Electron bridge mapping, and frontend session UX.

| Situation | Expected result | Notes |
| --- | --- | --- |
| start-session succeeds | return pending `SessionSummary` | The frontend may transition into active monitoring after later reads/polls. |
| start-session succeeds but the first read reports `session_not_found` | keep the started session active and retry on the next poll | The detached worker can lag briefly behind the accepted start request before the first persisted snapshot appears. |
| read/poll for an active session | return current persisted session snapshot | Persisted session files are the source of truth, not inferred frontend state. |
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
- Terminal states should remain readable after a session stops running.
- Invalid cancel requests should fail clearly rather than look like successful cancellation.
- Frontend transport normalization should preserve these meanings rather than reinterpret them.
- Frontend polling is intentionally tolerant of one-off read failures and keeps the last good session state instead of clearing the session immediately.
- Frontend stop behavior should suppress duplicate in-flight cancel requests and prefer a stable ending/terminal state over repeated stop churn.
- Once the UI has already settled into `completed`, the app suppresses another stop request rather than surfacing a late cancel-state failure from a request it no longer needs to send.

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
- committed `results` and `alerts` remain readable after terminal
  `completed`, `failed`, or `cancelled` settlement

This is a stable read-model promise across backends. File-backed storage is
still the default runtime path, and PostgreSQL remains explicit opt-in, but
the same session state should still yield the same public snapshot shape and
the same `results` / `latest_result` relationship.

At the backend persistence-helper layer, missing session snapshot reads still
degrade to the stable empty snapshot shape. Structured missing-session failures
are introduced later at the API boundary when that empty snapshot means
"session not found" for a route-level request.

That parity promise is narrower than "migration complete." It covers the
public session snapshot contract while storage ownership is still moving
behind `SessionStore`.

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

## Why this model works well right now

This contract is intentionally simple:

- easy for the local frontend bridge to read
- easy to debug by opening files directly
- easy to evolve later into API responses
- easy to reuse later for `api_stream`

## Notes For Agents

- Treat `src/session_store.py` as the canonical durable-session boundary.
- Treat the snapshot shape and field meaning as more stable than the current
  file layout.
- Treat session files as the current default backend representation, not as the
  long-term contract itself.
- If you change a session field meaning, update:
  - this doc
  - `docs/contracts.md`
  - `docs/session-persistence-audit.md`
  - the affected frontend readers/tests
- If you change only file-backend mechanics, keep the public snapshot contract
  and store behavior tests stable unless the product behavior is intentionally
  changing.

## Important design point

A session is not exactly the same thing as playback.

The frontend keeps these concerns separate:

- setup state
- session state
- playback state

That separation made the app much more stable and should be preserved.

It is especially important now that playback source resolution, bridge
normalization, and session polling are all explicit layers with their own error
handling.

## Future evolution

Later, the same session model could be exposed through:

- a local host bridge
- a small FastAPI service
- SSE
- WebSockets

without changing the meaning of the session itself.
