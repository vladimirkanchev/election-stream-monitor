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
The protected CI workflow runs on pull requests, and feature-branch pushes now
also trigger it so branch work gets feedback before a PR exists. `main` stays
out of the push trigger, which avoids duplicate status contexts on the protected
branch. Stale PR runs are also canceled automatically with GitHub Actions
concurrency.

The workflow is now path-aware:

- backend-heavy work runs only when backend or contract files change
- frontend-heavy work runs only when frontend or contract files change
- docs/workflow consistency checks run on docs-oriented pull requests
- PRs into `main` still receive the full validation set
- contract-boundary edits on `main` PRs are expected to come with matching
  tests and the owning docs update

The CI hardening owner is:

- `.github/ci_test_targets.json`
  - owner of the shared CI target groups used by workflow and policy consumers

Supporting scripts:

- `.github/scripts/ci_target_manifest.py`
  - shared manifest model and loading seam used by every Python-side CI target
    consumer
  - also exposes the shared manifest-group access seam used by
    `check_main_pr_consistency.py`
- `.github/scripts/validate_ci_test_targets.py`
  - validates manifest structure, ownership boundary, and target hygiene
- `.github/scripts/read_ci_test_targets.py`
  - resolves one stable target group for workflow shell steps
- `.github/scripts/check_ci_target_drift.py`
  - checks workflow, policy, and docs alignment with the manifest

The chosen manifest format is JSON. That keeps the source of truth easy to read
in Python tooling and straightforward to consume from workflow shell steps via
`python3`, without coupling the repo to an extra YAML parser or to a Python-only
module import seam.

Stable target groups:

- `backend_contract`
- `mcp_fastapi_parity`
- `frontend_contract`
- `weekly_slow_media`
- `weekly_api_stream_deep`
- `weekly_lifecycle`

Reader example:

```bash
python3 .github/scripts/read_ci_test_targets.py backend_contract --separator space
```

Workflow consumers:

- `test-and-build`
  - backend contract checks read `backend_contract` and `mcp_fastapi_parity`
  - frontend contract checks read `frontend_contract`
  - the job now validates the manifest boundary before resolving those groups
- `weekly-validation`
  - slow media reads `weekly_slow_media`
  - deeper `api_stream` validation reads `weekly_api_stream_deep`
  - lifecycle validation reads `weekly_lifecycle`
  - each weekly heavy job now validates the manifest boundary before resolving
    its target group

Ownership summary:

- the manifest owns the shared CI target groups
- `.github/scripts/check_main_pr_consistency.py` owns the narrower main-PR
  policy layer
- the policy layer keeps only:
  - gate activation rules
  - docs expectations
  - policy-only test expectations that are intentionally narrower than the
    shared CI groups

Policy consumer:

- backend contract gate reuses:
  - `backend_contract`
  - `mcp_fastapi_parity`
- frontend bridge gate reuses:
  - `frontend_contract`
- electron trust/playback stays local-only until the repo gives it a shared
  CI target group
- each policy gate now reads as:
  - label
  - changed paths
  - manifest groups
  - policy-only tests
  - docs expectations
- that keeps the script narrower than the workflow lanes it references, so it
  does not become a second target manifest

Manifest protection:

- required stable groups must be present and non-empty
- referenced target files must exist in the repo
- duplicate target paths are rejected
- a small denylist of retired split-test file names is rejected explicitly

Drift protection:

- `.github/scripts/check_ci_target_drift.py`
  - compares manifest groups, workflow usage, consistency-script usage, and
    CI-facing docs references
  - verifies that the main PR consistency policy consumes the same stable
    manifest groups as the main workflow contract lane
  - protects the ownership split between shared target data and narrower
    policy logic

Consistency-job order:

1. manifest validation
2. CI target drift check
3. manifest-backed main PR gate policy check

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
pytest -q -m "not e2e and not slow"
```

This default backend command keeps the normal local fast lane focused on unit,
service, and boundary coverage. Use the dedicated e2e commands below when you
want the snapshot-contract smoke check or the slower real-media matrix.

Focused repo-local skill validation:

```bash
.venv/bin/pytest -q tests/test_repo_skills.py
```

This skill-focused test slice is intentionally no-key and deterministic.
It currently covers:

- skill frontmatter and required section structure
- readable section ordering
- explicit hand-off boundaries between the skills
- golden scenario coverage for current repo use cases
- snapshot-style expected outputs for selected fixed prompts
- lightweight regression coverage for real repo incidents

Focused alert-query, incident, and MCP validation:

```bash
.venv/bin/pytest -q tests/test_api_auth.py tests/test_api_rate_limit.py tests/test_api_boundary_settings_env.py tests/test_api_boundary_settings_validation.py tests/test_api_boundary_error_contracts.py tests/test_api_server_cli_runtime.py tests/test_api_server_cli_routes.py tests/test_api_server_cli_output.py tests/test_api_alert_route_auth_policy.py tests/test_api_alert_route_rate_limit_policy.py tests/test_api_alert_route_contracts.py tests/test_alert_query_service_read.py tests/test_alert_query_service_filter.py tests/test_alert_query_service_summary.py tests/test_alert_timeline_service_grouping.py tests/test_alert_timeline_service_filters.py tests/test_alert_incident_summary_service_contracts.py tests/test_alert_incident_summary_service_filters.py tests/test_api_session_alerts.py tests/test_api_session_alert_incidents.py tests/test_mcp_server_contracts.py tests/test_mcp_server_alerts_behavior.py tests/test_mcp_server_alerts_errors.py tests/test_mcp_fastapi_boundary_split.py tests/test_mcp_fastapi_parity_behavior.py tests/test_mcp_fastapi_parity_edges.py tests/test_mcp_server_incidents_behavior.py tests/test_mcp_server_incidents_errors.py
```

This slice covers the shared read-only alert query service, the FastAPI alerts
boundary, and the MCP adapter over the same service seam. If you change only
one of those layers, this is still the best quick confidence check because it
proves the ownership split still lines up.

The fast backend CI lane intentionally stays synthetic and contract-focused.
The real-media `ffmpeg`/`ffprobe` fixture coverage lives in the slower weekly
e2e validation path rather than in the normal branch-push backend test job.
The same weekly validation workflow also owns the heavier confidence-building
checks for:

- real-media detector integration
- deeper `api_stream` validation
- lifecycle-focused backend regression slices
- security audits
- dependency consistency audits

It exercises the current alerts-router protection contract end to end:

- `local` mode defaults keep auth and rate limiting off
- `share` mode defaults turn auth and rate limiting on
- share mode can auto-generate one startup API key when none is configured
- protected scope
- structured `401` and `429` responses
- local in-memory/per-process limiter behavior
- coarse `Retry-After` behavior on `429`

Treat that as strong confidence for the current local/demo readiness level,
not as proof of a distributed shared-store deployment model.

The current functionality under that slice is:

- FastAPI API-key authentication seam for the alerts router
- FastAPI in-memory principal-aware rate-limiting seam for the alerts router
- raw session alert list queries
- raw numeric alert summaries
- grouped incident timelines
- grouped incident summaries
- stdio MCP launch wiring over the same shared service seam

The current test split is:

- `tests/session_alert_test_support.py`
  - shared file-backed session/alert setup helpers for this slice
- `tests/api_alert_test_support.py`
  - shared FastAPI alert-route payload builders plus boundary setup helpers for
    auth, limiter, and simple successful route responses
- `tests/mcp_alert_test_support.py`
  - shared in-memory MCP session helpers for the alert-tool tests
- `tests/alert_query_service_test_support.py`
  - tiny shared setup helpers for the split raw alert query service suites
- `tests/alert_incident_service_test_support.py`
  - tiny shared typed-access and empty-result helpers for the split grouped
    incident timeline and summary suites
- `tests/test_alert_query_service_read.py`
  - service-level persisted alert-log read semantics, corrupt/unreadable input
    tolerance, and missing/orphaned session handling
- `tests/test_alert_query_service_filter.py`
  - raw filtered alert semantics, including invalid time-filter validation,
    inclusive/open-ended time-range behavior, persisted ordering, unknown-filter
    empty results, and filtered-entrypoint missing-session failures
- `tests/test_alert_query_service_summary.py`
  - numeric raw alert summary semantics, summary-specific validation, empty
    summary behavior, and summary-entrypoint missing-session failures
- `tests/test_api_auth.py`
  - auth-boundary unit coverage for enabled/disabled auth, missing keys,
    invalid keys, blank headers, and unsupported modes
- `tests/test_api_rate_limit.py`
  - limiter unit coverage for fixed-window counting, principal separation,
    window reset, and IP-strategy subject building
- `tests/test_api_boundary_settings_env.py`
  - env parsing, run-mode defaults, and share-mode API-key generation coverage
- `tests/test_api_boundary_settings_validation.py`
  - direct validator coverage plus FastAPI startup validation integration
- `tests/test_api_boundary_error_contracts.py`
  - non-429 FastAPI boundary error-header regression coverage
- `tests/test_api_server_cli_runtime.py`
  - explicit `local`/`share` CLI runtime preparation, overrides, generated-key
    flow, fail-fast behavior, and CLI-only boundary posture decisions before
    any HTTP request exists
- `tests/test_api_server_cli_routes.py`
  - real alerts-router behavior under CLI-prepared `local` and `share` mode,
    including open local access, `401`, `429`, and proof that CLI-prepared
    share mode does not widen protection to public routes
  - also locks down that `/openapi.json` and `/detectors` remain outside the
    current alerts-router auth boundary
  - keeps generated-key and manual-key access aligned across more than one
    protected alerts route shape
- `tests/test_api_server_cli_output.py`
  - startup summary output, generated-key guidance, manual-key non-leakage,
    and operator-facing `share` versus `local` startup distinction
  - also covers custom host/port reflection for both manual `share` and `local`
    startup paths
- `tests/test_api_alert_route_auth_policy.py`
  - shared FastAPI alerts-router authentication policy, stable `401`
    behavior, cross-route invalid/missing-key consistency, and proof that the
    alerts-router auth boundary does not become app-wide policy
- `tests/test_api_alert_route_rate_limit_policy.py`
  - shared FastAPI alerts-router limiter behavior, logging, budget-sharing
    policy, stable `429` plus `Retry-After`, and proof that unrelated public
    routes stay usable after protected route throttling
- `tests/test_api_alert_route_contracts.py`
  - shared FastAPI alerts-router `429` response shaping and OpenAPI contract coverage
- `tests/test_alert_timeline_service_grouping.py`
  - service-level grouped timeline semantics for merge and non-merge rules,
    chronological ordering, deterministic same-timestamp tie-breaking, stable
    grouped `source_names`, transitive adjacent grouping, malformed-row
    degradation, and a light scaling guard
- `tests/test_alert_timeline_service_filters.py`
  - service-level grouped timeline filter reuse before grouping, invalid and
    inverted time-filter validation, missing-session failures, unknown-filter
    empty results, inclusive/open-ended time bounds, and time-filter handling
    for rows with unusable timestamps
- `tests/test_alert_incident_summary_service_contracts.py`
  - service-level grouped incident summary counts, categories, narrative
    shaping, deterministic tie-breaking, malformed-row degradation, and
    raw-versus-grouped count separation when some rows cannot form incidents
- `tests/test_alert_incident_summary_service_filters.py`
  - service-level grouped incident summary filter reuse, filtered-empty
    summaries, invalid and inverted time-filter validation, missing-session
    failures, and unknown-filter empty grouped summaries
- `tests/test_api_session_alerts.py`
  - FastAPI adapter behavior for raw alert list and summary routes
  - includes stable empty-result envelopes and filter-forwarding coverage
- `tests/test_api_session_alert_incidents.py`
  - FastAPI adapter behavior for timeline and grouped incident summary routes
  - includes stable empty-result envelopes and grouped filter-forwarding coverage
- `tests/test_mcp_server_contracts.py`
  - structural MCP registration and launch-wiring coverage, including stable
    tool names/count, read-only server instructions, schema basics, and stdio
    launch wiring
- `tests/mcp_server_alerts_test_support.py`
  - tiny shared setup and result helpers for the split raw MCP behavior/error suites
  - intentionally limited to filesystem seams plus success/error assertion helpers
- `tests/test_mcp_server_alerts_behavior.py`
  - MCP raw alert-query and raw-summary behavior through the real in-memory MCP session
  - includes known-session empty payloads, filtered raw MCP list/summary alignment,
    and raw unknown-filter empty payloads
  - keeps usable payload behavior separate from MCP-facing error translation
- `tests/test_mcp_server_alerts_errors.py`
  - raw MCP tool-level error mapping
  - includes missing-session failures, invalid time-range failures, and combined
    raw invalid-timestamp parity
  - keeps raw MCP list/summary error translation parity explicit
- `tests/mcp_fastapi_parity_test_support.py`
  - tiny shared setup, fetch, and meaning-level assertion helpers for the split
    FastAPI/MCP parity suites
  - intentionally limited to protected FastAPI route setup, parity fixture
    setup, and cross-surface meaning plumbing
- `tests/test_mcp_fastapi_boundary_split.py`
  - explicit FastAPI-versus-stdio MCP trust-boundary and cross-surface smoke coverage
  - keeps the raw MCP boundary checks grouped together and the grouped MCP
    boundary checks grouped together so the trust rule is easier to review
  - includes the regression that FastAPI `share` CLI runtime preparation must
    not pull stdio MCP raw or grouped tools into the HTTP auth/rate-limit boundary
  - also keeps raw MCP list/summary tools grouped together under direct FastAPI
    auth/rate-limit boundary checks
  - and keeps grouped MCP tools usable even when both `share` prep and direct
    FastAPI protections are applied before the MCP read
- `tests/test_mcp_fastapi_parity_behavior.py`
  - FastAPI/MCP meaning parity for normal shared-fixture reads
  - includes unfiltered and filtered raw/grouped reads, known empty sessions,
    unknown-filter no-match reads, and one shared time-bounded slice
  - keeps ordinary parity scenarios separate from validation and ordering edges
- `tests/test_mcp_fastapi_parity_edges.py`
  - FastAPI/MCP meaning parity for validation and ordering edges
  - includes invalid time-filter validation, inverted ranges, inclusive and
    open-ended time bounds, and same-timestamp grouped ordering
  - keeps the higher-risk boundary and ordering seams separate from ordinary
    parity behavior
- `tests/mcp_server_incidents_test_support.py`
  - tiny shared setup and result helpers for the split grouped MCP behavior/error suites
  - intentionally limited to grouped-session setup plus success/error assertion helpers
- `tests/test_mcp_server_incidents_behavior.py`
  - MCP grouped timeline and incident-summary behavior
  - includes known-session empty grouped payloads, filtered grouped MCP alignment,
    and unknown-filter empty grouped payloads
  - keeps grouped payload behavior separate from grouped MCP error translation
- `tests/test_mcp_server_incidents_errors.py`
  - grouped MCP tool-level error mapping
  - includes missing-session failures plus grouped invalid time-range and
    invalid timestamp-format parity
  - keeps grouped timeline/summary error translation parity explicit

Keep new tests near those ownership boundaries instead of adding a larger
catch-all alert-query suite.

The split is deliberate:

- service files prove the durable file-backed semantics once
- auth unit files prove API-key validation and auth-mode behavior before the
  HTTP adapter layer is involved
- rate-limit unit files prove fixed-window counting semantics before the HTTP
  adapter layer is involved
- `tests/api_alert_test_support.py` keeps the route-policy files small by
  owning the repeated alert-route setup seams rather than leaving each policy
  file to build its own tiny test framework
- the alerts-router HTTP protection composition lives in
  `src/api/alert_route_policy.py`, so route tests patch the boundary seam there
  rather than duplicating auth/rate-limit behavior inside route functions
- route-policy files prove router-scoped auth and limiter behavior once across
  the protected alerts surface, but are now split so authentication policy,
  limiter policy, and client-visible response contracts each have one obvious home
- route-policy files also lock down the current limiter identity rule:
  principal-by-default, optional IP strategy, and local fallback when auth is
  disabled
- FastAPI files prove HTTP parameter binding and error mapping
- MCP files prove tool registration, launch wiring, and behavior through the
  real in-memory MCP transport seam
- the FastAPI-versus-MCP boundary-split file keeps the current local-trust
  stdio story explicit without cluttering the raw MCP tool behavior files
- the raw and grouped MCP behavior files now also lock the no-data and
  filtered-data tool payloads to the same shared service contracts used by
  FastAPI

When you add new coverage for this slice, prefer extending the narrow owning
file over creating another mixed alert-and-incident test module.

Focused MCP launch wiring:

```bash
.venv/bin/esm-mcp
```

Raw-checkout equivalent:

```bash
PYTHONPATH=src .venv/bin/python -m esm_mcp
```

Both start the current MCP server over `stdio`, which is the intended local
client transport for the current project stage.
The installed `esm-mcp` entrypoint is available after refreshing the editable
environment (for example with `uv sync` or a fresh editable install). Use the
module form when you want a raw-checkout path that does not depend on the
console script already existing in `.venv/bin/`.

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

If you are validating the MCP slice specifically, include the new shared
service and MCP adapter in the import smoke check:

```bash
PYTHONPATH=src .venv/bin/python -c "import api.app, session_alerts, session_alert_incidents, esm_mcp.server"
```

For a slightly stronger launch-path smoke check, verify the installed console
entrypoint resolves:

```bash
.venv/bin/python -c "import esm_mcp.server; print(callable(esm_mcp.server.main))"
```

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

### Repo-Local Skill Tests

The repo-local Codex skills under `./.agents/skills/` are validated with a
small deterministic Python slice rather than live model calls.

Current test files:

- `tests/test_repo_skills.py`
  - structure, skill-boundary, scenario, and snapshot checks
- `tests/skill_test_support.py`
  - parsing and reusable test helpers
- `tests/fixtures/skill_output_snapshots/`
  - saved expected output templates for selected prompts

This keeps the skill layer cheap to validate and easy to evolve while the
project is still in a local-first pre-pilot stage.

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
- `tests/test_api_boundary_sessions_read.py`
  - session read-route behavior
- `tests/test_api_boundary_sessions_start.py`
  - session start-route behavior
- `tests/test_api_boundary_sessions_cancel.py`
  - session cancel-route behavior
- `tests/test_session_service_start.py`
  - shared start-session service behavior
- `tests/test_session_service_worker.py`
  - detached worker launch and log-handle behavior
- `tests/test_session_service_read_cancel.py`
  - shared read/cancel service behavior
- `tests/test_session_cli_tooling.py`
  - CLI adapter behavior over the shared session service
- `tests/test_api_boundary_contracts.py`
  - structured API error payloads
  - populated session snapshot response shape
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
- `tests/test_stream_loader_http_hls_reconnect_recovery.py`
  - reconnect recovery, resumed progression, and temporary outage behavior
- `tests/test_stream_loader_http_hls_reconnect_state.py`
  - reconnect budgets, replay de-duplication state, and reconnect logging behavior
- `tests/test_stream_loader_http_hls_limits_runtime.py`
  - runtime and refresh-budget enforcement plus shutdown behavior
- `tests/test_stream_loader_http_hls_limits_cleanup.py`
  - temp-state, cleanup, and storage-budget guarantees
- `tests/test_stream_loader_http_hls_limits_restart.py`
  - soak, restart, and dedup-resume behavior
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
- `frontend/src/bridge/contract.session-snapshot.shape.test.ts`
  - required session snapshot shape and lifecycle field preservation
- `frontend/src/bridge/contract.session-snapshot.malformed.test.ts`
  - fail-closed malformed nested payload handling
- `frontend/src/bridge/contract.session-snapshot.collections.test.ts`
  - partially corrupt alert/result collection compatibility
- `frontend/src/bridge/transport.test.ts`
  - transport selection and demo fallback behavior
- `frontend/src/components/SessionStatusPanel.test.tsx`
  - operator-facing lifecycle, reconnect, and playback-diagnostic wording
- `frontend/src/presenters/alertFeed.test.ts`
  - playback-aware alert feed reveal timing and timestamp labels
- `frontend/src/uiErrors.test.ts`
  - operator-facing error wording
  - `api_stream` status/error interpretation
- `frontend/src/hooks/useMonitoringSession.lifecycle.test.tsx`
  - hook behavior for local lifecycle polling, cancel-state transitions, and typed failures
- `frontend/src/hooks/useMonitoringSession.apiStream.test.tsx`
  - hook behavior for `api_stream` reconnect, recovery, and terminal polling semantics
- `frontend/src/hooks/usePlaybackSource.test.tsx`
  - hook behavior on top of normalized playback-source resolution
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
PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/pytest -p no:cacheprovider \
  tests/test_session_service_start.py \
  tests/test_session_service_worker.py \
  tests/test_session_service_read_cancel.py \
  tests/test_api_boundary_sessions_read.py \
  tests/test_api_boundary_sessions_start.py \
  tests/test_api_boundary_sessions_cancel.py \
  tests/test_session_cli_tooling.py -q
```

Use that command first for worker-observability changes. It covers:

- shared worker-launch behavior in `session_service.py`
- the current API rule that diagnostics stay backend-owned
- CLI-side worker failure logging behavior

### Legacy Seam Replacement

For the demoted legacy `src/main.py` seam, the intended replacement is focused
pytest coverage rather than a new manual tooling script. The main local
confidence replacements are:

- `tests/test_processor_routing.py`
- `tests/test_processor_failures.py`
- `tests/test_processor_context_alerts.py`
- `tests/test_session_runner_local.py`
- `tests/test_e2e_local_session.py`

```bash
PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/pytest -p no:cacheprovider tests/test_api_boundary_*.py -q
```

```bash
cd frontend
npm run test -- src/bridge/contract.success.test.ts src/bridge/contract.errors.test.ts src/bridge/contract.session-snapshot.shape.test.ts src/bridge/contract.session-snapshot.malformed.test.ts src/bridge/contract.session-snapshot.collections.test.ts src/uiErrors.test.ts
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
2. `tests/test_session_runner_execution_local.py`
3. `tests/test_session_runner_execution_api_stream.py`
4. `tests/test_session_runner_terminal.py`
5. `tests/test_session_runner_local.py`
6. `tests/test_session_runner_api_stream_progress.py`
7. `tests/test_session_runner_api_stream_http_hls_lifecycle.py` in a normal local shell when loopback sockets are available
8. `tests/test_session_runner_api_stream_http_hls_failures.py` in a normal local shell when loopback sockets are available

## Lifecycle Coverage Audit

Current lifecycle coverage is already spread across the main layers:

- backend tests
  - `tests/test_session_runner_lifecycle.py`
    - pending-session setup
    - pending-to-running transition semantics
    - smallest helper-level seam for session setup and status transitions
  - `tests/test_session_runner_execution_local.py`
    - extracted local execution-loop helper behavior
    - analyzer-bundle invocation and local event-persistence seams
  - `tests/test_session_runner_execution_api_stream.py`
    - extracted live `api_stream` execution-loop helper behavior
    - api-stream cleanup accounting and live helper wiring seams
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
  - `tests/test_session_runner_api_stream_progress.py`
    - seam-loader `api_stream` progress-shaping, repeated temporary failure
      tolerance, alert re-entry, and multi-detector live coherence
  - `tests/test_session_runner_api_stream_http_hls_lifecycle.py`
    - real HTTP/HLS-backed `api_stream` transport and lifecycle integration
    - keep this as the signoff suite when a change touches successful real HTTP/HLS progression
  - `tests/test_session_runner_api_stream_http_hls_failures.py`
    - real HTTP/HLS-backed failure persistence, partial-progress, and budget exhaustion coverage
  - `tests/test_session_io.py`
    - invalid terminal transitions
    - completed-progress consistency checks
- FastAPI boundary tests
  - `tests/test_api_boundary_validation.py`
    - request validation failures
  - `tests/test_api_boundary_sessions_read.py`
    - missing-session reads
    - populated session snapshot passthrough behavior
  - `tests/test_api_boundary_sessions_start.py`
    - start success and shared error mapping
  - `tests/test_api_boundary_sessions_cancel.py`
    - cancel success, missing-session cancel failure, and current terminal cancel behavior
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
  - `frontend/src/App.pollingStatus.local.test.tsx`
    - running-to-completed polling flow
  - `frontend/src/App.pollingStatus.apiStream.test.tsx`
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
