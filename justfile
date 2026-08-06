# Local developer workflow entrypoint.
#
# Conventions:
# - Keep recipe names short, lowercase, and hyphenated.
# - Prefer task-oriented names such as `test-fast` over tool-oriented names.
# - Keep recipes thin: call the existing project commands instead of embedding
#   large shell workflows here.
# - Default to readable command output. Add dedicated quiet variants later only
#   when the project actually needs them.
# - Add parameters only for cases we expect to reuse, not preemptively.
# - Keep focused lanes as the source of truth; broader lanes should compose
#   them instead of restating long command lists.
# - Choose the smallest honest lane first; reserve `test-fast` for multi-seam
#   runtime checks and `ci-local` for push-readiness.
# - Cheap local hygiene belongs in `pre-commit`; broader verification belongs
#   here or in CI.

# These recipes stay within POSIX shell features, so `sh -eu` keeps local
# runs deterministic without inheriting host-specific Bash startup noise.
set shell := ["sh", "-eu", "-c"]

venv_python := ".venv/bin/python"
venv_pytest := ".venv/bin/pytest"
venv_ruff := ".venv/bin/ruff"
venv_mypy := ".venv/bin/mypy"
venv_pyright := ".venv/bin/pyright"
venv_bandit := ".venv/bin/bandit"
venv_pip_audit := ".venv/bin/pip-audit"
security_tool_bin_dir := ".tools/security/bin"
pytest_base_flags := "-p no:cacheprovider -q"
pytest_env_prefix := "PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1"
backend_coverage_env_prefix := "ESM_ALERT_STORE_BACKEND=file ESM_SESSION_STORE_BACKEND=file POSTGRES_ALERT_STORE_REAL_SMOKE=0 POSTGRES_SESSION_STORE_REAL_SMOKE=0 API_STREAM_REAL_SMOKE=0 COVERAGE_FILE=coverage/backend/.coverage"
live_session_postgres_env_prefix := "ESM_SESSION_STORE_BACKEND=postgres ESM_POSTGRES_SESSION_AUTO_CREATE_TABLES=1 POSTGRES_SESSION_STORE_REAL_SMOKE=1"
backend_typecheck_target_file := ".github/backend_typecheck_targets.txt"
backend_fast_synthetic_selector := "-m 'not e2e and not slow'"

default:
    @just --list

help: default

# Reproducible contributor bootstrap. Host tools stay outside this repository.
setup:
    uv sync --locked --extra dev
    cd frontend && bash ../scripts/install_frontend_dependencies.sh
    just env-check

# Lightweight local environment sanity check.
env-check:
    python3 .github/scripts/check_development_environment.py

# Core local validation loop:
# - fast production backend detector/rule confidence
# - frontend checkpoint confidence for the desktop runtime path
test-fast: test-detectors test-processor test-alert-rules test-frontend

# Focused production detector contract lane.
test-detectors:
    {{pytest_env_prefix}} {{venv_pytest}} {{pytest_base_flags}} tests/test_detectors.py

# Focused production processor/orchestration lane.
test-processor:
    {{pytest_env_prefix}} {{venv_pytest}} {{pytest_base_flags}} \
      tests/test_processor_routing.py \
      tests/test_processor_context_alerts.py \
      tests/test_processor_failures.py

# Focused production alert-rule lane.
test-alert-rules:
    {{pytest_env_prefix}} {{venv_pytest}} {{pytest_base_flags}} \
      tests/test_alert_rules.py \
      tests/test_alert_rules_black.py \
      tests/test_alert_rules_blur.py

# Focused HLS / api_stream loader seam lane.
test-hls:
    {{pytest_env_prefix}} {{venv_pytest}} {{pytest_base_flags}} \
      tests/test_stream_loader_http_hls_playlist.py \
      tests/test_stream_loader_http_hls_fetch.py \
      tests/test_stream_loader_http_hls_materialize.py \
      tests/test_stream_loader_http_hls_policy.py \
      tests/test_stream_loader_http_hls_core_playlist.py \
      tests/test_stream_loader_http_hls_core_progression.py \
      tests/test_stream_loader_http_hls_core_provider.py \
      tests/test_stream_loader_http_hls_reconnect_recovery.py \
      tests/test_stream_loader_http_hls_reconnect_state.py \
      tests/test_stream_loader_http_hls_limits_runtime.py \
      tests/test_stream_loader_http_hls_limits_cleanup.py \
      tests/test_stream_loader_http_hls_limits_restart.py

# Focused frontend runtime/bridge lane.
test-frontend:
    npm --prefix frontend run test:frontend-checkpoint

# Docs/workflow consistency lane for local maintainer checks.
docs-check:
    python3 .github/scripts/validate_ci_test_targets.py
    python3 .github/scripts/check_ci_test_paths_exist.py
    python3 .github/scripts/check_ci_target_drift.py

# Focused workflow-contract regression lane for local maintainer checks.
ci-contract-check:
    {{pytest_env_prefix}} {{venv_pytest}} {{pytest_base_flags}} \
      tests/test_ci_workflow.py \
      tests/test_ci_test_target_scripts.py

# Focused deterministic FastAPI/MCP security regression lane.
# This stays synthetic and is safe for routine backend validation: it does not
# start a server, open sockets, or require PostgreSQL.
test-security-regression:
    {{pytest_env_prefix}} {{venv_pytest}} {{pytest_base_flags}} \
      tests/test_api_auth.py \
      tests/test_api_rate_limit.py \
      tests/test_api_boundary_settings_env.py \
      tests/test_api_boundary_settings_validation.py \
      tests/test_api_boundary_contracts.py \
      tests/test_api_boundary_error_contracts.py \
      tests/test_api_server_cli_runtime.py \
      tests/test_api_server_cli_routes.py \
      tests/test_api_server_cli_output.py \
      tests/test_api_alert_route_auth_policy.py \
      tests/test_api_alert_route_rate_limit_policy.py \
      tests/test_api_session_route_rate_limit_policy.py \
      tests/test_api_playback_route_policy.py \
      tests/test_api_read_resource_policy.py \
      tests/test_session_cli_tooling.py \
      tests/test_mcp_server_contracts.py \
      tests/test_mcp_server_alerts_errors.py \
      tests/test_mcp_server_incidents_errors.py \
      tests/test_mcp_fastapi_boundary_split.py \
      tests/test_postgres_diagnostics.py

# Fixture/environment policy lane for local maintainer checks.
fixture-check:
    python3 .github/scripts/check_fixture_environment_policy.py

# Lightweight dependency metadata drift lane for local maintainer checks.
dependency-check:
    python3 .github/scripts/check_dependency_drift.py

# Focused local security evidence. These inspect declared sources without
# changing dependency versions or applying automatic fixes.
audit-bandit:
    {{venv_bandit}} -r src -x tests,frontend

audit-python:
    PIP_AUDIT={{venv_pip_audit}} sh scripts/audit_python_dependencies.sh

audit-frontend:
    npm --prefix frontend audit --audit-level=high

# Check committed repository history with the reviewed pinned Gitleaks binary.
install-gitleaks:
    python3 scripts/install_security_tool.py gitleaks --bin-dir {{security_tool_bin_dir}}

audit-gitleaks:
    {{security_tool_bin_dir}}/gitleaks git --redact --no-banner --exit-code 1

# Non-destructive branch hygiene and review-readiness check.
branch-cleanup:
    echo "== branch =="
    git branch --show-current
    echo
    echo "== status =="
    git status --short
    echo
    echo "== upstream =="
    git rev-parse --abbrev-ref --symbolic-full-name '@{upstream}' 2>/dev/null || echo "(no upstream configured)"
    echo
    echo "== divergence vs upstream =="
    git rev-list --left-right --count '@{upstream}'...HEAD 2>/dev/null || echo "(cannot compare without upstream)"
    echo
    echo "== changed files =="
    git diff --stat
    echo
    echo "== staged files =="
    git diff --cached --stat

# Protected backend Python lint gate.
lint-backend:
    {{venv_ruff}} check src scripts tests

# Protected renderer lint gate.
lint-renderer:
    npm --prefix frontend run lint:renderer

# Advisory Electron main-process, bridge, and local-proxy lint feedback.
lint-electron-advisory:
    npm --prefix frontend run lint:electron

# Full local lint feedback, including the advisory Electron companion.
lint: lint-backend lint-renderer lint-electron-advisory

# Check the shared Python formatting contract without rewriting the worktree.
format-check:
    {{venv_ruff}} format --check src scripts tests

# Apply the shared Python formatter. Keep its mechanical baseline separate from
# behavior changes so reviews remain readable.
format:
    {{venv_ruff}} format src scripts tests

# Fast detector-lab lane for synthetic and runner-scaffold confidence.
test-detector-lab:
    {{pytest_env_prefix}} {{venv_pytest}} {{pytest_base_flags}} \
      tests/test_detector_lab_runner.py \
      tests/test_detector_lab_metrics.py \
      tests/test_detector_lab_practical_blur.py \
      tests/test_detector_lab_practical_motion.py

# Slow decoded-detector and detector-lab confidence lane backed by checked-in media.
test-real-media:
    {{pytest_env_prefix}} {{venv_pytest}} {{pytest_base_flags}} \
      tests/test_detectors_integration.py \
      tests/test_detector_lab_real_media.py

# Slower detached-worker runtime lane for FastAPI/session persistence confidence.
test-session-runtime:
    {{pytest_env_prefix}} {{venv_pytest}} {{pytest_base_flags}} \
      tests/test_session_service_worker.py \
      tests/test_session_cli_tooling.py \
      tests/test_api_boundary_sessions_runtime.py \
      tests/test_session_store_runtime.py

# Focused session-store contract and parity lane.
test-session-store:
    {{pytest_env_prefix}} {{venv_pytest}} {{pytest_base_flags}} \
      tests/test_session_store_contract.py \
      tests/test_session_store_file.py \
      tests/test_session_store_parity.py \
      tests/test_session_store_runtime.py

# Opt-in local live PostgreSQL confidence lane.
# Runs the narrow real-DB store smoke first, then the matching runtime smoke.
# This stays outside protected PR CI.
test-session-postgres-live:
    @if [ "${POSTGRES_SESSION_STORE_REAL_SMOKE:-0}" != "1" ]; then \
      echo "Set POSTGRES_SESSION_STORE_REAL_SMOKE=1 to run live PostgreSQL session smoke."; \
      exit 1; \
    fi
    @if [ -z "${ESM_POSTGRES_SESSION_DATABASE_URL:-}" ]; then \
      echo "Set ESM_POSTGRES_SESSION_DATABASE_URL to run live PostgreSQL session smoke."; \
      exit 1; \
    fi
    @if [ "${ESM_POSTGRES_SESSION_AUTO_CREATE_TABLES:-}" != "1" ]; then \
      echo "Set ESM_POSTGRES_SESSION_AUTO_CREATE_TABLES=1 to run live PostgreSQL session smoke."; \
      exit 1; \
    fi
    {{live_session_postgres_env_prefix}} {{pytest_env_prefix}} {{venv_pytest}} {{pytest_base_flags}} tests/test_session_store_postgres.py -k real_postgres_session_store
    {{live_session_postgres_env_prefix}} {{pytest_env_prefix}} {{venv_pytest}} {{pytest_base_flags}} tests/test_api_boundary_sessions_runtime.py -k live_postgres_runtime

# Opt-in local live PostgreSQL alert confidence lane.
# The shared helper forces PostgreSQL selection and the live-smoke gate.
# This stays outside protected PR CI and requires a disposable database URL.
test-alert-postgres-live:
    {{venv_python}} scripts/postgres_alert_weekly_confidence.py

# Fast synthetic backend lane aligned with the current `backend-tests` CI job.
_backend-tests-fast:
    {{venv_python}} -c "import api.app, api.routers.sessions, session_service, session_cli, session_alert_report"
    {{venv_python}} -m py_compile src/session_alert_report.py scripts/session_alert_demo_report.py
    {{pytest_env_prefix}} {{venv_pytest}} {{pytest_base_flags}} {{backend_fast_synthetic_selector}}

# Advisory in-process coverage for the broad fast backend suite. This keeps
# slow, E2E, live PostgreSQL, and real external-stream confidence out of the
# baseline and does not add a percentage gate.
coverage-backend:
    mkdir -p coverage/backend
    {{backend_coverage_env_prefix}} {{pytest_env_prefix}} {{venv_pytest}} {{pytest_base_flags}} -p pytest_cov {{backend_fast_synthetic_selector}} --cov=src --cov-branch --cov-report=term-missing --cov-report=json:coverage/backend/coverage.json --cov-report=xml:coverage/backend/coverage.xml

# Local fast-CI reproduction lane.
# This intentionally mirrors the everyday branch-feedback checks, not the
# weekly, slow, or PR-only policy lanes that stay owned by GitHub Actions.
ci-local: _backend-tests-fast lint-backend lint-renderer typecheck-backend typecheck-frontend
    npm --prefix frontend run test:frontend-checkpoint

# Protected backend Python type gate.
typecheck-backend:
    MYPYPATH=src xargs {{venv_mypy}} --explicit-package-bases < {{backend_typecheck_target_file}}

# Advisory editor-aligned Python type feedback. Run separately so its findings
# do not block the local protected gate.
typecheck-advisory:
    xargs {{venv_pyright}} --project pyrightconfig.json < {{backend_typecheck_target_file}}

# Protected renderer and Electron TypeScript type gate.
typecheck-frontend:
    npm --prefix frontend run typecheck

# Full local type feedback, including the advisory Pyright companion.
typecheck: typecheck-backend typecheck-advisory typecheck-frontend
