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

This is the current bridge between detailed backend observability and
operator-safe frontend wording.

The session model is stricter now than in earlier iterations:

- invalid lifecycle transitions are rejected centrally
- malformed persisted artifacts degrade to safe empty/null snapshot fields
- append-only event logs are preserved even when later lines are malformed

The backend also resets any per-session rolling alert-rule state when a session starts or ends.

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
