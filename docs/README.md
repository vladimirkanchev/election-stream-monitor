# Docs Index

This folder is the internal reference set for contributors, reviewers, and
people using AI-assisted tools for coding and development. Use it as the
intent layer for the current repo state, not as end-user documentation.

## Best First Reads

If you are new to the repo, read these in order:

1. [../NEXT_SESSION.md](../NEXT_SESSION.md) if you are returning after a break
2. [architecture.md](./architecture.md)
3. [contracts.md](./contracts.md)
4. [session-model.md](./session-model.md)
5. then the task-specific doc for the subsystem you want to change

## Best Entry Points For Coding Agents

Use this shortcut map before editing code:

- changing session snapshot or polling behavior:
  - [session-model.md](./session-model.md)
  - [contracts.md](./contracts.md)
  - [architecture.md](./architecture.md)
- changing frontend bridge normalization or UI transport handling:
  - [frontend-architecture.md](./frontend-architecture.md)
  - [contracts.md](./contracts.md)
  - [testing-and-validation.md](./testing-and-validation.md)
- changing FastAPI endpoints or response semantics:
  - [fastapi-boundary.md](./fastapi-boundary.md)
  - [architecture-decision-fastapi.md](./architecture-decision-fastapi.md)
  - [contracts.md](./contracts.md)
  - read `fastapi-boundary.md` first if the change touches auth, rate
    limiting, or current readiness expectations for the alerts router
  - current CLI-oriented FastAPI boundary checks live mainly in:
    - `tests/test_api_server_cli_runtime.py`
    - `tests/test_api_server_cli_output.py`
    - `tests/test_api_server_cli_routes.py`
- changing MCP alert-query tools or local MCP launch wiring:
  - [architecture.md](./architecture.md)
  - [contracts.md](./contracts.md)
  - [mcp-server.md](./mcp-server.md)
  - [testing-and-validation.md](./testing-and-validation.md)
  - [fastapi-boundary.md](./fastapi-boundary.md)
  - `src/api_auth.py`
  - `src/api_rate_limit.py`
  - `src/api/alert_route_policy.py`
  - `src/esm_mcp/`
  - `src/session_alert_store.py`
  - `src/session_alert_store_postgres.py`
  - `src/session_alert_store_postgres_config.py`
  - `src/session_alerts.py`
  - `src/session_alert_incidents.py`
- adding a detector:
  - [adding-an-analyzer.md](./adding-an-analyzer.md)
- adding an alert rule:
  - [adding-an-alert-rule.md](./adding-an-alert-rule.md)
- working on repo-local Codex skills or their tests:
  - [testing-and-validation.md](./testing-and-validation.md)
  - `./.agents/skills/`
  - `tests/test_repo_skills.py`
- changing CI ownership rules, target manifests, or split-suite registration:
  - [ci-maintainer-guide.md](./ci-maintainer-guide.md)
  - [testing-and-validation.md](./testing-and-validation.md)

## Current High-Signal Code Areas

If you want the shortest path into the current repo shape, start with these
module families and the matching tests:

- session lifecycle and persistence:
  - `src/session_service.py`
  - `src/api/routers/sessions.py`
  - `src/session_cli.py`
  - `src/session_runner.py`
  - `src/session_runner_lifecycle.py`
  - `src/session_runner_execution.py`
  - `src/session_runner_terminal.py`
  - `src/session_runner_discovery.py`
  - `src/session_runner_progress.py`
  - `tests/test_session_service_start.py`
  - `tests/test_session_service_worker.py`
  - `tests/test_session_service_read_cancel.py`
  - `tests/test_api_boundary_sessions_read.py`
  - `tests/test_api_boundary_sessions_start.py`
  - `tests/test_api_boundary_sessions_cancel.py`
  - `tests/test_session_cli_tooling.py`
  - `tests/test_session_runner_lifecycle.py`
  - `tests/test_session_runner_execution_local.py`
  - `tests/test_session_runner_execution_api_stream.py`
  - `tests/test_session_runner_terminal.py`
  - `tests/test_session_runner_local.py`
  - `tests/test_session_runner_api_stream_completion.py`
  - `tests/test_session_runner_api_stream_cancellation.py`
  - `tests/test_session_runner_api_stream_failures.py`
  - `tests/test_session_runner_api_stream_progress.py`
  - `tests/test_session_runner_api_stream_http_hls_lifecycle.py`
  - `tests/test_session_runner_api_stream_http_hls_failures.py`
  - read the session-service files first, then the runner files, if you want
    the shortest path into the current session lifecycle split
- live `api_stream` loading:
  - `src/stream_loader.py`
  - `src/stream_loader_contracts.py`
  - `src/stream_loader_http_hls.py`
  - `src/stream_loader_fakes.py`
  - `tests/test_stream_loader_contracts.py`
  - `tests/test_stream_loader_http_hls_core_playlist.py`
  - `tests/test_stream_loader_http_hls_core_progression.py`
  - `tests/test_stream_loader_http_hls_core_provider.py`
  - `tests/test_stream_loader_http_hls_reconnect_recovery.py`
  - `tests/test_stream_loader_http_hls_reconnect_state.py`
  - `tests/test_stream_loader_http_hls_limits_runtime.py`
  - `tests/test_stream_loader_http_hls_limits_cleanup.py`
  - `tests/test_stream_loader_http_hls_limits_restart.py`
- Electron/FastAPI desktop runtime:
  - `frontend/electron/main.mjs`
  - `frontend/electron/fastApiStartupOrchestrator.mjs`
  - `frontend/electron/fastApiRuntimePolicy.mjs`
  - `frontend/electron/fastApiProcessManager.mjs`
  - `frontend/electron/bridgeHandlerRegistry.mjs`
  - `frontend/electron/localMediaRequestPolicy.mjs`
  - `frontend/electron/localMediaResponses.mjs`
- frontend bridge normalization:
  - `frontend/src/bridge/contract.ts`
  - `frontend/src/bridge/contractErrors.ts`
  - `frontend/src/bridge/contractDetectors.ts`
  - `frontend/src/bridge/contractSessionSnapshot.ts`
  - `frontend/src/bridge/transport.ts`
  - `frontend/src/bridge/contract.testSupport.ts`
  - `frontend/src/bridge/contract.success.test.ts`
  - `frontend/src/bridge/contract.errors.test.ts`
  - `frontend/src/bridge/contract.session-snapshot.shape.test.ts`
  - `frontend/src/bridge/contract.session-snapshot.malformed.test.ts`
  - `frontend/src/bridge/contract.session-snapshot.collections.test.ts`
- frontend operator state presentation:
  - `frontend/src/components/SessionStatusPanel.tsx`
  - `frontend/src/components/SessionStatusPanel.test.tsx`
  - `frontend/src/presenters/alertFeed.ts`
  - `frontend/src/presenters/alertFeed.test.ts`
- MCP alert-query surface:
  - `src/api_auth.py`
  - `src/api_rate_limit.py`
  - `src/api/alert_route_policy.py`
  - `src/session_alert_store.py`
  - `src/session_alerts.py`
  - `src/session_alert_incidents.py`
  - `src/session_alert_adapter.py`
  - `src/session_alert_store_runtime_config.py`
    - explicit runtime selection for the default alert store:
      `ESM_ALERT_STORE_BACKEND=file|postgres`
  - `src/session_alert_store_postgres.py`
    - concrete PostgreSQL alert backend plus schema/bootstrap helpers
  - `src/session_alert_store_postgres_config.py`
    - narrow env/config parsing for the PostgreSQL alert-store bootstrap path
  - `src/session_io.py`
  - `src/api/schemas.py`
  - `src/api/routers/alerts.py`
  - `src/esm_mcp/server.py`
  - `src/esm_mcp/alert_tools.py`
  - `tests/session_alert_test_support.py`
  - `tests/api_alert_test_support.py`
  - `tests/mcp_alert_test_support.py`
  - `tests/test_session_alert_store.py`
    - file-backed seam contract for the current default alert store
  - `tests/test_session_alert_store_runtime.py`
    - runtime backend selection plus caller-stability coverage for the default
      alert seam
  - `tests/test_session_alert_store_runtime_config.py`
    - explicit `file` versus `postgres` backend-mode config coverage
  - `tests/test_session_alert_store_parity.py`
    - file-store versus PostgreSQL-store parity over the shared alert seam and
      read-model layer
  - `tests/test_session_alert_store_postgres.py`
    - PostgreSQL alert-store contract for schema/bootstrap plus the concrete
      second backend's read/write drift-sensitive behavior
  - `tests/test_session_alert_store_postgres_config.py`
    - narrow env/config coverage for the PostgreSQL alert-store bootstrap path
  - `tests/test_session_io.py`
    - compatibility write-entry and write-to-read seam coverage
  - `tests/test_session_runner_execution_local.py`
    - local execution-path coverage for runner-written alerts through the seam
  - `tests/test_api_auth.py`
  - `tests/test_api_rate_limit.py`
  - `tests/test_api_alert_route_auth_policy.py`
    - router-scoped `401` policy, invalid/missing-key consistency, and
      protected-versus-public route scope
  - `tests/test_api_alert_route_rate_limit_policy.py`
    - router-scoped limiter policy, stable `429` plus `Retry-After`, and proof
      that public routes remain usable after protected-route throttling
  - `tests/test_api_alert_route_contracts.py`
  - `tests/test_alert_query_service_read.py`
    - shared raw alert-log read semantics and degradation on corrupt or
      unreadable persisted input
  - `tests/test_alert_query_service_filter.py`
    - shared raw filtered alert semantics, including invalid time-filter
      validation, inclusive/open-ended time bounds, ordering, and
      missing-session failures
  - `tests/test_alert_query_service_summary.py`
    - shared raw numeric alert summary semantics, including empty-summary
      behavior, timestamp-bound handling, and summary-specific validation
  - `tests/alert_incident_service_test_support.py`
    - tiny shared typed-access, stable empty-result, and time-filter helper
      seams for the split grouped incident suites
  - `tests/test_alert_timeline_service_grouping.py`
    - grouped incident timeline semantics for merge and non-merge rules,
      deterministic ordering, stable grouped `source_names`, transitive
      adjacent grouping, malformed-row degradation, and a light scaling guard
  - `tests/test_alert_timeline_service_filters.py`
    - grouped incident timeline filter and validation semantics, including
      raw-filter reuse before grouping, invalid and inverted time filters,
      missing sessions, unknown-filter empty results, and inclusive/open-ended
      time bounds
  - `tests/test_alert_incident_summary_service_contracts.py`
    - grouped incident summary semantics for counts, categories, narrative
      shaping, deterministic tie-breaking, and explicit raw-versus-grouped
      count separation when some rows cannot form incidents cleanly
  - `tests/test_alert_incident_summary_service_filters.py`
    - grouped incident summary filter and validation semantics, including
      filtered-empty grouped results, invalid and inverted time filters,
      missing sessions, and unknown-filter empty grouped summaries
  - `tests/test_api_session_alerts.py`
  - `tests/test_api_session_alert_incidents.py`
  - `tests/test_mcp_server_contracts.py`
  - `tests/test_mcp_server_alerts_behavior.py`
  - `tests/test_mcp_server_alerts_errors.py`
  - `tests/test_mcp_fastapi_boundary_split.py`
  - `tests/test_mcp_fastapi_parity_behavior.py`
  - `tests/test_mcp_fastapi_parity_edges.py`
  - `tests/test_mcp_server_incidents_behavior.py`
  - `tests/test_mcp_server_incidents_errors.py`
  - read them in that order if you want the cleanest path from the shared
    alert store seam and raw/grouped services to HTTP and MCP adapters
  - `tests/test_mcp_server_alerts_behavior.py` owns raw MCP no-alert,
    filtered-data, and unknown-filter empty behavior, with payload-shaping
    expectations kept separate from MCP-facing error translation
  - `tests/test_mcp_server_alerts_errors.py` owns raw MCP missing-session,
    invalid-range, and invalid-timestamp error mapping
  - `tests/test_mcp_server_incidents_behavior.py` owns grouped MCP no-alert,
    filtered-data, and unknown-filter empty behavior, with grouped output
    shaping kept separate from grouped MCP error translation
  - `tests/test_mcp_server_incidents_errors.py` owns grouped MCP missing-session,
    invalid-range, and invalid-timestamp error mapping
  - `tests/api_alert_test_support.py` owns the repeated FastAPI alerts-router
    setup seams
  - `tests/test_mcp_fastapi_boundary_split.py` owns the current
    “FastAPI protected, stdio MCP local-trust” boundary rule, including grouped
    MCP tools under `share`, the combined raw list/summary direct-boundary
    check, the stronger grouped `share` plus direct-protection regression, and
    the small cross-surface smoke path where protected HTTP and local MCP read
    the same persisted alert data together
  - `tests/mcp_fastapi_parity_test_support.py` owns the tiny shared setup and
    parity-assertion seams for the split FastAPI/MCP parity suites
  - it is intentionally limited to protected-route setup, persisted parity
    fixture setup, and cross-surface meaning helpers
  - `tests/test_mcp_fastapi_parity_behavior.py` owns the current normal
    FastAPI/MCP parity slice for one shared fixture session across raw alert
    totals and grouped incident totals
  - that parity slice includes filtered reads, known empty sessions,
    unknown-filter no-match reads, and one shared time-bounded query
  - `tests/test_mcp_fastapi_parity_edges.py` owns the current validation and
    ordering parity slice, including invalid time-filter validation,
    inverted ranges, inclusive/open-ended time bounds, and same-timestamp
    grouped ordering
  - `tests/test_mcp_server_contracts.py` also keeps one explicit “exactly four
    current tools” guard for the read-only MCP surface, alongside the
    structural registration, schema, and stdio launch-wiring checks
  - CI ownership now centers on `.github/ci_test_targets.json` and the shared
    Python seam in `.github/scripts/ci_target_manifest.py`
  - `.github/scripts/check_main_pr_consistency.py` owns the narrower main-PR
    policy layer
  - `.github/scripts/check_ci_target_drift.py` is the high-signal drift guard
    for workflow, policy, and CI-facing docs
  - use [ci-maintainer-guide.md](./ci-maintainer-guide.md) for the short CI
    ownership handoff
  - use [testing-and-validation.md](./testing-and-validation.md) for the full
    lane, filter, split-suite, and validation model

## Current Stable Contracts

At the current stage, treat these as stable unless you deliberately intend a
coordinated contract change:

- session snapshot shape
- frontend bridge normalization shape
- FastAPI structured error payload shape
- detector catalog shape

## Repo-Local Codex Skills

The repo also carries a small local skill set for AI-assisted diagnostic work:

- `./.agents/skills/summarization/`
- `./.agents/skills/incident-timeline/`
- `./.agents/skills/test-coverage-gaps/`
- `./.agents/skills/root-cause-suggestion/`

Treat these as lightweight workflow helpers for the current project stage.
They are intentionally small, text-first, and easy to extend without adding a
separate automation framework.

The deterministic tests for them live in:

- `tests/test_repo_skills.py`
- `tests/skill_test_support.py`
- `tests/fixtures/skill_output_snapshots/`

## Document Ownership

Use each doc for one main question:

- [architecture.md](./architecture.md)
  - system responsibilities
  - runtime boundaries
  - where a change belongs
- [contracts.md](./contracts.md)
  - stable payloads and bridge contracts
  - `api_stream` trust, failure, and playback contracts
- [session-model.md](./session-model.md)
  - persisted session files
  - lifecycle meaning
  - progress semantics
- [data-models.md](./data-models.md)
  - compact field guide for detector, alert, and session shapes
- [frontend-architecture.md](./frontend-architecture.md)
  - React/Electron split
  - playback state
  - frontend transport boundary
- [fastapi-boundary.md](./fastapi-boundary.md)
  - what a future FastAPI layer should own
  - what should stay local/runtime-specific
- [mcp-server.md](./mcp-server.md)
  - local MCP startup and connection details
  - current read-only/query-only MCP scope
- [testing-and-validation.md](./testing-and-validation.md)
  - routine verification commands
  - CI scope
  - manual vs automated validation
- [api-stream-local-validation.md](./api-stream-local-validation.md)
  - repeatable local `api_stream` trial workflow
  - expected status, logs, and cleanup
- [reviewer-guide.md](./reviewer-guide.md)
  - fastest review order
  - best feedback targets for the current project stage
- [release-versioning.md](./release-versioning.md)
  - `0.x` release expectations
- repo-local skill files under `./.agents/skills/`
  - concise AI workflow helpers for summarization, incident review, test-gap analysis, and root-cause narrowing

## Extension Guides

Use these when changing the detector/rule surface:

- [adding-an-analyzer.md](./adding-an-analyzer.md)
- [adding-an-alert-rule.md](./adding-an-alert-rule.md)
- [detector-template.md](./detector-template.md)

## Visual References

- [runtime-flow.svg](./runtime-flow.svg)
- [plugin-structure.svg](./plugin-structure.svg)
- [frontend-overview.svg](./frontend-overview.svg)
- [frontend-flow.svg](./frontend-flow.svg)
- [detector-and-alert-extension-flow.svg](./detector-and-alert-extension-flow.svg)

## Task-Based Reading Paths

If you are working on:

- transport / streaming
  - [architecture.md](./architecture.md)
  - [contracts.md](./contracts.md)
  - [testing-and-validation.md](./testing-and-validation.md)
- session lifecycle / persistence
  - [architecture.md](./architecture.md)
  - [session-model.md](./session-model.md)
  - [contracts.md](./contracts.md)
  - [testing-and-validation.md](./testing-and-validation.md)
- frontend playback / monitoring UX
  - [frontend-architecture.md](./frontend-architecture.md)
  - [contracts.md](./contracts.md)
  - [testing-and-validation.md](./testing-and-validation.md)
- Electron/FastAPI desktop runtime
  - [frontend-architecture.md](./frontend-architecture.md)
  - [architecture.md](./architecture.md)
  - [testing-and-validation.md](./testing-and-validation.md)
- detector or alert extension
  - [adding-an-analyzer.md](./adding-an-analyzer.md)
  - [adding-an-alert-rule.md](./adding-an-alert-rule.md)
  - [data-models.md](./data-models.md)
- review / onboarding
  - [reviewer-guide.md](./reviewer-guide.md)
  - [architecture.md](./architecture.md)
  - [contracts.md](./contracts.md)

## Update Rules

- Prefer code and tests as the final source of truth when a doc drifts.
- If you change a boundary, lifecycle meaning, or payload shape, update the
  matching doc in the same change.
- Avoid copying large blocks of guidance across files. Link to the owning doc
  instead.
