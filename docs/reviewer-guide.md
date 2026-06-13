# Reviewer Guide

This document is for engineers who want to review the repo efficiently without
reading every file first.

If you only care about one subsystem, skip straight to that section.

For branch workflow and PR shape, use this sequence alongside the review:

1. [branch-purpose-template.md](./branch-purpose-template.md)
2. [`../.github/pull_request_template.md`](../.github/pull_request_template.md)
3. [merge-readiness-checklist.md](./merge-readiness-checklist.md)

Before going deep on code, make sure the PR notes state:

- the validation commands that were run
- fixture/environment impact
- docs impact
- why dependency metadata changes belong, if `pyproject.toml` or `uv.lock` changed
- whether the branch used focused lanes, `test-fast`, or `ci-local` for the right reason

The pull-request CI also fails early if those validation, fixture/environment,
or docs sections are left effectively blank.

For commit history, prefer readable messages that describe the actual change
and keep one clear theme per commit when practical.

## Best Review Order

1. Read [architecture.md](./architecture.md)
2. Read [contracts.md](./contracts.md)
3. Read [fastapi-boundary.md](./fastapi-boundary.md)
4. Then inspect the implementation areas below

## Best Files To Review First

### Transport / Streaming

Start here if you care most about media ingest, HLS behavior, and trust-policy
boundaries.

- [`src/stream_loader.py`](../src/stream_loader.py)
- [`src/stream_loader_contracts.py`](../src/stream_loader_contracts.py)
- [`src/stream_loader_http_hls.py`](../src/stream_loader_http_hls.py)
- [`src/stream_loader_fakes.py`](../src/stream_loader_fakes.py)
- [`src/source_validation.py`](../src/source_validation.py)
- [`frontend/electron/hlsProxy.mjs`](../frontend/electron/hlsProxy.mjs)
- [`frontend/electron/main.mjs`](../frontend/electron/main.mjs)
- [`frontend/electron/fastApiStartupOrchestrator.mjs`](../frontend/electron/fastApiStartupOrchestrator.mjs)
- [`frontend/electron/fastApiRuntimePolicy.mjs`](../frontend/electron/fastApiRuntimePolicy.mjs)
- [`frontend/electron/localMediaRequestPolicy.mjs`](../frontend/electron/localMediaRequestPolicy.mjs)
- [`frontend/electron/localMediaResponses.mjs`](../frontend/electron/localMediaResponses.mjs)

Key review themes:

- `main.mjs` should read mostly as composition/wiring, not backend-policy detail
- startup orchestration vs low-level process/runtime policy ownership
- request classification vs response generation on `local-media://`
- source validation and trust policy
- reconnect and failure policy
- temp-file lifecycle
- remote HLS proxy behavior
- provider-specific failure handling

### Backend Session Runner

Start here if you care most about monitoring lifecycle, progress semantics, and
persistence.

- [`src/session_runner.py`](../src/session_runner.py)
- [`src/session_runner_discovery.py`](../src/session_runner_discovery.py)
- [`src/session_runner_progress.py`](../src/session_runner_progress.py)
- [`src/session_io.py`](../src/session_io.py)
- [`src/session_models.py`](../src/session_models.py)
- [`src/processor.py`](../src/processor.py)

Key review themes:

- session start/stop/cancel/fail behavior
- local discovery vs lifecycle ownership
- progress snapshots and persisted state
- dedup/replay handling
- detector/rule orchestration

### Frontend Playback / Status UX

Start here if you care most about operator clarity and runtime diagnostics.

- [`frontend/src/components/VideoPlayerPanel.tsx`](../frontend/src/components/VideoPlayerPanel.tsx)
- [`frontend/src/components/SessionStatusPanel.tsx`](../frontend/src/components/SessionStatusPanel.tsx)
- [`frontend/src/hooks/usePlaybackSource.ts`](../frontend/src/hooks/usePlaybackSource.ts)
- [`frontend/src/hooks/useMonitoringSession.ts`](../frontend/src/hooks/useMonitoringSession.ts)
- [`frontend/electron/playbackSourcePolicy.mjs`](../frontend/electron/playbackSourcePolicy.mjs)
- [`frontend/src/bridge/contract.ts`](../frontend/src/bridge/contract.ts)
- [`frontend/src/bridge/contractErrors.ts`](../frontend/src/bridge/contractErrors.ts)
- [`frontend/src/bridge/transport.ts`](../frontend/src/bridge/transport.ts)

Key review themes:

- playback failure messaging
- separation of playback vs monitoring failure states
- operator diagnostics during retrying and terminal failures
- frontend/backend contract alignment
- bridge normalization vs transport fallback ownership

## Current Honest Project State

The project is best understood as:

- local-first AI video monitoring system
- advanced prototype moving toward pre-pilot
- stronger in backend/runtime architecture than in broad operational maturity

## Best Feedback Targets

The most useful external feedback right now is around:

- streaming architecture and trust boundaries
- real-provider assumptions
- session lifecycle correctness
- FastAPI migration boundary
- operator-facing failure UX
