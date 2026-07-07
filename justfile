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
pytest_base_flags := "-p no:cacheprovider -q"
pytest_env_prefix := "PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1"
backend_typecheck_targets := "src/alert_rules.py src/api/app.py src/api/routers/alerts.py src/api/routers/detectors.py src/api/routers/health.py src/api/routers/playback.py src/api/routers/sessions.py src/api/schemas.py src/api_auth.py src/api_boundary_config.py src/api_rate_limit.py src/api_server_cli.py src/esm_mcp/alert_tools.py src/esm_mcp/server.py src/session_alert_adapter.py src/session_alert_incidents.py src/session_alert_report.py src/session_alerts.py src/session_alert_store.py src/session_alert_store_runtime_config.py src/session_alert_store_postgres.py src/session_alert_store_postgres_config.py src/session_io.py src/session_models.py src/session_runner.py src/session_service.py src/stream_loader_contracts.py"
backend_fast_synthetic_selector := "-m 'not e2e and not slow'"

default:
    @just --list

help: default

# Lightweight local environment sanity check.
env-check:
    python3 --version
    node --version
    ffmpeg -version | head -n 1
    if command -v just >/dev/null 2>&1; then just --version; else echo "just: not installed"; fi

# Core local validation loop:
# - fast production backend detector/rule confidence
# - frontend checkpoint confidence for the desktop runtime path
test-fast: test-detectors test-processor test-alert-rules test-frontend

# Focused production detector contract lane.
test-detectors:
    {{pytest_env_prefix}} {{venv_pytest}} {{pytest_base_flags}} tests/test_detectors.py

# Focused production processor/orchestration lane.
test-processor:
    {{pytest_env_prefix}} {{venv_pytest}} {{pytest_base_flags}} tests/test_processor.py

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

# Fixture/environment policy lane for local maintainer checks.
fixture-check:
    python3 .github/scripts/check_fixture_environment_policy.py

# Lightweight dependency metadata drift lane for local maintainer checks.
dependency-check:
    python3 .github/scripts/check_dependency_drift.py

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

# Aggregated lint lane matching the current backend/frontend split.
lint:
    {{venv_ruff}} check src scripts tests
    npm --prefix frontend run lint:frontend

# Fast detector-lab lane for synthetic and runner-scaffold confidence.
test-detector-lab:
    {{pytest_env_prefix}} {{venv_pytest}} {{pytest_base_flags}} tests/test_detector_lab.py

# Slow detector-lab confidence lane backed by checked-in real media fixtures.
test-real-media:
    {{pytest_env_prefix}} {{venv_pytest}} {{pytest_base_flags}} tests/test_detector_lab_real_media.py

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

# Fast synthetic backend lane aligned with the current `backend-tests` CI job.
_backend-tests-fast:
    {{venv_python}} -c "import api.app, api.routers.sessions, session_service, session_cli, session_alert_report"
    {{venv_python}} -m py_compile src/session_alert_report.py scripts/session_alert_demo_report.py
    {{pytest_env_prefix}} {{venv_pytest}} {{pytest_base_flags}} {{backend_fast_synthetic_selector}}

# Local fast-CI reproduction lane.
# This intentionally mirrors the everyday branch-feedback checks, not the
# weekly, slow, or PR-only policy lanes that stay owned by GitHub Actions.
ci-local: _backend-tests-fast lint typecheck
    npm --prefix frontend run test:frontend-checkpoint

# Aggregated type lane:
# - backend mypy remains the primary Python type gate
# - backend pyright stays included as the editor-aligned companion signal
# - frontend TypeScript typecheck protects the renderer and bridge layers
typecheck:
    MYPYPATH=src {{venv_mypy}} --explicit-package-bases {{backend_typecheck_targets}}
    {{venv_pyright}} --project pyrightconfig.json {{backend_typecheck_targets}}
    npm --prefix frontend run typecheck
