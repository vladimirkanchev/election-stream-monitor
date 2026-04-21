# Session Model

This document explains the current session contract between the Python backend
and the frontend.

It is meant for contributors and coding agents working on the session layer,
not as end-user documentation.

Use this doc for persisted session meaning and lifecycle semantics.
Do not use it as the main architecture overview or as the complete bridge
payload catalog; see [architecture.md](./architecture.md) and
[contracts.md](./contracts.md) for those.

## At a glance

- sessions are the persisted contract between backend and frontend
- persistence is file-backed today, but the session meaning should survive
  later storage changes
- monitoring session state and playback state are related but intentionally
  separate

## Why sessions exist here

The frontend and backend do not talk through a full web service yet.

Instead, the backend writes session data to disk and the frontend reads it
through the local bridge. That keeps the current project simple while still
giving a clear session lifecycle and a stable read model.

## Session files

Each session currently writes:

- `session.json`
- `progress.json`
- `alerts.jsonl`
- `results.jsonl`
- `api_stream_seen_chunks.jsonl` for `api_stream` de-duplication state

These files live under the configured session output folder in `data/sessions/`.

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

Behavior depends a bit on mode:

- for `video_segments`, progress moves naturally segment by segment
- for `video_files`, one `.mp4` is expanded into one-second-like analysis slices
- for `api_stream`, progress moves accepted live slices/chunks and may stay
  open-ended while playback is still live

So `current_item` and `processed_count` for `video_files` are now slice-based,
not whole-file based.

### `alerts.jsonl`

Append-only alert events for the session.

These are the alerts shown in the frontend.

### `results.jsonl`

Append-only detector result events for the session.

These are the structured outputs of detectors before or alongside alert interpretation.

## Persistence contract

The current persistence layer is intentionally simple, but it still has a
useful contract.

### Session-scoped files

These files belong to one session directory:

- `session.json`
- `progress.json`
- `alerts.jsonl`
- `results.jsonl`
- optional `api_stream_seen_chunks.jsonl`

That means the frontend and local tooling should treat them as the canonical
state for one monitoring run.

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

This is the current bridge between detailed backend observability and
operator-safe frontend wording.

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

At the backend persistence-helper layer, missing session snapshot reads still
degrade to the stable empty snapshot shape. Structured missing-session failures
are introduced later at the API boundary when that empty snapshot means
"session not found" for a route-level request.

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

- Treat session files as the canonical persisted contract, even if helper code
  changes around them.
- If you change a session field meaning, update:
  - this doc
  - `docs/contracts.md`
  - the affected frontend readers/tests

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
