## Summary

This branch promotes the FastAPI backend boundary into the main runtime path and cleans up several backend/frontend seams that had drifted during earlier milestone work.

The largest changes are architectural rather than feature-facing:
- FastAPI backend boundary is now the owned runtime backend path
- shared session service / CLI seam is established
- session-runner logic is split into focused helper modules
- HTTP/HLS `api_stream` loading is split into focused helper modules
- frontend/backend source contract and repo docs are aligned with current behavior
- Python packaging/install/CI expectations are cleaner

## Main changes

### FastAPI backend boundary
- established FastAPI as the current backend runtime boundary
- aligned frontend/electron/backend assumptions with that model
- clarified backend-only startup vs normal Electron app startup

### Shared session service / CLI split
- introduced a clearer shared service seam for session operations
- kept CLI as a tooling/debugging path over shared backend logic rather than a primary runtime entrypoint

### Session-runner modularization
- split session-runner responsibilities into focused modules for:
  - lifecycle
  - execution
  - terminal/persistence behavior
- kept the top-level runner as the orchestration shell

### HLS loader split
- split `stream_loader_http_hls.py` into focused helper modules for:
  - playlist parsing
  - fetch/error mapping
  - temp-file materialization
  - policy/state transitions
- kept the top-level HLS loader as the concrete orchestration shell

### Source contract and docs cleanup
- tightened frontend source access inference to match selected mode more reliably
- aligned `source_validation.py` docs/comments with actual DNS-check behavior
- refreshed `NEXT_SESSION.md`, README wording, and related docs to match current repo state

### Packaging / install / CI cleanup
- separated runtime dependencies from test/lint/typecheck tooling in `pyproject.toml`
- added explicit build-system metadata
- clarified editable install, backend import, and backend startup expectations
- added packaging/import smoke coverage in CI

## Validation

### Backend
- focused pytest slices for session, API boundary, validation, and HLS helper behavior
- editable install smoke check passed
- backend import/startup smoke checks passed

### Frontend
- frontend test suites passed
- app/session/playback-focused Vitest suites passed
- production build passed

## Notes

- the frontend bundle is now split more cleanly:
  - lazy-loaded playback panel
  - dynamic `hls.js` loading for HLS-only playback
  - lazy-loaded alert details drawer
- the remaining large HLS chunk is on-demand rather than startup-critical

This branch is broad but intentionally grouped around one theme: making the FastAPI/session/runtime boundary the real architecture, then cleaning up the surrounding contracts, loader structure, and install story to match.
