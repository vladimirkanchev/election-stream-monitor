# Architecture Decision: FastAPI Boundary v1

This document records the current architectural decision for introducing
FastAPI into the local-first monitoring runtime.

It is a short reference for contributors. The goal is to keep ownership
boundaries explicit while the Electron bridge transitions from CLI-backed calls
toward a local HTTP API.

## Decision Summary

FastAPI should own the stable monitoring/session backend contract.

Electron should remain the desktop/runtime host and continue owning privileged
playback and renderer-facing transport concerns.

The React frontend should keep one stable bridge contract and should not care
whether the underlying transport is a demo bridge, CLI bridge, or FastAPI-
backed Electron bridge.

## FastAPI Owns

- `GET /health`
- `GET /detectors`
- `POST /sessions`
- `GET /sessions/{session_id}`
- `POST /sessions/{session_id}/cancel`
- `POST /playback/resolve`
- structured API error payloads
- stable session-domain status semantics

These operations describe stable monitoring behavior rather than desktop-host
implementation details.

## Electron Owns

- app window lifecycle
- preload bridge exposure
- privileged desktop/runtime access
- `local-media://` serving for renderer-safe local playback
- remote HLS playback proxying for the renderer
- playback URL transformation for renderer-safe consumption
- local runtime process management
- optionally later, FastAPI process startup and supervision

These responsibilities are tied to the desktop host and renderer environment.
They are not part of the stable backend monitoring contract.

## React Frontend Owns

- one stable bridge consumer surface
- UI state and presentation
- bridge-contract normalization
- user-facing error handling and presentation

The frontend should not need to know whether data came from:

- demo bridge
- CLI-backed Electron bridge
- FastAPI-backed Electron bridge

## CLI Status

The current CLI bridge remains a valid fallback during migration.

That means:

- existing CLI entry points remain usable while FastAPI integration is incomplete
- Electron can migrate operation by operation instead of switching transport all
  at once

The CLI is a migration fallback and tooling seam, not the intended long-term
main transport for session/domain operations.

## Session State Policy

Immediate route-level failures should come from structured API error payloads.

Ongoing session lifecycle state should come from the persisted session snapshot,
especially:

- `progress.status`
- `progress.status_reason`
- `progress.status_detail`

This keeps request failures distinct from the state of already-running
sessions.

## Migration Order

Recommended order:

1. keep Python session/domain code as the source of truth
2. keep Electron preload and frontend bridge contract stable
3. move low-risk read-oriented operations first:
   - `GET /health`
   - `GET /detectors`
   - `GET /sessions/{session_id}`
   - `POST /playback/resolve`
4. move lifecycle-changing operations later:
   - `POST /sessions`
   - `POST /sessions/{session_id}/cancel`
5. keep CLI fallback during the transition
6. revisit Electron-managed FastAPI startup after the API boundary is stable

## Explicit Non-Goals For This Phase

This phase does not introduce:

- SQLAlchemy
- database-backed persistence
- authentication
- deployment/orchestration concerns
- moving remote HLS playback proxying into FastAPI
- replacing the frontend bridge contract

## Why This Decision

- keeps FastAPI focused on stable backend behavior
- keeps Electron focused on desktop/runtime responsibilities
- reduces migration risk by preserving the frontend contract
- creates a clean path toward later MCP or service-style integration
- avoids mixing backend API design with renderer playback workarounds
