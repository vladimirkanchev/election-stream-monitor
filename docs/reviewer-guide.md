# Reviewer Guide

This document is for engineers who want to review the repo efficiently without
reading every file first.

If you only care about one subsystem, skip straight to that section instead of
reading the whole repo front to back.

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
- [`src/source_validation.py`](../src/source_validation.py)
- [`frontend/electron/hlsProxy.mjs`](../frontend/electron/hlsProxy.mjs)
- [`frontend/electron/main.mjs`](../frontend/electron/main.mjs)

Key review themes:

- source validation and trust policy
- reconnect and failure policy
- temp-file lifecycle
- remote HLS proxy behavior
- provider-specific failure handling

### Backend Session Runner

Start here if you care most about monitoring lifecycle, progress semantics, and
persistence.

- [`src/session_runner.py`](../src/session_runner.py)
- [`src/session_io.py`](../src/session_io.py)
- [`src/session_models.py`](../src/session_models.py)
- [`src/processor.py`](../src/processor.py)

Key review themes:

- session start/stop/cancel/fail behavior
- progress snapshots and persisted state
- dedup/replay handling
- detector/rule orchestration

### Frontend Playback / Status UX

Start here if you care most about operator clarity and runtime diagnostics.

- [`frontend/src/components/VideoPlayerPanel.tsx`](../frontend/src/components/VideoPlayerPanel.tsx)
- [`frontend/src/components/SessionStatusPanel.tsx`](../frontend/src/components/SessionStatusPanel.tsx)
- [`frontend/src/hooks/usePlaybackSource.ts`](../frontend/src/hooks/usePlaybackSource.ts)
- [`frontend/src/hooks/useMonitoringSession.ts`](../frontend/src/hooks/useMonitoringSession.ts)

Key review themes:

- playback failure messaging
- separation of playback vs monitoring failure states
- operator diagnostics during retrying and terminal failures
- frontend/backend contract alignment

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
