# Testing And Validation

This document summarizes how the repo is currently validated and where deeper
confidence still needs to be built.

Use it for verification commands and validation scope.
Do not use it as a detailed architecture or contract doc.

## Routine Validation

## CI Shape

The current GitHub Actions workflow uses three practical layers:

- `changes`
  - path filter job that classifies backend, frontend, docs, workflow, and contract-sensitive edits
- `frontend-checkpoint`
  - quick Electron/bridge/session-flow regression signal
- `backend-tests`
  - packaging/import smoke check after editable install
  - backend tests
- `backend-ruff`
  - primary Python lint check with Ruff
- `frontend-typecheck`
  - frontend TypeScript typecheck
- `frontend-lint`
  - advisory frontend ESLint signal on `src` TypeScript files
- `feature-gate`
  - summary job for the fast backend/frontend checks on pull requests
  - useful as a single CI signal, even though feature branches are no longer
    protected merge targets
- `main-gate`
  - summary job for the full `main` pull-request validation set
  - keeps `main` defended with one required context instead of seven separate
    merge blockers
- `contract-checks`
  - boundary-focused backend and frontend contract checks for PRs
- `backend-typecheck`
  - targeted type defense for the contract-sensitive Python boundary modules
- `backend-pyright`
  - advisory VSCode-aligned type signal for the same Python boundary modules
- `test-and-build`
  - full frontend tests
  - frontend build
- `main` pull-request guards
  - a small integration smoke test
  - a lightweight docs/contract consistency check
  - contract-sensitive changes must move with nearby tests and owning docs
- `docs-consistency`
  - path-aware docs and workflow consistency checks for non-`main` pull requests
- `weekly-validation`
  - scheduled slow e2e media tests
  - lifecycle-focused backend test coverage
  - deeper `api_stream` validation
  - Bandit security audit
  - `pip-audit` Python dependency scan
  - `npm audit` frontend dependency scan
  - dependency consistency check
  - packaging smoke check

Failure-only artifacts are now uploaded for the heaviest backend PR lane, the
weekly lifecycle lane, the slow e2e lane, and the weekly `api_stream`
deep-validation lane, starting with plain test logs.
The weekly lifecycle lane also uploads the persisted session files that most
often explain runner state, cancel behavior, and terminal outcomes.

This keeps ordinary branch feedback reasonably fast while giving `main` a
stricter merge barrier.

Feature branches now rely on CI feedback rather than required branch
protection. The underlying fast jobs still run, and the `feature-gate` job
provides one easy-to-scan summary context for pull requests.
The `main` branch now uses a repository ruleset for a single required summary
gate. The `main-gate` job depends on the fast feature gate, the main PR
consistency check, integration smoke, contract checks, and the full frontend
test/build job. That keeps the branch defended without forcing GitHub to
reconcile seven separate required contexts at once.
The protected CI workflow now runs on pull requests rather than both pushes
and pull requests, which avoids duplicate status contexts on the same PR head.
Stale PR runs are also canceled automatically with GitHub Actions concurrency.

The workflow is now path-aware:

- backend-heavy work runs only when backend or contract files change
- frontend-heavy work runs only when frontend or contract files change
- docs/workflow consistency checks run on docs-oriented pull requests
- PRs into `main` still receive the full validation set
- contract-boundary edits on `main` PRs are expected to come with matching
  tests and the owning docs update

The slower confidence-building checks run weekly instead of on every PR, so
the repo gets a broader safety net without turning normal branch work into a
long queue.

### Backend

The Python suite covers:

- detector and alert-rule behavior
- session runner lifecycle
- session persistence and snapshot assembly
- `api_stream` validation and loading
- loader contract helpers and deterministic seam behavior
- HLS/provider edge cases and soak-oriented scenarios

Alert-rule coverage is now split so the ownership is easier to scan:

- `tests/test_alert_rules.py`
  - metadata, failure wrapping, malformed payload tolerance, and detector isolation
- `tests/test_alert_rules_black.py`
  - `video_metrics` black-screen rule state transitions
- `tests/test_alert_rules_blur.py`
  - `video_blur` rolling/recovery rule state transitions

Common local command:

```bash
. .venv/bin/activate
pip install -e .[test]
pytest -q
```

The current backend packaging split is:

- `pip install -e .`
  - runtime dependencies only
- `pip install -e .[test]`
  - runtime plus backend test tooling
- `pip install -e .[dev]`
  - runtime plus test, Ruff lint, and type-check tooling

Current backend import/run expectations:

- `npm run dev`
  - canonical desktop runtime path
- `pip install -e .` or `pip install -e .[test]`
  - editable-install path for backend runtime and test work
- `PYTHONPATH=src`
  - raw-checkout backend import/debug path when you are not relying on an
    editable install
- `uvicorn api.app:app --app-dir src --reload`
  - backend-only HTTP startup path for the current flat `src/` layout

Packaging sanity check:

```bash
python3 -m venv /tmp/esm-packaging-check
/tmp/esm-packaging-check/bin/python -m pip install --upgrade pip
/tmp/esm-packaging-check/bin/python -m pip install --no-deps --no-build-isolation -e .
```

Runtime import smoke check:

```bash
. .venv/bin/activate
pip install -e .[test]
python -c "import api.app, api.routers.sessions, session_service, session_cli"
```

Raw-checkout import/debug check:

```bash
PYTHONPATH=src .venv/bin/python -c "import api.app, api.routers.sessions, session_service, session_cli"
```

The first check confirms that editable installs still build cleanly with the
current package metadata. The second confirms that the backend import surface
still works in a runtime-capable environment after packaging changes. The
third is useful when you want to confirm raw-checkout backend imports still
work with the current `src/` layout.

Dedicated backend typecheck:

```bash
uv sync --extra typecheck
MYPYPATH=src mypy --explicit-package-bases src/alert_rules.py src/api/app.py src/api/routers/detectors.py src/api/routers/health.py src/api/routers/playback.py src/api/routers/sessions.py src/api/schemas.py src/session_io.py src/session_models.py src/session_runner.py src/session_service.py src/stream_loader_contracts.py
```

Use `uv sync --extra typecheck` to make sure the local typecheck env has the
required checker deps.
Use `MYPYPATH=src` so mypy resolves the flat `src/` modules as source files
rather than treating them like installed third-party packages.
Use this after changing the Python contracts that sit closest to the frontend
bridge, session lifecycle, or alert-rule boundary.

Primary backend lint check:

```bash
python -m pip install -e .[lint]
ruff check src tests
```

Use this as the main Python lint gate now that Ruff is the standardized
linter. Keep Bandit separate for security-focused checks.

CI currently runs the Ruff job as a fast backend gate on backend or contract
changes, and on `main` pull requests.

Advisory backend pyright check:

```bash
python -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/pip install -e .[typecheck]
.venv/bin/pyright --project pyrightconfig.json src/alert_rules.py src/api/app.py src/api/routers/detectors.py src/api/routers/health.py src/api/routers/playback.py src/api/routers/sessions.py src/api/schemas.py src/session_io.py src/session_models.py src/session_runner.py src/session_service.py src/stream_loader_contracts.py
```

Use this as a non-blocking editor-aligned signal if you want pyright feedback
without making it the required branch gate yet.

### Frontend

The frontend suite covers:

- setup flow
- playback source routing
- session status UX
- playback error messaging
- bridge contract normalization

Frontend type safety is intentionally strict:

- `tsc -b --incremental false`
- `noUncheckedIndexedAccess`
- `exactOptionalPropertyTypes`
- `noPropertyAccessFromIndexSignature`
- `noImplicitReturns`
- `noFallthroughCasesInSwitch`

Common local command:

```bash
npm --prefix frontend run test
```

Advisory frontend lint check:

```bash
npm --prefix frontend run lint:frontend
```

Use this as a lightweight frontend quality signal. It is not yet part of the
required merge gate, but it is already wired into CI as a non-blocking job.

## FastAPI And Bridge Contract Checks

These tests are especially important for the current project stage because they
protect the boundary between backend contracts and frontend normalization.

Backend/API contract checks:

- `tests/test_api_boundary_validation.py`
  - FastAPI request validation
- `tests/test_api_boundary_playback.py`
  - playback-resolution behavior
- `tests/test_api_boundary_sessions.py`
  - session start/read/cancel behavior
- `tests/test_session_service.py`
  - shared start/read/cancel service behavior
- `tests/test_session_cli_tooling.py`
  - CLI adapter behavior over the shared session service
- `tests/test_api_boundary_contracts.py`
  - structured API error payloads
  - populated session snapshot response shape
- `tests/test_api_boundary_sessions.py`
  - session start/read/cancel contract behavior
- `tests/test_session_service.py`
  - shared start/read/cancel service behavior
- `tests/test_session_cli_tooling.py`
  - CLI adapter behavior over the shared session service
- `tests/test_stream_loader_contracts.py`
  - `api_stream` contract-builder consistency
  - loader seam helper invariants
  - replay/identity helper behavior
- `tests/test_stream_loader_http_hls_core_playlist.py`
  - ordinary playlist parsing, variant resolution, and segment-path resolution
- `tests/test_stream_loader_http_hls_core_progression.py`
  - live progression, moving-window, cancel, and idle-refresh behavior
- `tests/test_stream_loader_http_hls_core_provider.py`
  - malformed refresh recovery and provider/transport edge behavior
- `tests/test_stream_loader_http_hls_reconnect.py`
  - reconnect, replay de-duplication, and moving-window recovery behavior
- `tests/test_stream_loader_http_hls_limits.py`
  - runtime/fetch/temp-budget enforcement and cleanup guarantees
- `tests/test_stream_loader_http_hls_playlist.py`
  - direct playlist parsing helper coverage
- `tests/test_stream_loader_http_hls_fetch.py`
  - direct transport helper coverage
- `tests/test_stream_loader_http_hls_materialize.py`
  - direct temp-file materialization helper coverage
- `tests/test_stream_loader_http_hls_policy.py`
  - direct replay/window/policy helper coverage

Frontend contract checks:

- `frontend/src/bridge/contract.success.test.ts`
  - bridge success normalization
  - detector and playback-source normalization
- `frontend/src/bridge/contract.errors.test.ts`
  - typed bridge failures
  - transport-envelope error normalization
  - bridge error payload fallback and typed metadata preservation
- `frontend/src/bridge/contract.session-snapshot.test.ts`
  - session snapshot compatibility
  - fail-closed nested payload handling
- `frontend/src/bridge/transport.test.ts`
  - transport selection and demo fallback behavior
- `frontend/src/uiErrors.test.ts`
  - operator-facing error wording
  - `api_stream` status/error interpretation
- `frontend/src/hooks/useMonitoringSession.lifecycle.test.tsx`
  - hook behavior for local lifecycle polling, cancel-state transitions, and typed failures
- `frontend/src/hooks/useMonitoringSession.apiStream.test.tsx`
  - hook behavior for `api_stream` reconnect, recovery, and terminal polling semantics
- `frontend/src/hooks/usePlaybackSource.test.tsx`
  - hook behavior on top of normalized playback-source resolution
- `frontend/src/uiErrors.test.ts`
  - operator-facing error wording
  - `api_stream` status/error interpretation
- `frontend/electron/fastApiFallback.test.mjs`
  - FastAPI readiness cache and fallback policy
  - no-fallback behavior for structured API business errors
- `frontend/electron/fastApiRuntimePolicy.test.mjs`
  - startup timeout and clear unavailable-runtime behavior
  - no-operation execution after startup failure
- `frontend/electron/fastApiProcessManager.test.mjs`
  - FastAPI process ownership
  - single-start behavior and process-state reset
- `frontend/electron/bridgeResponses.test.mjs`
  - Electron bridge success/error envelope mapping
  - structured bridge payload expectations for lifecycle operations
- `frontend/electron/bridgeHandlerRegistry.test.mjs`
  - current IPC channel map and shared runtime-policy wrapping
- `frontend/electron/fastApiClient.test.mjs`
  - FastAPI JSON request/response shaping
- `frontend/electron/fastApiStartupOrchestrator.test.mjs`
  - startup composition across process management, readiness checks, and policy
- `frontend/electron/playbackSourcePolicy.test.mjs`
  - renderer-safe playback URL adaptation
- `frontend/electron/localMediaResponses.test.mjs`
  - concrete `local-media://` file/range response helpers
- `frontend/electron/localMediaRequestPolicy.test.mjs`
  - `local-media://` request classification and routing policy
- `frontend/electron/hlsProxy.test.mjs`
  - remote HLS manifest rewriting and opaque proxy-token behavior

Use these focused checks when changing:

- shared session start/read/cancel mechanics
- detached worker launch, `worker.log` capture, or parent/worker observability
- FastAPI request/response schemas
- session snapshot fields
- bridge error payloads
- frontend normalization logic
- frontend transport selection and demo fallback behavior
- bridge helper ownership or validator-sharing inside the normalized contract layer
- Electron transport fallback or bridge-envelope behavior
- Electron startup orchestration, readiness policy, or process ownership
- Electron bridge-handler registration or playback URL adaptation
- `local-media://` protocol routing/response behavior
- `api_stream` contract builders or loader helper semantics
- concrete HTTP/HLS reconnect, cleanup, or limit behavior
- the new direct HLS helper modules or their helper-level invariants

Focused HLS helper command:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/pytest -p no:cacheprovider \
  tests/test_stream_loader_http_hls_playlist.py \
  tests/test_stream_loader_http_hls_fetch.py \
  tests/test_stream_loader_http_hls_materialize.py \
  tests/test_stream_loader_http_hls_policy.py -q
```

Useful focused commands:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/pytest -p no:cacheprovider tests/test_session_service.py tests/test_api_boundary_sessions.py tests/test_session_cli_tooling.py -q
```

Use that command first for worker-observability changes. It covers:

- shared worker-launch behavior in `session_service.py`
- the current API rule that diagnostics stay backend-owned
- CLI-side worker failure logging behavior

### Legacy Seam Replacement

For the demoted legacy `src/main.py` seam, the intended replacement is focused
pytest coverage rather than a new manual tooling script. The main local
confidence replacements are:

- `tests/test_processor.py`
- `tests/test_session_runner_local.py`
- `tests/test_e2e_local_session.py`

```bash
PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/pytest -p no:cacheprovider tests/test_api_boundary_*.py -q
```

```bash
cd frontend
npm run test -- src/bridge/contract.success.test.ts src/bridge/contract.errors.test.ts src/bridge/contract.session-snapshot.test.ts src/uiErrors.test.ts
```

```bash
cd frontend
npm run test:electron-bridge
```

Frontend migration checkpoint:

```bash
cd frontend
npm run test:frontend-checkpoint
```

Dedicated frontend typecheck:

```bash
cd frontend
npm run typecheck
```

Cancel migration checkpoint:

```bash
cd frontend
npm run test:cancel-migration
```

Startup/runtime checkpoint:

```bash
cd frontend
npm run test:startup-runtime
```

Startup milestone checkpoint:

```bash
cd frontend
npm run test:startup-milestone
```

Use this checkpoint after a meaningful FastAPI startup/readiness change when
you want both the focused Electron runtime tests and the broader frontend
session-flow checks in one run.

If a change touches FastAPI startup/readiness behavior, run Electron-layer
startup tests first before expanding into broader app-level checks.

For narrower diagnosis:

```bash
cd frontend
npm run test:electron-bridge
npm run test:session-flow
```

For faster local feedback loops, use the narrower frontend aliases:

```bash
cd frontend
npm run test:app-runtime
```

Runs the heavier App integration checks for start/cancel/polling behavior
without paying for the full frontend suite.

```bash
cd frontend
npm run test:ui-fast
```

Runs the cheap bridge/view-model/presenter/source-model slices that are useful
when iterating on contracts or UI state logic without touching the App shell.

## Lifecycle Slice Validation

After each lifecycle-hardening slice, run:

```bash
cd frontend
npm run test:startup-milestone
```

Use the full frontend suite at larger boundaries, such as before grouping
commits or after a broader lifecycle/race hardening pass:

```bash
cd frontend
npm run test
```

If one side of the contract changes, do not rely on only backend tests or only
frontend tests. Run at least one focused backend contract check and one focused
frontend normalization check together.

For a branch that is about to merge into `main`, also run a small composed
smoke check:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/pytest -p no:cacheprovider tests/test_e2e_local_session.py -q
```

For the backend E2E suites, the current split is:

- `tests/test_e2e_local_session.py`
  - small snapshot-contract smoke check
- `tests/test_e2e_local_session_real_media.py`
  - curated real-media local-session coverage
- `tests/test_e2e_session_ground_truth_api_stream.py`
  - synthetic `api_stream` ground-truth contract cases
- `tests/test_e2e_session_ground_truth_local.py`
  - slower real-media ground-truth matrix

Use markers to keep local feedback tight:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/pytest -p no:cacheprovider -m "e2e and not slow" tests/test_e2e_*.py -q
```

That command keeps:

- the small local-session smoke test
- the synthetic `api_stream` ground-truth cases

and skips the heavier real-media suites until you actually need them.

Run the fuller real-media E2E pass when changing detector behavior, windowing,
or persisted snapshot expectations for checked-in media fixtures:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/pytest -p no:cacheprovider -m "e2e and slow" tests/test_e2e_*.py -q
```

Note:

- some Electron/HLS tests bind loopback listeners on `127.0.0.1`
- those cases may fail inside stricter sandboxes even when the code is healthy
- if that happens, rerun the same targeted suite in a normal local shell

Recommended backend order for session-runner work:

1. `tests/test_session_runner_lifecycle.py`
2. `tests/test_session_runner_execution.py`
3. `tests/test_session_runner_terminal.py`
4. `tests/test_session_runner_local.py`
5. `tests/test_session_runner_api_stream_basic.py`
6. `tests/test_session_runner_api_stream_http_hls.py` in a normal local shell when loopback sockets are available

## Lifecycle Coverage Audit

Current lifecycle coverage is already spread across the main layers:

- backend tests
  - `tests/test_session_runner_lifecycle.py`
    - pending-session setup
    - pending-to-running transition semantics
    - smallest helper-level seam for session setup and status transitions
  - `tests/test_session_runner_execution.py`
    - extracted local execution-loop helper behavior
    - extracted live `api_stream` execution-loop helper behavior
    - analyzer-bundle invocation and event-persistence seams
    - first stop when a refactor changes slice-processing flow
  - `tests/test_session_runner_terminal.py`
    - terminal outcome persistence
    - validation-failure persistence
    - api-stream cleanup accounting and terminal log-field shaping
    - first stop when a refactor changes status mapping, cleanup, or terminal logs
  - `tests/test_session_runner_local.py`
    - start-to-completed flow
    - mid-run cancel leading to `cancelled`
    - runtime failure persistence
    - validation failure persistence
    - stable black-box local lifecycle coverage
    - local discovery and slice-expansion behavior now owned by
      `session_runner_discovery`
  - `tests/test_session_runner_api_stream_basic.py`
    - seam-loader `api_stream` completion, cancel, cleanup, and failure paths
    - stable black-box live progress and summary logging behavior
  - `tests/test_session_runner_api_stream_http_hls.py`
    - real HTTP/HLS-backed `api_stream` transport and lifecycle integration
    - keep this as the signoff suite when a change touches real HTTP/HLS behavior
  - `tests/test_session_io.py`
    - invalid terminal transitions
    - completed-progress consistency checks
- FastAPI boundary tests
  - `tests/test_api_boundary_validation.py`
    - request validation failures
  - `tests/test_api_boundary_sessions.py`
    - missing-session reads
    - cancel success
    - missing-session cancel failure
    - current terminal cancel behavior
  - `tests/test_api_boundary_contracts.py`
    - structured error envelopes
    - malformed nested payload fail-closed behavior
- Electron bridge/runtime tests
  - `frontend/electron/bridgeResponses.test.mjs`
    - start/cancel success mapping
    - structured start/cancel failure mapping
    - generic unavailable-runtime failure mapping
  - `frontend/electron/fastApiRuntimePolicy.test.mjs`
    - startup readiness success
    - startup timeout and clear unavailable failure
  - `frontend/electron/fastApiFallback.test.mjs`
    - legacy fallback/helper seam coverage for start/read/cancel edge cases
- frontend app/session-flow tests
  - `frontend/src/App.startSession.test.tsx`
    - start failures
    - malformed start payloads
    - initial-read failure after start
    - successful `api_stream` start flow
  - `frontend/src/App.cancelSession.test.tsx`
    - normal cancel flow
    - typed cancel failures
    - malformed cancel payloads
    - missing-session cancel failure
    - `cancelSession -> null` success
  - `frontend/src/App.pollingStatus.test.tsx`
    - running-to-completed polling flow
    - polling failure with recovery
    - running-to-failed terminal transitions
    - `api_stream` status/detail messaging

Current high-value gaps:

- no explicit backend truth-table style test for repeated cancel requests
- no explicit backend/API test for canceling an already terminal session as a final intended rule
- no focused Electron test for read-session missing-session bridge mapping
- no frontend app-flow coverage for cancel-after-completion

## Current Branch Validation Baseline

This branch currently has a green full-suite validation baseline:

- backend: `350 passed, 3 skipped`
- frontend/Electron: `24 files passed, 203 tests passed`

That is strong coverage for the current late-prototype / MVP stage.
The remaining gaps are mostly security-policy activation and deeper Electron
main-process composition checks, not broad missing functional coverage.
  - stale poll result arriving after cancel request
  - repeated end/cancel requests from the UI

Use this audit before adding more lifecycle tests so new coverage fills a real
gap instead of duplicating an existing layer.

### Runtime Doc Alignment

When the desktop runtime model changes, keep these docs aligned:

- `docs/fastapi-boundary.md`
- `docs/architecture-decision-fastapi.md`
- `docs/architecture.md`
- `README.md`
- `frontend/README.md`

These docs should describe the same normal runtime path:

- Electron owns local FastAPI startup/readiness
- FastAPI is the normal desktop runtime backend
- Python CLI commands remain available for tooling/debugging only

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

- backend runtime install plus `test` extra for pytest jobs
- frontend install
- frontend test run
- frontend build

That is enough to catch common regressions without pretending CI replaces
manual real-stream validation.
