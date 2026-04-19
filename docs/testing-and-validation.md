# Testing And Validation

This document summarizes how the repo is currently validated and where deeper
confidence still needs to be built.

Use it for verification commands and validation scope.
Do not use it as a detailed architecture or contract doc.

## Routine Validation

### Backend

The Python suite covers:

- detector and alert-rule behavior
- session runner lifecycle
- session persistence and snapshot assembly
- `api_stream` validation and loading
- HLS/provider edge cases and soak-oriented scenarios

Common local command:

```bash
. .venv/bin/activate
pytest -q
```

### Frontend

The frontend suite covers:

- setup flow
- playback source routing
- session status UX
- playback error messaging
- bridge contract normalization

Common local command:

```bash
npm --prefix frontend run test
```

## FastAPI And Bridge Contract Checks

These tests are especially important for the current project stage because they
protect the boundary between backend contracts and frontend normalization.

Backend/API contract checks:

- `tests/test_api_boundary.py`
  - FastAPI request validation
  - structured API error payloads
  - session start/read/cancel behavior
  - playback-resolution behavior
  - populated session snapshot response shape

Frontend contract checks:

- `frontend/src/bridge/contract.test.ts`
  - bridge normalization
  - typed bridge failures
  - session snapshot compatibility
- `frontend/src/uiErrors.test.ts`
  - operator-facing error wording
  - `api_stream` status/error interpretation
- `frontend/electron/fastApiFallback.test.mjs`
  - FastAPI readiness cache and fallback policy
  - no-fallback behavior for structured API business errors
- `frontend/electron/bridgeResponses.test.mjs`
  - Electron bridge success/error envelope mapping
  - structured bridge payload expectations for lifecycle operations

Use these focused checks when changing:

- FastAPI request/response schemas
- session snapshot fields
- bridge error payloads
- frontend normalization logic
- Electron transport fallback or bridge-envelope behavior

Useful focused commands:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/pytest -p no:cacheprovider tests/test_api_boundary.py -q
```

```bash
cd frontend
npm run test -- src/bridge/contract.test.ts src/uiErrors.test.ts
```

Frontend migration checkpoint:

```bash
cd frontend
npm run test:frontend-checkpoint
```

For narrower diagnosis:

```bash
cd frontend
npm run test:electron-bridge
npm run test:session-flow
```

If one side of the contract changes, do not rely on only backend tests or only
frontend tests. Run at least one focused backend contract check and one focused
frontend normalization check together.

### Build Validation

Common local build command:

```bash
npm run build
```

## Opt-In Manual Validation

Public-stream validation is intentionally split from routine tests because
provider behavior is unstable and can make CI noisy.

Use:

- [api-stream-local-validation.md](./api-stream-local-validation.md)
- `tests/test_api_stream_real_smoke.py`

That split keeps normal regression tests reproducible while still leaving a
path for real-stream confidence checks.

## Current Validation Limits

- not all public providers allow automated fetches
- some providers require Cloudflare/browser behavior and will fail even with a
  local proxy
- long-run operational confidence is improving but not finished
- broader multi-user or service-mode validation still belongs to the next stage

## What CI Should Cover

The current GitHub Actions workflow is intentionally lightweight:

- backend install and test run
- frontend install
- frontend test run
- frontend build

That is enough to catch common regressions without pretending CI replaces
manual real-stream validation.
