# Docs Index

This folder is the internal reference set for contributors, reviewers, and
people using AI-assisted tools for coding and development. Use it as the
maintainer view of the current repo state, not as end-user documentation.

If you want the gentlest product-level overview first, start with the root
[`README.md`](../README.md) and come back here for the maintainer view.

If you want the shortest contributor entrypoint for branch flow, local
commands, and docs ownership, start with [../CONTRIBUTING.md](../CONTRIBUTING.md).

Before running Python commands, prefer the repo-local interpreter or a `just`
recipe. This repo does not auto-activate `.venv`, so inherited shell state can
still point at another project's environment.

## Best First Reads

If you are new to the repo, read these in order:

1. [../NEXT_SESSION.md](../NEXT_SESSION.md) if you are returning after a break
2. [architecture.md](./architecture.md)
3. [contracts.md](./contracts.md)
4. [session-model.md](./session-model.md)
5. then the subsystem-specific doc you need for the change

## Quick Role Map

Use these first depending on what you are doing:

- understanding the current runtime
  - [architecture.md](./architecture.md)
  - [contracts.md](./contracts.md)
  - [session-model.md](./session-model.md)
- changing detectors or alert rules
  - [adding-an-analyzer.md](./adding-an-analyzer.md)
  - [adding-an-alert-rule.md](./adding-an-alert-rule.md)
  - treat `src/detectors/` as the canonical production detector package and
    `src/detectors/registry.py` as the canonical runtime registration owner
  - [`../detector_lab/README.md`](../detector_lab/README.md) for experimental work
  - use [adding-an-analyzer.md](./adding-an-analyzer.md) as the canonical
    promotion rule when an experiment may become supported runtime behavior
  - [detector-lab-analysis.md](./detector-lab-analysis.md) for the current detector-lab structure and evaluation intent
  - [motion-coherence.md](./motion-coherence.md) for the current motion-coherent blur experiment
  - [testing-and-validation.md](./testing-and-validation.md) for the focused production-vs-lab test split
  - high-signal test files:
    - `tests/test_analyzer_registry.py`
    - `tests/test_api_boundary_contracts.py`
    - `tests/test_session_cli_tooling.py`
    - `tests/test_export_detector_catalog.py`
    - `tests/test_detectors.py`
    - `tests/test_processor.py`
    - `tests/test_alert_rules.py`
    - `tests/test_alert_rules_black.py`
    - `tests/test_alert_rules_blur.py`
    - `tests/test_plugin_manifest_validation.py`
    - `tests/test_detector_lab.py`
- checking validation and CI expectations
  - [testing-and-validation.md](./testing-and-validation.md)
  - [ci-maintainer-guide.md](./ci-maintainer-guide.md)
  - [fixture-environment-policy.md](./fixture-environment-policy.md)
  - use the fixture/environment policy when deciding whether a path belongs in
    shared tests, local-only notes, or a slower explicit lane
- using the local developer workflow harness
  - use [../CONTRIBUTING.md](../CONTRIBUTING.md) first if you want the short
    version of branch flow, local commands, and docs ownership
  - [`../justfile`](../justfile)
  - treat the `justfile` as the canonical local command entrypoint for daily
    validation and developer-productivity lanes
  - harness shape:
    - `justfile` owns daily command entrypoints
    - `pre-commit` owns cheap commit-time hygiene only
    - `scripts/git-hooks/pre-push` is the optional last cheap local push guard
    - CI owns broader branch and weekly confidence
  - dependency metadata rule:
    - if `pyproject.toml` or `uv.lock` changes, explain why in the PR or commit
    - if it is unclear whether they belong, use
      `./.agents/skills/dependency-change-review/`
  - commit-message rule:
    - describe the actual change, not the branch purpose
    - keep one clear theme per commit when practical
    - prefer a short prefix such as `feat:`, `fix:`, `docs:`, `test:`, or `chore:`
  - [`../.pre-commit-config.yaml`](../.pre-commit-config.yaml) is the cheap
    local guardrail layer:
    - Ruff
    - trailing whitespace / EOF fixes
    - YAML / JSON / TOML validation
    - fixture/environment policy guard
  - [`../.editorconfig`](../.editorconfig) keeps whitespace, final newlines,
    and basic indentation consistent across Python, frontend files, and docs
  - [git-hooks.md](./git-hooks.md) explains the optional versioned `pre-push`
    hook and when to keep it narrow
  - Markdown policy:
    - keep it light
    - prefer clear headings, short lists, and one owner per topic
    - use existing `pre-commit` and `.editorconfig` guardrails instead of adding heavy Markdown enforcement
  - use [../CONTRIBUTING.md](../CONTRIBUTING.md) for the short everyday local
    flow and [testing-and-validation.md](./testing-and-validation.md) for lane
    details and CI ownership
  - use the workflow template trio as one branch flow:
    - start with [branch-purpose-template.md](./branch-purpose-template.md)
      for branch purpose, scope, split trigger, and the lightweight
      execution checklist, including early test/contract/dependency prompts
    - use [`.github/pull_request_template.md`](../.github/pull_request_template.md)
      while opening or updating the PR so validation, fixture impact, and docs impact stay explicit
    - finish with [merge-readiness-checklist.md](./merge-readiness-checklist.md)
      before merge, retarget, or branch cleanup
- changing frontend or Electron bridge behavior
  - [frontend-architecture.md](./frontend-architecture.md)
  - [contracts.md](./contracts.md)

## Best Entry Points For Coding Agents

Use this shortcut map before editing code:

For the current persistence rollout state, use:

- [session-persistence-audit.md](./session-persistence-audit.md) for rollout,
  schema, rollback, backfill policy, and default-readiness evidence
- [architecture.md](./architecture.md) for the concise storage split
- [session-model.md](./session-model.md) for snapshot and persistence semantics
- [testing-and-validation.md](./testing-and-validation.md) for the synthetic-versus-live validation split

- changing session snapshot or polling behavior:
  - [contracts.md](./contracts.md)
  - [session-model.md](./session-model.md)
  - [session-persistence-audit.md](./session-persistence-audit.md)
  - [architecture.md](./architecture.md)
  - current runtime note: session persistence still defaults to the file-backed
    store; PostgreSQL session bootstrap/config exists, and PostgreSQL session
    storage is available as an explicit runtime opt-in
  - `src/session_store.py`
  - `src/session_store_runtime.py`
  - `src/session_store_runtime_config.py`
  - `src/session_store_file.py`
  - `src/session_store_postgres.py`
  - `src/session_service.py`
  - `tests/test_session_store_contract.py`
  - `tests/test_session_store_file.py`
  - `tests/test_session_store_parity.py`
  - `tests/test_session_store_runtime.py`
  - `tests/test_session_store_postgres.py`
  - `tests/test_api_boundary_sessions_read.py`
  - `frontend/src/bridge/contract.session-snapshot.shape.test.ts`
  - `frontend/src/bridge/contract.session-snapshot.malformed.test.ts`
  - `frontend/src/bridge/contract.session-snapshot.collections.test.ts`
- changing frontend bridge normalization or UI transport handling:
  - [frontend-architecture.md](./frontend-architecture.md)
  - [contracts.md](./contracts.md)
  - [testing-and-validation.md](./testing-and-validation.md)
- changing FastAPI endpoints or response semantics:
  - [architecture-decision-fastapi.md](./architecture-decision-fastapi.md)
  - [contracts.md](./contracts.md)
  - [`fastapi-boundary.md`](./fastapi-boundary.md#policy-and-regression-ownership)
    owns the HTTP route/mode matrix, share-mode policy, and its regression map
  - current CLI-oriented FastAPI boundary checks live mainly in:
    - `tests/test_api_server_cli_runtime.py`
    - `tests/test_api_server_cli_output.py`
    - `tests/test_api_server_cli_routes.py`
- changing MCP alert-reading tools or local MCP launch wiring:
  - [architecture.md](./architecture.md)
  - [contracts.md](./contracts.md)
  - [testing-and-validation.md](./testing-and-validation.md)
  - [`mcp-server.md`](./mcp-server.md#current-tool-inventory) owns MCP
    transport and tool policy; [fastapi-boundary.md](./fastapi-boundary.md)
    explains why HTTP and MCP protections are separate
  - `src/api_auth.py`
  - `src/api/http_auth_policy.py`
  - `src/api_rate_limit.py`
  - `src/api/alert_route_policy.py`
  - `src/esm_mcp/`
  - `src/session_alert_store.py`
  - `src/session_alert_store_postgres.py`
  - `src/session_alert_store_postgres_config.py`
  - `src/session_alerts.py`
  - `src/session_alert_incidents.py`
  - `src/session_io.py`
- adding a detector:
  - [adding-an-analyzer.md](./adding-an-analyzer.md)
  - [testing-and-validation.md](./testing-and-validation.md)
  - [architecture.md](./architecture.md)
  - `src/detectors/`
  - `src/detectors/registry.py`
- experimenting with detector metrics before production integration:
  - [`../detector_lab/README.md`](../detector_lab/README.md)
  - [detector-lab-analysis.md](./detector-lab-analysis.md)
  - [motion-coherence.md](./motion-coherence.md) when the change touches motion-backed blur experiments
  - [testing-and-validation.md](./testing-and-validation.md)
  - use `detector_lab` when the detector idea is still exploratory and you
    want to compare metric variants against the checked-in MP4 fixture sets
- adding an alert rule:
  - [adding-an-alert-rule.md](./adding-an-alert-rule.md)
  - [testing-and-validation.md](./testing-and-validation.md)
  - [architecture.md](./architecture.md)
- working on repo-local Codex skills or their tests:
  - [testing-and-validation.md](./testing-and-validation.md)
  - [branch-purpose-template.md](./branch-purpose-template.md) for the
    lightweight execution pattern reused by planning-oriented skills
  - `./.agents/skills/`
  - use `./.agents/skills/readme-alignment-review/` for root README section
    fit, stage honesty, or README trimming
  - use `./.agents/skills/docs-drift-check/` for pre-edit docs drift audits
    and owner routing
  - use `./.agents/skills/architecture-diagram-review/` for diagram flow,
    boundaries, visual quality, and current-stage honesty
  - these three stay intentionally separate, and the repo skill tests protect
    that split with paired boundary checks
  - before heavier PostgreSQL persistence or FastAPI/MCP security branches,
    start with the nearest review checklist skill instead of writing a broad
    new plan from scratch:
    `persistence-backend-review`,
    `postgres-migration-rollout-review`,
    `fastapi-mcp-security-review`,
    `test-strategy-review`,
    `branch-pr-readiness`
  - use those skills to sanity-check backend defaults, validation shape, docs
    ownership, rollout truth, and branch drift before expanding into
    implementation work
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
  - `src/session_store.py`
  - `src/session_store_runtime.py`
  - `src/session_store_file.py`
  - `tests/test_session_service_start.py`
  - `tests/test_session_service_worker.py`
  - `tests/test_session_service_read_cancel.py`
  - `tests/test_session_store_contract.py`
  - `tests/test_session_store_file.py`
  - `tests/test_session_store_runtime.py`
  - `tests/test_api_boundary_sessions_read.py`
  - `tests/test_api_boundary_sessions_start.py`
  - `tests/test_api_boundary_sessions_cancel.py`
  - `tests/test_session_cli_tooling.py`
  - `tests/test_session_runner_lifecycle.py`
  - `tests/test_session_runner_execution_local.py`
  - `tests/test_session_runner_execution_api_stream.py`
  - `tests/test_session_runner_terminal.py`
  - `tests/test_session_runner_store_writes.py`
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
    - concrete PostgreSQL alert backend, bootstrap, and test-only schema-reset helpers
  - `src/session_alert_store_postgres_config.py`
    - narrow env/config parsing for the PostgreSQL alert-store bootstrap path
  - `src/session_io.py`
  - `src/api/schemas.py`
  - `src/api/routers/alerts.py`
  - `src/esm_mcp/server.py`
  - `src/esm_mcp/alert_tools.py`
  - `src/session_alert_report.py`
    - compact session-alert report shaping and table formatting
    - source owner for the demo-report CLI and normalized alert-report test helpers
  - `tests/session_alert_test_support.py`
    - shared alert/session helpers, including strict opt-in live-PostgreSQL setup
  - `tests/api_alert_test_support.py`
  - `tests/mcp_alert_test_support.py`
  - `tests/test_session_alert_store.py`
    - file-backed contract for the current default alert store
  - `tests/test_session_alert_store_runtime.py`
    - runtime backend selection plus caller-stability coverage for the default
      alert backend, including explicit Postgres URL/bootstrap failure policy
      and cache recovery after failed Postgres bootstrap
  - `tests/test_session_alert_store_runtime_config.py`
    - explicit `file` versus `postgres` backend-mode config coverage
  - `tests/test_session_alert_store_parity.py`
    - file-store versus PostgreSQL-store parity over the shared alert backend
      and read-model layer, including append order, normalized raw shape,
      session-scoped filtering, empty-state behavior, and grouped reads
  - `tests/test_session_alert_store_postgres.py`
    - PostgreSQL alert-store contract, including opt-in live schema/reset and
      read-model smoke coverage
  - `tests/test_session_alert_store_postgres_config.py`
    - narrow env/config, cache-behavior, and URL-validation coverage for the
      PostgreSQL alert-store bootstrap path
  - `tests/test_session_io.py`
    - compatibility write-entry and write-to-read coverage
  - `tests/test_session_runner_execution_local.py`
    - local execution-path coverage for runner-written alerts through the
      shared alert backend plus the live weekly runtime/operator-flow runner
      confidence anchor
  - `scripts/postgres_alert_weekly_confidence_support.py`
    - shared explicit-PostgreSQL environment and current-interpreter runner for
      the scheduled/manual alert-confidence bundles
  - `scripts/postgres_alert_weekly_backend_confidence.py`
    - opt-in weekly/manual live Postgres backend-confidence runner for store,
      raw/grouped FastAPI, and grouped MCP checks
  - `scripts/postgres_alert_weekly_runtime_operator_confidence.py`
    - opt-in weekly/manual live Postgres runtime/operator-flow runner for
      runner writes, snapshot reads, and CLI session reads
  - `scripts/postgres_alert_weekly_confidence.py`
    - umbrella runner that executes both weekly/manual live Postgres
      confidence bundles in order
  - `scripts/session_alert_demo_report.py`
    - prints one compact session-alert report as a table or JSON for manual checks
  - `.github/workflows/weekly-validation.yml`
    - scheduled weekly automation runs both live Postgres confidence bundles
      against a disposable GitHub Actions Postgres service container
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
  - `tests/test_api_session_alert_incidents.py` owns grouped FastAPI route
    behavior, grouped filter binding, runtime-selected Postgres wiring,
    bootstrap-failure parity, and the small live grouped-route smokes
  - `tests/test_mcp_server_alerts_errors.py` owns raw MCP missing-session,
    invalid-range, invalid-timestamp, and runtime Postgres bootstrap-failure
    error mapping
  - `tests/test_mcp_server_incidents_behavior.py` owns grouped MCP no-alert,
    filtered-data, runtime-selected Postgres grouped reads, and small live
    grouped-tool smokes, with grouped output shaping kept separate from
    grouped MCP error translation
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
- durable session-store boundary in `src/session_store.py`

## Repo-Local Codex Skills

The repo also carries a small local skill set for AI-assisted development
work. Treat these as lightweight workflow helpers for the current project
stage: text-first, narrow in scope, and easy to evolve without a separate
automation framework.

Keep workflow ownership split:

- [branch-purpose-template.md](./branch-purpose-template.md)
  - execution pattern, medium-task checklist, and early test/contract/dependency prompts
- [testing-and-validation.md](./testing-and-validation.md)
  - validation lanes, CI depth, and honest manual-only validation notes
- [merge-readiness-checklist.md](./merge-readiness-checklist.md)
  - final branch-ready pass and seam-evidence check
- repo-local skill files under `./.agents/skills/`
  - question-specific prompts only

Use the skill set by question type:

- explain what happened
  - `./.agents/skills/summarization/`
  - `./.agents/skills/incident-timeline/`
  - `./.agents/skills/root-cause-suggestion/`
- shape a branch or next step
  - `./.agents/skills/branch-pr-readiness/`
  - `./.agents/skills/dependency-change-review/`
  - `./.agents/skills/task-planning-evaluation/`
- decide version or rollout meaning
  - `./.agents/skills/release-version-readiness/`
  - `./.agents/skills/postgres-migration-rollout-review/`
- choose validation or test work
  - `./.agents/skills/ci-failure-triage/`
  - `./.agents/skills/test-strategy-review/`
  - `./.agents/skills/manual-validation-planner/`
  - `./.agents/skills/fixture-environment-safety/`
- review a main repo seam
  - `./.agents/skills/detector-rule-review/`
  - `./.agents/skills/frontend-bridge-review/`
  - `./.agents/skills/persistence-backend-review/`
  - `./.agents/skills/alert-backend-parity-review/`
  - `./.agents/skills/fastapi-mcp-security-review/`
  - `./.agents/skills/real-media-validation-review/`
  - `./.agents/skills/security-surface-review/`
  - `./.agents/skills/docs-alignment/`

Most common starting points:

- branch drift, commit shape, or merge readiness
  - `./.agents/skills/branch-pr-readiness/`
- branch/task sizing before implementation
  - `./.agents/skills/task-planning-evaluation/`
- CI failure and smallest honest next lane
  - `./.agents/skills/ci-failure-triage/`
  - `./.agents/skills/test-strategy-review/`
  - if no honest automated lane fits yet, say `manual confidence only for now`
    and name the manual step plainly
- session or alert persistence drift
  - `./.agents/skills/persistence-backend-review/`
  - `./.agents/skills/postgres-migration-rollout-review/`
- dependency metadata drift
  - `./.agents/skills/dependency-change-review/`
- detector/rule changes
  - `./.agents/skills/detector-rule-review/`
- frontend or bridge changes
  - `./.agents/skills/frontend-bridge-review/`
- FastAPI or MCP security-sensitive changes
  - `./.agents/skills/fastapi-mcp-security-review/` for branch-scoped hardening review
  - `./.agents/skills/security-surface-review/` for broader trust-boundary review
- docs or docstring drift
  - `./.agents/skills/docs-alignment/`
- API, CLI, persisted-data, or bridge contract drift
  - `./.agents/skills/docs-alignment/`
  - then [contracts.md](./contracts.md)

The deterministic harness for this layer lives in:

- `tests/test_repo_skills.py`
- `tests/repo_skill_expectations.py`
- `tests/skill_test_support.py`
- `tests/fixtures/skill_output_snapshots/`

Use [testing-and-validation.md](./testing-and-validation.md#repo-local-skill-tests)
for the actual command and validation-lane expectations.

## Document Ownership

Use each doc for one main question:

- root [`README.md`](../README.md)
  - project/runtime overview
  - first stop for trying the repo or understanding the current product shape
- [`docs/README.md`](./README.md)
  - maintainer routing
  - where to start for contributor, reviewer, and AI-agent workflows
- [`testing-and-validation.md`](./testing-and-validation.md)
  - validation lanes
  - routine commands, CI scope, and deeper confidence paths
  - lane policy, fixture-check usage, and cheap local guardrails
- repo-local skill files under `./.agents/skills/`
  - skill behavior only
  - keep repo routing and broader workflow guidance in the maintainer docs, not inside each skill
- when a note starts duplicating one of the sources above, shorten it and point back to the owner
- for Markdown-heavy docs, prefer small edits that keep one owner per topic instead of copying the same guidance into several files
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
- [api-stream-local-validation.md](./api-stream-local-validation.md)
  - repeatable local `api_stream` trial workflow
  - expected status, logs, and cleanup
- [reviewer-guide.md](./reviewer-guide.md)
  - fastest review order
  - best feedback targets for the current project stage
- [release-versioning.md](./release-versioning.md)
  - `0.x` release expectations

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
