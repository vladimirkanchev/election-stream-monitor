# Docs Index

This folder is the internal reference set for contributors, reviewers, and
people using AI-assisted tools for coding and development. Use it as the
intent layer for the current repo state, not as end-user documentation.

## Best First Reads

If you are new to the repo, read these in order:

1. [../NEXT_SESSION.md](../NEXT_SESSION.md) if you are returning after a break
2. [architecture.md](./architecture.md)
3. [contracts.md](./contracts.md)
4. [session-model.md](./session-model.md)
5. then the task-specific doc for the subsystem you want to change

## Best Entry Points For Coding Agents

Use this shortcut map before editing code:

- changing session snapshot or polling behavior:
  - [session-model.md](./session-model.md)
  - [contracts.md](./contracts.md)
  - [architecture.md](./architecture.md)
- changing frontend bridge normalization or UI transport handling:
  - [frontend-architecture.md](./frontend-architecture.md)
  - [contracts.md](./contracts.md)
  - [testing-and-validation.md](./testing-and-validation.md)
- changing FastAPI endpoints or response semantics:
  - [fastapi-boundary.md](./fastapi-boundary.md)
  - [architecture-decision-fastapi.md](./architecture-decision-fastapi.md)
  - [contracts.md](./contracts.md)
- adding a detector:
  - [adding-an-analyzer.md](./adding-an-analyzer.md)
- adding an alert rule:
  - [adding-an-alert-rule.md](./adding-an-alert-rule.md)

## Current High-Signal Code Areas

If you want the shortest path into the current repo shape, start with these
module families and the matching tests:

- session lifecycle and persistence:
  - `src/session_service.py`
  - `src/api/routers/sessions.py`
  - `src/session_cli.py`
  - `src/session_runner.py`
  - `src/session_runner_lifecycle.py`
  - `src/session_runner_execution.py`
  - `src/session_runner_terminal.py`
  - `src/session_runner_discovery.py`
  - `src/session_runner_progress.py`
  - `tests/test_session_service.py`
  - `tests/test_api_boundary_sessions.py`
  - `tests/test_session_cli_tooling.py`
  - `tests/test_session_runner_lifecycle.py`
  - `tests/test_session_runner_execution.py`
  - `tests/test_session_runner_terminal.py`
  - `tests/test_session_runner_local.py`
  - `tests/test_session_runner_api_stream_completion.py`
  - `tests/test_session_runner_api_stream_cancellation.py`
  - `tests/test_session_runner_api_stream_failures.py`
  - `tests/test_session_runner_api_stream_progress.py`
  - `tests/test_session_runner_api_stream_http_hls.py`
  - read the session-service files first, then the runner files, if you want
    the shortest path into the current session lifecycle split
- live `api_stream` loading:
  - `src/stream_loader.py`
  - `src/stream_loader_contracts.py`
  - `src/stream_loader_http_hls.py`
  - `src/stream_loader_fakes.py`
  - `tests/test_stream_loader_contracts.py`
  - `tests/test_stream_loader_http_hls_core_playlist.py`
  - `tests/test_stream_loader_http_hls_core_progression.py`
  - `tests/test_stream_loader_http_hls_core_provider.py`
  - `tests/test_stream_loader_http_hls_reconnect.py`
  - `tests/test_stream_loader_http_hls_limits.py`
- Electron/FastAPI desktop runtime:
  - `frontend/electron/main.mjs`
  - `frontend/electron/fastApiStartupOrchestrator.mjs`
  - `frontend/electron/fastApiRuntimePolicy.mjs`
  - `frontend/electron/fastApiProcessManager.mjs`
  - `frontend/electron/bridgeHandlerRegistry.mjs`
  - `frontend/electron/localMediaRequestPolicy.mjs`
  - `frontend/electron/localMediaResponses.mjs`
- frontend bridge normalization:
  - `frontend/src/bridge/contract.ts`
  - `frontend/src/bridge/contractErrors.ts`
  - `frontend/src/bridge/contractDetectors.ts`
  - `frontend/src/bridge/contractSessionSnapshot.ts`
  - `frontend/src/bridge/transport.ts`
  - `frontend/src/bridge/contract.success.test.ts`
  - `frontend/src/bridge/contract.errors.test.ts`
  - `frontend/src/bridge/contract.session-snapshot.test.ts`

## Current Stable Contracts

At the current stage, treat these as stable unless you deliberately intend a
coordinated contract change:

- session snapshot shape
- frontend bridge normalization shape
- FastAPI structured error payload shape
- detector catalog shape

## Document Ownership

Use each doc for one main question:

- [architecture.md](./architecture.md)
  - system responsibilities
  - runtime boundaries
  - where a change belongs
- [contracts.md](./contracts.md)
  - stable payloads and bridge contracts
  - `api_stream` trust, failure, and playback contracts
- [session-model.md](./session-model.md)
  - persisted session files
  - lifecycle meaning
  - progress semantics
- [data-models.md](./data-models.md)
  - compact field guide for detector, alert, and session shapes
- [frontend-architecture.md](./frontend-architecture.md)
  - React/Electron split
  - playback state
  - frontend transport boundary
- [fastapi-boundary.md](./fastapi-boundary.md)
  - what a future FastAPI layer should own
  - what should stay local/runtime-specific
- [testing-and-validation.md](./testing-and-validation.md)
  - routine verification commands
  - CI scope
  - manual vs automated validation
- [api-stream-local-validation.md](./api-stream-local-validation.md)
  - repeatable local `api_stream` trial workflow
  - expected status, logs, and cleanup
- [reviewer-guide.md](./reviewer-guide.md)
  - fastest review order
  - best feedback targets for the current project stage
- [release-versioning.md](./release-versioning.md)
  - `0.x` release expectations

## Extension Guides

Use these when changing the detector/rule surface:

- [adding-an-analyzer.md](./adding-an-analyzer.md)
- [adding-an-alert-rule.md](./adding-an-alert-rule.md)
- [detector-template.md](./detector-template.md)

## Visual References

- [runtime-flow.svg](./runtime-flow.svg)
- [plugin-structure.svg](./plugin-structure.svg)
- [frontend-overview.svg](./frontend-overview.svg)
- [frontend-flow.svg](./frontend-flow.svg)
- [detector-and-alert-extension-flow.svg](./detector-and-alert-extension-flow.svg)

## Task-Based Reading Paths

If you are working on:

- transport / streaming
  - [architecture.md](./architecture.md)
  - [contracts.md](./contracts.md)
  - [testing-and-validation.md](./testing-and-validation.md)
- session lifecycle / persistence
  - [architecture.md](./architecture.md)
  - [session-model.md](./session-model.md)
  - [contracts.md](./contracts.md)
  - [testing-and-validation.md](./testing-and-validation.md)
- frontend playback / monitoring UX
  - [frontend-architecture.md](./frontend-architecture.md)
  - [contracts.md](./contracts.md)
  - [testing-and-validation.md](./testing-and-validation.md)
- Electron/FastAPI desktop runtime
  - [frontend-architecture.md](./frontend-architecture.md)
  - [architecture.md](./architecture.md)
  - [testing-and-validation.md](./testing-and-validation.md)
- detector or alert extension
  - [adding-an-analyzer.md](./adding-an-analyzer.md)
  - [adding-an-alert-rule.md](./adding-an-alert-rule.md)
  - [data-models.md](./data-models.md)
- review / onboarding
  - [reviewer-guide.md](./reviewer-guide.md)
  - [architecture.md](./architecture.md)
  - [contracts.md](./contracts.md)

## Update Rules

- Prefer code and tests as the final source of truth when a doc drifts.
- If you change a boundary, lifecycle meaning, or payload shape, update the
  matching doc in the same change.
- Avoid copying large blocks of guidance across files. Link to the owning doc
  instead.
