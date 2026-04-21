# Frontend Architecture

This document explains the current frontend shape and how it talks to the
backend.

It is aimed at contributors and coding agents working on the React/Electron
side of the project.

## At a glance

- React owns UI composition and local state transitions
- Electron owns the privileged bridge and playback-safe local media protocol
- Python remains the source of truth for monitoring sessions and playback
  source resolution
- playback state is separate from monitoring session state on purpose

![Frontend overview](./frontend-overview.svg)
![Frontend state flow](./frontend-flow.svg)

## Current frontend idea

The frontend is local-first.

It is built around:

- React for UI
- Electron for the desktop shell and local bridge
- the Python backend for detector logic, session state, and playback resolution

The frontend is no longer just a demo shell. It now follows a clearer split between setup, session, and playback state.

The backend-facing surface is also stricter now:

- one explicit preload bridge surface
- explicit success/error transport envelopes
- one normalized frontend bridge contract consumed by hooks
- local HLS proxying for remote HLS playback that would otherwise fail in the
  renderer

## Main frontend layers

### 1. Setup state

Owned mainly through:

- [`frontend/src/hooks/useSetupState.ts`](../frontend/src/hooks/useSetupState.ts)

This layer owns:

- source mode
- source path
- selected detectors
- visible detectors for the chosen mode

### 2. Monitoring session state

Owned mainly through:

- [`frontend/src/hooks/useMonitoringSession.ts`](../frontend/src/hooks/useMonitoringSession.ts)

This layer owns:

- start monitoring
- stop monitoring
- polling session snapshots
- session status
- session errors
- typed bridge error handling after transport normalization

### 3. Playback state

Owned mainly through:

- [`frontend/src/hooks/usePlaybackSource.ts`](../frontend/src/hooks/usePlaybackSource.ts)

This layer owns:

- playback source resolution
- playback status
- playback time
- playback errors
- live-vs-file playback assumptions derived from the resolved source
- HLS vs direct-file playback behavior after resolution

That split is important because backend session state and media playback state are related, but they are not the same thing.

## Main UI file

- [`frontend/src/App.tsx`](../frontend/src/App.tsx)

`App.tsx` is now mostly composition:

- setup controls
- session status panel
- playback panel
- alert feed

The heavy state logic was moved into hooks and small view-model helpers.

## Electron bridge

Main backend bridge files:

- [`frontend/electron/main.mjs`](../frontend/electron/main.mjs)
- [`frontend/electron/preload.mjs`](../frontend/electron/preload.mjs)
- [`frontend/src/bridge/contract.ts`](../frontend/src/bridge/contract.ts)
- [`frontend/src/bridge/transport.ts`](../frontend/src/bridge/transport.ts)

Current responsibilities are split like this:

- `preload.mjs`
  - exposes one minimal `window.electionBridge` surface
- `main.mjs`
  - stays mostly as Electron bootstrap and wiring
  - registers bridge handlers and app/protocol lifecycle hooks
  - delegates FastAPI startup/readiness orchestration and transport details to focused helpers
- `contract.ts`
  - normalizes payloads and raises typed bridge errors
- `transport.ts`
  - selects the active transport implementation and falls back to demo mode when needed

The bridge currently handles:

- listing detectors
- starting a session
- reading a session snapshot
- cancelling a session
- resolving playback sources
- serving local media to the renderer
- proxying remote HLS playlists and assets through `local-media://`

This is the layer that keeps the React frontend from needing to know Python process details directly.

The bridge error payload can now preserve backend-native metadata when
available:

- `backend_error_code`
- `status_reason`
- `status_detail`

UI code may still present a simplified operator-facing message, but the bridge
contract now has room to preserve backend meaning during the FastAPI migration.

## Current design goals

The frontend is optimized for:

- local development speed
- understandable state flow
- stable playback for local files and segments
- stable playback for remote HLS sources that require Electron-side proxying
- future source growth without rewriting everything
- transport replaceability without changing UI semantics

That is why the frontend now prefers:

- small hooks
- normalized state
- simple control rules
- presentation-focused components

## Current UX model

The main user flow is:

1. choose source mode
2. choose file or folder path
3. choose detectors
4. start monitoring
5. watch playback
6. inspect alerts
7. end monitoring

That flow should stay simple even if more detectors or API streams are added later.

## Future direction

Most likely frontend next steps:

- keep detector UX simple as more detectors are added
- show better error and session diagnostics
- keep hardening `api_stream` as another source type
- avoid coupling frontend logic too tightly to one backend transport

## Notes For Agents

- Keep business rules out of React components when they can live in hooks or
  presenters.
- Treat `bridge/contract.ts` and `types.ts` as the canonical frontend contract
  boundary.
- If you change remote playback behavior, check:
  - `frontend/electron/main.mjs`
  - `frontend/electron/hlsProxy.mjs`
  - `frontend/src/hooks/usePlaybackSource.ts`
  - `frontend/src/components/VideoPlayerPanel.tsx`
