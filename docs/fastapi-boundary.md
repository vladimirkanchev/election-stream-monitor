# FastAPI Boundary

This document describes the recommended boundary if the current local-first
runtime later gains a FastAPI layer.

It is written for contributors and coding agents who need a pragmatic split
between stable monitoring contracts and desktop/runtime-specific concerns.

## Short version

FastAPI should own the stable monitoring API surface.

It should not absorb every Electron or local-runtime implementation detail.

## FastAPI should own

- `POST /sessions`
  - start a monitoring session
- `POST /sessions/{session_id}/cancel`
  - request session cancellation
- `GET /sessions/{session_id}`
  - read the current session snapshot
- `GET /detectors`
  - expose the detector catalog
- `POST /playback/resolve`
  - resolve the current playback source from validated monitoring inputs

These operations already exist conceptually in the CLI/bridge flow today, so
they are the cleanest candidates to become HTTP endpoints later.

## Should remain local/runtime-specific

- Electron `local-media://` serving
- Electron remote HLS proxying for renderer playback
- local file trust and path validation for desktop use
- FFmpeg / FFprobe subprocess invocation
- session temp-file materialization and cleanup
- detached child-process spawn details used by the current CLI bridge

These concerns are real, but they are not part of the stable monitoring API
contract. They belong to the current runtime environment, not to FastAPI as a
service abstraction.

## Why this split is useful

- keeps FastAPI focused on session/domain behavior instead of desktop plumbing
- preserves the current local-first runtime while still preparing a service path
- makes testing cleaner because API tests can target stable session semantics
- avoids coupling HTTP design to Electron-specific playback transport details

## Failure-policy implications

If FastAPI is added later, the API layer should surface:

- stable session status
- `progress.status_reason`
- `progress.status_detail` when appropriate

That is enough for clients to distinguish:

- retry-like transient reads
- graceful stops
- terminal failures
- explicit cancels

without forcing clients to parse raw loader logs.

## Migration guidance

The recommended order is:

1. keep Python session/domain code as the source of truth
2. wrap existing session start/read/cancel flows in FastAPI
3. keep Electron using the same session snapshot semantics
4. move only the stable bridge surface first
5. reconsider playback proxy ownership separately later

The key idea is to migrate the contract first, not every runtime detail at once.
