# FastAPI Boundary

This document explains the current FastAPI layer in the project: what it does,
how to run it locally, what contract it exposes, and what is still incomplete.

Right now, FastAPI is the owned runtime backend for the main Electron session
bridge. It is still a thin HTTP boundary over the existing local-first
session/domain code, and it does not replace Electron-specific playback or
renderer transport responsibilities.

## Current Status

The FastAPI layer currently provides:

- `GET /health`
- `GET /detectors`
- `POST /sessions`
- `GET /sessions/{session_id}`
- `POST /sessions/{session_id}/cancel`
- `POST /playback/resolve`

These endpoints already use:

- explicit request/response schemas
- structured error payloads
- cleaned session snapshot semantics

What is still partial:

- playback proxying and renderer-specific media handling still live in Electron
- startup/readiness ownership is in place, but the runtime model still needs
  hardening and broader validation

## Current Runtime State

Electron now uses FastAPI as the normal runtime transport for the main session
lifecycle and read paths.

Python CLI commands remain available as tooling/debugging commands, not as the
normal Electron runtime backend path.

## Current Startup Model

Electron now:

- starts the local FastAPI process when needed
- waits briefly for `/health` during startup
- uses one shared runtime policy for unavailable-backend behavior

The next step is to harden and validate that startup model rather than decide
whether it should exist.

That means:

- validating startup/readiness ownership with focused Electron tests
- deciding whether any development-only escape hatch is still needed
- tightening docs and runtime policy as the model settles

## Run Locally

From the repository root:

```bash
. .venv/bin/activate
uvicorn api.app:app --app-dir src --reload
```

Open the interactive docs at:

- `http://127.0.0.1:8000/docs`

## What The API Owns

The FastAPI layer currently wraps stable backend/session behavior:

- detector catalog reads
- monitoring session start
- monitoring session snapshot read
- cancellation request
- validated playback-source resolution

It does not currently own:

- Electron `local-media://` serving
- Electron remote HLS proxying
- desktop/runtime-specific process management
- the full frontend transport path

## Endpoints

### `GET /health`

Simple local backend health check.

### `GET /detectors`

Returns the detector catalog for the current runtime. Optional `mode` filtering
is supported for:

- `video_segments`
- `video_files`
- `api_stream`

### `POST /sessions`

Starts a monitoring session and returns the pending session metadata.

### `GET /sessions/{session_id}`

Returns the current persisted session snapshot.

### `POST /sessions/{session_id}/cancel`

Requests cancellation for an existing monitoring session.

### `POST /playback/resolve`

Validates monitoring input and returns a playback source contract for the
frontend/Electron layer.

## Structured Error Payloads

Route-level failures use one consistent JSON shape:

```json
{
  "detail": "Session not found",
  "error_code": "session_not_found",
  "status_reason": "session_not_found",
  "status_detail": "No persisted session snapshot found for session_id=abc123"
}
```

Typical cases include:

- `validation_failed`
- `session_not_found`
- `playback_unavailable`
- `session_start_failed`
- `internal_error`

The API also normalizes request validation failures into the same structured
shape instead of using the default FastAPI validation response.

## Session Snapshot Meaning

`GET /sessions/{session_id}` returns a snapshot with these top-level fields:

- `session`
- `progress`
- `alerts`
- `results`
- `latest_result`

Important `progress` fields:

- `status`
- `status_reason`
- `status_detail`

Use them like this:

- route-level request failure:
  returned as a structured API error payload
- ongoing or terminal session state:
  returned through the session snapshot

That separation is important. A request can succeed while the session itself is
already failed, completed, or cancelled.

## Input Modes

The FastAPI layer currently accepts these monitoring modes:

- `video_segments`
- `video_files`
- `api_stream`

Invalid mode values are rejected at the API boundary.

## Current Integration Limits

This is still a migration-stage backend layer.

Today that means:

- FastAPI wraps the current local-first backend logic
- CLI entry points still exist for tooling/debugging and scripted inspection
- Electron integration is still partial
- renderer-facing playback concerns still belong to Electron

So the FastAPI layer is already useful and testable, but it is not yet the only
owned runtime concern in the application.
