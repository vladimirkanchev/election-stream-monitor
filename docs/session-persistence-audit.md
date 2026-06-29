# Session Persistence Audit

This audit captures the current session persistence surface before the
PostgreSQL session-store migration. Use it as the storage-contract inventory;
keep [session-model.md](./session-model.md) as the semantic reference.

## Current Artifacts

| Artifact | Current owner | Write shape | Read path | Migration note |
| --- | --- | --- | --- | --- |
| `session.json` | `session_io.write_session_metadata(...)` through `session_runner_lifecycle` and terminal updates | Overwrite JSON | `session_io.read_session_snapshot(...)`, `session_io.session_exists(...)` | Current "known session" marker; alert reads still depend on it. |
| `progress.json` | `session_io.write_session_progress(...)` through lifecycle, execution, and terminal helpers | Overwrite JSON | `session_io.read_session_snapshot(...)` | Preserve frontend fields and terminal `status_reason` / `status_detail` behavior. |
| `results.jsonl` | `session_io.append_result(...)` from `session_runner_execution.persist_bundle_events(...)` | Append-only JSONL | `session_io.read_session_snapshot(...)` | Keep append ordering and `latest_result` behavior stable. |
| `alerts.jsonl` | `session_alert_store.FileSessionAlertStore` through `session_io.append_alert(...)` | Append-only JSONL | Active alert-store seam and snapshot alert reads | Alerts already have file/PostgreSQL store selection, but PostgreSQL alert reads still check file-backed session existence. |
| `cancel_requested.json` | `session_io.request_session_cancel(...)` from `session_service.cancel_session(...)` and tests | Overwrite JSON marker | `session_io.is_session_cancel_requested(...)` in session execution and HTTP/HLS loader loops | Runtime control state, not historical data. Keep cancellation responsive. |
| `api_stream_seen_chunks.jsonl` | `session_io.append_api_stream_seen_chunk_key(...)` from `HttpHlsApiStreamLoader.persist_identity_key(...)` | Append-only JSONL | `session_io.read_api_stream_seen_chunk_keys(...)` during HTTP/HLS connect/restart | Live-stream replay/de-dup state; include in design, but do not treat as user-facing history. |
| `worker.log` | `session_service._spawn_session_worker(...)` | Append log file | Not part of the public snapshot; used for diagnostics | Keep file-backed for now unless a deliberate diagnostics surface is added. |
| API stream temp media files | `stream_loader_http_hls` materialization and cleanup helpers | Runtime files | Processed by detectors, then cleaned | Runtime artifact, not durable session data. Keep out of the first migration. |

## Current Ownership Map

- `src/session_service.py` owns start/read/cancel orchestration for FastAPI and CLI adapters.
- `src/session_runner.py` owns the worker-side execution flow and delegates persistence steps.
- `src/session_runner_lifecycle.py` owns pending and running metadata/progress transitions.
- `src/session_runner_execution.py` owns result/alert append calls and per-slice progress writes.
- `src/session_runner_terminal.py` owns terminal metadata/progress updates.
- `src/session_io.py` owns file-backed metadata, progress, results, cancel markers, live de-dup keys, and snapshot assembly.
- `src/session_alert_store.py` owns the alert persistence seam and default file-backed alert log.
- `src/session_alert_store_postgres.py` owns the opt-in PostgreSQL alert table, while session metadata still decides whether a session is known.

## Writer And Reader Map

| Persisted concern | Main writers | Main readers | Current coupling to preserve |
| --- | --- | --- | --- |
| Session metadata | `session_runner_lifecycle.initialize_pending_session(...)`, `session_runner_lifecycle.persist_pending_metadata(...)`, `session_runner_terminal.finalize_session_outcome(...)` | `session_io.read_session_snapshot(...)`, `session_service.read_session_snapshot_or_none(...)`, alert-store known-session checks | Public summary and current existence check. |
| Session progress | `session_runner_lifecycle.initialize_pending_session(...)`, `session_runner_lifecycle.start_running_session(...)`, `session_runner_execution.process_discovered_slices(...)`, `session_runner_execution.run_api_stream_session(...)`, `session_runner_terminal.finalize_session_outcome(...)` | `session_io.read_session_snapshot(...)`, FastAPI session reads, CLI session reads, frontend polling through the bridge | Progress is the latest snapshot, not a full history. Terminal reason/detail fields must survive storage changes. |
| Detector results | `session_runner_execution.persist_bundle_events(...)` through `session_io.append_result(...)` | `session_io.read_session_snapshot(...)`, frontend/debug snapshot users | Append order matters because `latest_result` is derived from the last valid row. |
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
- Snapshot reads are centralized in `session_io.read_session_snapshot(...)`;
  keep that shape stable while changing storage underneath it.

## Lifecycle Transition Map

| Step | Persisted transition | Main owner | Notes for PostgreSQL migration |
| --- | --- | --- | --- |
| Start request accepted | none yet in the parent process; `start_session(...)` returns pending metadata after spawning the worker | `session_service.start_session(...)` | The worker creates durable session state. Avoid parent-side durable claims unless reservation is deliberately designed. |
| Worker initialization | no session -> `pending` metadata and zero-count `pending` progress | `session_runner_lifecycle.initialize_pending_session(...)` | This creates the durable known-session marker and initial polling shape. |
| Source validation succeeds | `pending` metadata is rewritten with the validated input path | `session_runner_lifecycle.persist_pending_metadata(...)` | Preserve the normalized input path behavior so snapshots do not drift between parent request and worker execution. |
| Source validation or discovery fails | `pending` -> `failed` metadata and `failed` progress with `validation_failed` detail | `session_runner_terminal.finalize_validation_failure(...)` | Failed pending sessions must remain readable with a clear terminal reason. |
| Execution starts | `pending` -> `running`; progress is rewritten with the discovered total count | `session_runner_lifecycle.start_running_session(...)` | Local inputs know `total_count`; `api_stream` starts with `total_count = 0` and grows as chunks are accepted. |
| Slice/chunk processed | `running` remains `running`; append results/alerts; overwrite latest progress | `session_runner_execution.process_discovered_slices(...)` and `run_api_stream_session(...)` | Preserve result/alert order and latest-progress semantics. |
| Cancel requested | persistent cancel marker is written; route/CLI may return transient `cancelling` summary | `session_service.cancel_session(...)`, `session_io.request_session_cancel(...)` | `cancelling` is a control response, not the durable settled state today. Workers poll the marker and then persist `cancelled` or `failed`. |
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
| `alerts` | Raw alert rows read through the active alert-store seam | `[]` when the session is unknown or has no alerts | Snapshot alerts must agree with dedicated alert routes and MCP alert tools for the selected backend. |
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
- keep `worker.log`, cancel markers, replay keys, and temp media out of the
  public snapshot unless a deliberate new contract is added

## Durable Data Vs Runtime Artifacts

PostgreSQL migration should not treat every session-directory file alike. Some
artifacts are durable read-model data, some are runtime coordination signals,
and some are local diagnostics.

| Concern | Category | Current artifact | First migration decision |
| --- | --- | --- | --- |
| Session metadata | Durable session data | `session.json` | Move behind the session-store seam. This is the known-session marker and public summary. |
| Latest progress | Durable session data | `progress.json` | Move behind the session-store seam while keeping latest-snapshot semantics. |
| Detector results | Durable session event data | `results.jsonl` | Move or abstract with append ordering preserved. `latest_result` remains derived from this stream. |
| Alerts | Durable alert event data | `alerts.jsonl` or PostgreSQL alert store | Keep aligned with the existing alert-store seam. Remove file-backed session-existence coupling only after session metadata has a PostgreSQL-backed existence check. |
| Cancel request | Runtime control state with durability needs | `cancel_requested.json` | Do not expose in the public snapshot. Decide deliberately whether it remains file-backed for fast local polling or becomes a lightweight DB flag/channel. |
| API-stream replay keys | Runtime/restart coordination state | `api_stream_seen_chunks.jsonl` | Keep in scope for migration design because it affects reconnect/rerun correctness, but do not model it as user-facing session history. |
| Worker diagnostics | Local diagnostic artifact | `worker.log` | Keep file-backed for now. Move only if a separate diagnostics surface is designed. |
| API-stream temp media | Ephemeral processing artifact | temp `.ts` files under the stream temp directory | Keep filesystem-only. These are detector inputs during processing, not persisted session data. |

Practical rule: migrate the data needed to rebuild the current snapshot and
alert/session query surfaces first. Treat cancellation and replay keys as
runtime coordination contracts that need tests before storage changes. Leave
logs and temp media local unless diagnostics or artifact retention become
explicit product features.

## Tests That Encode File Behavior

The suite protects two contracts: file-specific fallback behavior and
storage-independent public behavior. Keep both during the migration.

| Test area | Current examples | What the tests encode | Migration use |
| --- | --- | --- | --- |
| File-backed session helpers | `tests/test_session_io.py` | JSON/JSONL writes, malformed-file tolerance, empty snapshot shape, result ordering, `latest_result`, cancel marker files, worker-log path | Keep for the default file backend and any compatibility fallback. Add store-agnostic equivalents for the new session-store seam. |
| File-backed alert read behavior | `tests/test_alert_query_service_read.py`, `tests/test_session_alert_store.py` | Known-session checks through `session.json`, missing `alerts.jsonl` as empty alerts, corrupt-line tolerance | Keep while file alerts remain supported. Revisit known-session checks when PostgreSQL session metadata can answer existence. |
| PostgreSQL alert parity | `tests/test_session_alert_store_postgres.py`, `tests/test_session_alert_store_parity.py`, runtime alert route tests | Alert rows preserve fields, order, timestamp string shape, and file/PostgreSQL parity | Use as the pattern for the session-store migration: same public contract, different backend. |
| Shared session service | `tests/test_session_service_read_cancel.py`, `tests/test_session_service.py` | Missing snapshot -> `None`, cancel allowed/rejected states, transient `cancelling` summary, worker-log exclusion from public metadata | Expand around a session-store seam so service behavior does not depend on raw files. |
| FastAPI session boundary | `tests/test_api_boundary_sessions_read.py`, `tests/test_api_boundary_sessions_start.py`, `tests/test_api_boundary_sessions_cancel.py`, `tests/test_api_boundary_contracts.py` | Stable route payloads, route-level `404`, validation errors, snapshot shape, malformed payload fail-closed behavior | Treat as high-value migration guards because the frontend depends on these shapes rather than storage files. |
| Runner and live-stream lifecycle | `tests/test_session_runner_lifecycle.py`, `tests/test_session_runner_terminal.py`, `tests/test_session_runner_execution*.py`, `tests/test_session_runner_api_stream*.py` | Pending/running/terminal writes, progress status reasons, cancellation timing, API-stream temp cleanup, de-dup state | Keep broad lifecycle assertions. Split any direct file assumptions from behavior that should work through both stores. |
| HTTP/HLS de-dup and cancel mechanics | `tests/test_stream_loader_http_hls*.py` | `api_stream` replay-key persistence and cooperative cancellation checks | Keep as runtime-coordination coverage. If replay keys or cancel markers move to DB, add focused parity tests before deleting file assertions. |

Test migration rule: do not delete direct file tests when PostgreSQL arrives.
Add the storage seam and store-agnostic contract tests first, then keep file
tests scoped to the file backend. Public API/service tests should not assert raw
filenames such as `session.json` or `results.jsonl`; low-level file backend
tests may.

## Docs That Mention Session Persistence

Most docs match the current stage: session metadata, progress, and results are
file-backed today; alerts are file-backed by default with PostgreSQL opt-in. The
risk is future drift once a session-store backend exists.

| Doc area | Current claim style | Status now | Migration action |
| --- | --- | --- | --- |
| Root `README.md` | User-facing current state: session files stay file-backed; PostgreSQL is optional for alerts | Accurate for the current release stage | Update when PostgreSQL session storage becomes available, but keep README high-level and avoid schema/runbook detail. |
| `docs/session-model.md` | Canonical session semantics plus current file names and JSON/JSONL behavior | Accurate, intentionally file-specific | Keep semantic sections stable; move file-specific wording under "current file backend" once a session-store seam lands. |
| `docs/contracts.md` | Snapshot contract and route behavior, with some file-backed implementation notes | Mostly storage-independent, with a few file examples | Preserve as the public contract reference. Replace implementation-specific "missing `session.json`" wording when known-session checks move behind a store. |
| `docs/data-models.md` and `docs/fastapi-boundary.md` | Snapshot/API shape rather than storage implementation | Low drift risk | Keep focused on payload shape. Avoid adding PostgreSQL implementation details here unless the API changes. |
| `docs/architecture.md` | Current runtime architecture: file-backed session state plus opt-in PostgreSQL alerts | Accurate but implementation-oriented | Update alongside the storage seam so architecture reflects file backend plus PostgreSQL backend rather than only files. |
| `docs/testing-and-validation.md` | Current lanes and test ownership, including file-backed session tests and live PostgreSQL alert confidence | Accurate but will need the largest validation update | Add session-store parity, backend-mode, and optional live PostgreSQL session-store commands when implementation begins. |
| `docs/README.md` | Navigation to session model, contracts, and this audit | Aligned | Keep this audit linked while the migration is active. |

Docs migration rule: keep docs honest about the current default, but avoid
timeless phrasing that says "sessions are files" when the real contract is the
snapshot/read model. During implementation, update docs in this order:
`session-persistence-audit.md`, `session-model.md`, `contracts.md`,
`architecture.md`, then `README.md` only for user-visible behavior.

## Migration Boundary Notes

Use this boundary as the guide for the first PostgreSQL session-store branch.
The goal is storage parity, not a new session product surface.

| Area | First migration decision | Reason |
| --- | --- | --- |
| Session metadata and existence | In scope | This is the current known-session marker and the base for route-level `404` behavior. |
| Latest progress snapshot | In scope | Frontend polling depends on the latest progress shape, counts, status, and terminal reason/detail fields. |
| Detector results | In scope | Snapshot `results` and derived `latest_result` must preserve append order. |
| Snapshot assembly | In scope | Readers should get the same five top-level keys regardless of backend. |
| Store selection | In scope | Keep file-backed sessions as the default until PostgreSQL has parity tests and operational confidence. |
| Alert/session existence coupling | In scope as a design seam | PostgreSQL alert reads still need a backend-neutral known-session check. |
| Cancel requests | Deliberate follow-up or scoped opt-in | Live control state. Move it only if polling stays cheap and failure behavior is tested. |
| API-stream replay keys | Deliberate follow-up or tightly scoped opt-in | Replay keys affect reconnect correctness, but they are runtime coordination rather than user-facing history. |
| Worker logs | Out of scope | `worker.log` is local diagnostics, not public session state. |
| API-stream temp media | Out of scope | Temporary `.ts` files are processing artifacts and should stay filesystem-only. |
| Frontend/API payload shape changes | Out of scope | Storage migration should not change the public session contract. |
| Making PostgreSQL the default | Out of scope for the first pass | Switch defaults only after parity, rollback, and operations are boring. |

Recommended implementation order:

1. Define a small session-store seam around metadata, progress, results, and snapshot reads.
2. Wrap the current file behavior behind that seam without changing defaults.
3. Add store-agnostic contract tests for snapshot shape, missing-session behavior, ordering, and terminal progress.
4. Add the PostgreSQL implementation and schema as opt-in configuration.
5. Add file/PostgreSQL parity tests and focused FastAPI boundary tests.
6. Revisit cancel markers, replay keys, and alert known-session checks after the durable read model is stable.

Hidden obstacles to keep visible:

- The parent FastAPI process returns pending metadata before the detached worker creates the durable session record.
- The detached worker and FastAPI process must resolve the same backend configuration.
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
  leave file-backed wording in public contract docs after the store seam owns it.
