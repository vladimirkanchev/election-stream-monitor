# Architecture

This document describes the current runtime architecture of Election Stream Monitor.

It is written for contributors and people using AI-assisted tools for coding
and development who need to reason about the actual code paths in the
repository today, not the aspirational future design.

Use this doc for responsibilities and change placement.
Do not use it as the source of truth for field-level payloads or exact
persisted-session semantics; see [contracts.md](./contracts.md) and
[session-model.md](./session-model.md) for those.
Use [testing-and-validation.md](./testing-and-validation.md) for validation
commands and [ci-maintainer-guide.md](./ci-maintainer-guide.md) for CI
enforcement policy.

This is a production-runtime document.
It intentionally does not describe detector-lab experimental algorithms as if
they were part of the supported runtime detector or alert surface. For that
workbench, use [detector_lab/README.md](../detector_lab/README.md).

## At a glance

- project stage: advanced prototype / pre-pilot
- architecture shape: local-first modular monolith
- backend: local FastAPI boundary plus shared Python session services and a
  detached session worker
- frontend: React/Electron setup, playback, alert inspection
- live support: bounded HTTP/HLS `.m3u8` analysis with Electron-side HLS
  playback proxying; direct remote `.mp4` remains a source-validation and
  playback path, not a remote-analysis loader input

## Best use of this doc

Use this document when you need to answer:

- where a responsibility lives
- which layer should change for a given feature or bug
- whether something belongs to transport, session lifecycle, detector logic,
  alert policy, playback, or persistence

## Detailed architecture

The detailed view shows process boundaries, monitoring writes, persisted read
paths, and the read-only MCP surface. Exact payload shapes and lifecycle
semantics remain owned by [contracts.md](./contracts.md) and
[session-model.md](./session-model.md).

![Detailed Election Stream Monitor architecture showing Electron, FastAPI, the detached monitoring worker, persistence, shared alert reads, and read-only MCP](./assets/architecture-detailed.png)

[Open the detailed architecture diagram at full size.](./assets/architecture-detailed.png)

The following focused diagrams provide complementary runtime-flow and
extension views.

![Runtime flow](./runtime-flow.svg)

![Plugin structure](./plugin-structure.svg)

## Main runtime flow

1. The frontend chooses:
   - source mode
   - source path
   - selected detectors
2. The React app calls the normalized bridge surface exposed through
   `window.electionBridge`.
3. Electron owns local runtime startup/readiness, talks to the local FastAPI
   boundary for normal operation, and returns explicit success/error envelopes
   to the frontend transport layer.
4. [`src/api/routers/sessions.py`](../src/api/routers/sessions.py) adapts HTTP
   session requests into the shared application service in
   [`src/session_service.py`](../src/session_service.py).
5. [`src/session_service.py`](../src/session_service.py) validates start
   requests, spawns the detached worker process, and keeps start/read/cancel
   logic transport-agnostic.
6. [`src/session_runner.py`](../src/session_runner.py) coordinates the actual
   monitoring run inside that worker and delegates local discovery/progress
   shaping to its focused helper modules.
7. [`src/detectors/registry.py`](../src/detectors/registry.py) decides which
   detectors are enabled for that mode and keeps the explicit detector runtime
   contract in one place on purpose:
   - detector ids
   - detector callable wiring
   - supported modes and suffixes
   - store targets
   - frontend catalog metadata
   - default alert-rule linkage
   The older
   [`src/analyzer_registry.py`](../src/analyzer_registry.py) file now exists as
   a thin compatibility wrapper for older imports. Future plugin metadata can
   build on this explicit registration contract without replacing it with
   dynamic discovery yet.
8. [`src/detectors/`](../src/detectors) extracts detector facts and returns
   typed detector rows through focused detector modules.
9. [`src/processor.py`](../src/processor.py) normalizes detector output into
   the runtime row contract.
10. [`src/alert_rules.py`](../src/alert_rules.py) evaluates production alert
    policy on those runtime rows.
11. The worker persists session metadata, latest progress, and ordered results
    through the current default `SessionStore`, which still writes under
    `data/sessions/` for this stage, including backend-owned diagnostics such
    as `worker.log`.
12. The frontend polls the session snapshot and updates playback and alerts.

Session and alert persistence are file-backed by default. PostgreSQL requires
explicit backend selection and never silently replaces a failed bootstrap with
file storage. The [session persistence audit](./session-persistence-audit.md)
owns rollout evidence and readiness decisions.

FastAPI is the desktop application's HTTP boundary. MCP is a separate,
read-only local `stdio` adapter over shared alert services; it does not inherit
FastAPI authentication. Detailed HTTP and MCP trust rules belong in
[fastapi-boundary.md](./fastapi-boundary.md) and [mcp-server.md](./mcp-server.md).

## Legacy Tooling

[`src/main.py`](../src/main.py) is a legacy local developer harness for the
older file-based path only.

- It is non-canonical and not part of the supported session/runtime
  architecture described above.
- It is kept temporarily for narrow local debugging/smoke use.
- It is slated for removal once the accepted replacement is focused pytest
  coverage for the older local-file path.

## Input modes

Current modes:

- `video_segments`
- `video_files`
- `api_stream`

These modes describe how the source arrives, not what the detector does.

Right now the behavior is:

- `video_segments`
  - preferred near-live path
  - `.ts` files are processed one by one
- `video_files`
  - `.mp4` inputs are expanded into roughly one-second analysis slices
  - this keeps detector and alert timing aligned with segment-style processing
  - image files are processed one by one
- `api_stream`
  - accepts direct `.m3u8` or `.mp4` URLs
  - backend loader owns live playlist polling, segment download, reconnect
    behavior, and temp-file lifecycle
  - Electron playback uses a local HLS proxy for remote HLS sources when the
    renderer would otherwise hit CORS limits

## Core backend modules

### Detector contract

[`src/analyzer_contract.py`](../src/analyzer_contract.py)

Defines:

- detector result base shape
- detector callable contract
- registration metadata
- analysis slice metadata

Detectors return typed, backend-owned facts rather than frontend wording or
alert decisions. The processor serializes flat rows only at persistence and
event boundaries; alert rules own interpretation, suppression, and re-entry.

The supported production surface is `video_metrics` and `video_blur` with
their explicit default rules. Experimental policies in `detector_lab/` are not
runtime contracts. Use [adding-an-analyzer.md](./adding-an-analyzer.md) for
promotion requirements and [detector-validation-ownership.md](./detector-validation-ownership.md)
for confidence ownership.

### Detector registry

[`src/detectors/registry.py`](../src/detectors/registry.py)

The registry defines:

- detector id
- callable
- supported modes
- supported suffixes
- output store
- frontend-facing metadata
- default bundled alert-rule linkage
- explicit detector ownership (`built_in` vs `user`)

This is the main extension point for new detectors.

### Detector implementation

[`src/detectors/`](../src/detectors)

Detectors are expected to:

- process one file or one time slice
- return typed detector rows with stable serialization
- avoid direct persistence
- avoid frontend concerns

Current examples:

- video black-screen metrics
- rolling blur metrics with detector-side motion summaries

### Alert rules

[`src/alert_rules.py`](../src/alert_rules.py)

This layer converts detector output into alert events and owns the small
rolling state needed for the current black-screen and blur policies.

That separation is intentional:

- detectors compute facts
- rules decide whether those facts matter enough to alert

Current rule shape:

- rule metadata stays explicit through `AlertRule`
- rule inputs are normalized into `RuntimeResultRow`
- detector-specific evaluators stay narrow and fact-oriented
- rolling state is keyed by session id, detector id, and source group through
  a small `RuleStateStore`
- rule decision output is kept separate from row-facing annotation metadata
- rolling state is reset at session boundaries by the runner

### Processor

[`src/processor.py`](../src/processor.py)

Responsibilities:

- retrieve enabled detectors from the registry
- run matching detectors
- write results to the correct store
- evaluate alert rules
- isolate detector failures where possible
- treat persistence failures as session-fatal

### Session runner

[`src/session_runner.py`](../src/session_runner.py),
[`src/session_runner_lifecycle.py`](../src/session_runner_lifecycle.py),
[`src/session_runner_execution.py`](../src/session_runner_execution.py),
[`src/session_runner_terminal.py`](../src/session_runner_terminal.py),
[`src/session_runner_discovery.py`](../src/session_runner_discovery.py),
[`src/session_runner_progress.py`](../src/session_runner_progress.py)

Responsibilities:

- `src/session_runner.py` coordinates source validation, execution selection,
  rule-state reset, and final cleanup.
- Lifecycle, execution, terminal persistence, discovery, and progress remain
  in the corresponding focused `session_runner_*` modules.
- The runner persists progress, results, and alerts incrementally and sends
  `api_stream` work to the dedicated loader rather than local discovery.

### Session service

[`src/session_service.py`](../src/session_service.py),
[`src/api/routers/sessions.py`](../src/api/routers/sessions.py),
[`src/session_cli.py`](../src/session_cli.py)

Responsibilities:

- keep `src/session_service.py` as the shared start/read/cancel application seam
- keep detached worker diagnostics session-scoped under
  `data/sessions/<session_id>/worker.log` without making them a frontend/API
  contract yet
- keep `src/api/routers/sessions.py` as the FastAPI adapter for the canonical desktop runtime path
- keep `src/session_cli.py` as the tooling/debugging adapter over the same shared service
- keep `run-session` in `src/session_cli.py` as the internal worker command used by the detached session process

Reading order for this module family:

1. `src/session_service.py`
2. `src/api/routers/sessions.py`
3. `src/session_cli.py`

That order is the shortest path for understanding where session lifecycle
request ownership ends and actual session execution begins.

### API stream loader

[`src/stream_loader.py`](../src/stream_loader.py),
[`src/stream_loader_contracts.py`](../src/stream_loader_contracts.py),
[`src/stream_loader_http_hls.py`](../src/stream_loader_http_hls.py),
[`src/stream_loader_fakes.py`](../src/stream_loader_fakes.py)

Responsibilities:

- `src/stream_loader.py` is the thin public facade and loader selector.
- Contract builders and identity helpers stay separate from HTTP/HLS transport.
- Focused HTTP/HLS modules own orchestration, playlist parsing, fetching,
  materialization, and replay/window policy.
- Deterministic seam loaders remain separate from the concrete transport.

This keeps live transport behavior explicit and separate from session
orchestration in the runner.

### Session persistence

[`src/session_store.py`](../src/session_store.py),
[`src/session_store_runtime.py`](../src/session_store_runtime.py),
[`src/session_store_runtime_config.py`](../src/session_store_runtime_config.py),
[`src/session_store_file.py`](../src/session_store_file.py),
[`src/session_io.py`](../src/session_io.py)

Responsibilities:

- keep `src/session_store.py` as the durable session contract
- keep `src/session_store_runtime.py` and
  `src/session_store_runtime_config.py` as the centralized default-store and
  rollback configuration layer
- keep `src/session_store_file.py` as the current file-backed backend
- keep `src/session_io.py` as the concrete file helper layer and snapshot
  assembly path behind that backend

The current design still persists sessions through local files at runtime, but
the public read contract is now the session snapshot and the `SessionStore`
boundary rather than raw filenames alone. Snapshot assembly remains explicit
and defensive against missing or malformed artifacts.

### Stores

[`src/stores.py`](../src/stores.py)

Persistence is still simple:

- CSV-backed buffered stores
- one store instance per result schema family

These are stores for detector result metrics, not stores for alerts.

## Frontend/backend boundary

The frontend is local-first and talks to Python through Electron.

Important parts:


- [`frontend/electron/main.mjs`](../frontend/electron/main.mjs) composes local
  application lifecycle and delegates backend startup and playback transport.
- `frontend/electron/fastApi*` modules own process startup, readiness, and
  unavailable-runtime policy.
- `frontend/electron/bridge*` modules expose IPC handlers and normalize stable
  success/error envelopes.
- Playback policy and local-media responders keep renderer-safe URLs, file
  responses, and remote HLS proxying outside the renderer.
- `frontend/src/hooks/` owns setup, session, and playback state; the bridge
  contract modules normalize transport data before it reaches that state.

This split is important because playback state and backend session state are related, but not the same thing.

## Where to change things

If you are deciding where a change belongs:

- detector math / extracted metrics
  - `src/detectors/`
- alert thresholds / re-alert semantics / operator wording from detector output
  - `src/alert_rules.py`
- session lifecycle / completion / cancel / failure behavior
  - `src/session_runner.py` and the focused `session_runner_*` modules
- `api_stream` transport, reconnect, playlist parsing, temp files
  - `src/stream_loader.py` and focused `stream_loader_*` modules
- renderer playback routing and HLS proxy behavior
  - `frontend/electron/` and `frontend/src/components/VideoPlayerPanel.tsx`

## Current design decisions

The project currently prefers:

- explicit detector registration over dynamic plugin loading
- readable rule definitions over hidden heuristics
- flat result rows over deeply nested payloads
- simple local persistence over service infrastructure
- composition over heavy OOP
- explicit trust-boundary validation over permissive source handling
- one explicit preload bridge surface over ad-hoc renderer capabilities

## Failure policy

The current `api_stream` runtime intentionally distinguishes four operator-level
outcomes:

- `retry`
  - transient upstream or polling failure where the loader should keep going
- `stop`
  - bounded or graceful terminal state such as `ENDLIST` or idle-poll stop
- `fail`
  - explicit terminal runtime failure such as reconnect-budget exhaustion,
    runtime-limit exhaustion, malformed unsupported source, or temp-budget
    exhaustion
- `cancel`
  - explicit user-requested shutdown

The important design choice is that low-level transport errors stay inside the
loader seam, while session persistence and frontend wording consume a smaller,
stable set of outcomes.

That keeps three layers aligned:

- backend logs keep detailed failure reasons
- persisted progress snapshots keep machine-readable `status_reason` and
  `status_detail`
- frontend UI maps those details to operator-safe wording without exposing raw
  transport noise

## FastAPI boundary

A first FastAPI boundary now exists for the stable backend/session contract.

It currently provides:

- `GET /health`
- `GET /detectors`
- `POST /sessions`
- `GET /sessions/{session_id}`
- `POST /sessions/{session_id}/cancel`
- `POST /playback/resolve`

The current FastAPI layer is the normal runtime backend boundary for the
desktop app. Electron now owns local FastAPI startup/readiness and uses the
API for normal session and playback-resolution bridge operations.

The Python CLI remains available as a tooling/debugging seam rather than the
normal runtime bridge.

Use these docs together:

- [fastapi-boundary.md](./fastapi-boundary.md)
  - practical run/use/current-status guide
- [architecture-decision-fastapi.md](./architecture-decision-fastapi.md)
  - ownership split and migration order

Current ownership split:

- FastAPI owns:
  - stable monitoring/session backend behavior
  - structured API error payloads
  - session snapshot reads
  - validated playback-resolution contract
- local/runtime-specific layers keep owning:
  - Electron-only `local-media://` serving
  - remote HLS proxying for renderer playback
  - local file trust rules
  - FFmpeg/FFprobe invocation
  - temp-file materialization and cleanup
  - local process-spawn details for detached session execution and backend
    startup

That split is intentional because FastAPI should expose the stable monitoring
contract, not absorb every desktop/runtime concern that currently exists only
to support the local Electron app.

If an API or bridge payload changes, update its schemas, bridge normalizers,
boundary tests, and [contracts.md](./contracts.md) together. Use
[testing-and-validation.md](./testing-and-validation.md) to select the
smallest honest validation lane. Operator-facing session and alert presentation
belongs in the renderer components and presenters, not the backend boundary.
