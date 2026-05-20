#!/usr/bin/env python3
"""Run the small opt-in weekly/manual live Postgres alert confidence slice."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
PYTEST_PATH = REPO_ROOT / ".venv" / "bin" / "pytest"
LIVE_POSTGRES_TESTS: tuple[str, ...] = (
    "tests/test_session_alert_store_postgres.py::test_real_postgres_alert_store_smoke_round_trip",
    "tests/test_api_session_alert_incidents.py::test_live_runtime_postgres_grouped_routes_follow_actual_startup_path",
    "tests/test_api_boundary_sessions_read.py::test_live_runtime_postgres_session_snapshot_reads_alerts_from_the_active_backend",
    "tests/test_session_cli_tooling.py::test_live_runtime_postgres_read_session_reads_alerts_from_the_active_backend",
)


def _require_pytest_executable() -> None:
    """Fail clearly when the project virtualenv has not been created yet."""
    if PYTEST_PATH.exists():
        return
    print(f"Pytest executable not found: {PYTEST_PATH}", file=sys.stderr)
    print("Create the project virtualenv before running this helper.", file=sys.stderr)
    raise SystemExit(1)


def _require_database_url() -> str:
    """Return the live Postgres URL or fail with one clear setup hint."""
    database_url = os.environ.get("ESM_POSTGRES_ALERT_DATABASE_URL", "").strip()
    if database_url:
        return database_url
    print(
        "Set ESM_POSTGRES_ALERT_DATABASE_URL before running the live Postgres confidence slice.",
        file=sys.stderr,
    )
    raise SystemExit(1)


def _build_live_postgres_env(database_url: str) -> dict[str, str]:
    """Return the opt-in live-Postgres env used by the weekly/manual smoke run."""
    env = os.environ.copy()
    env.setdefault("PYTEST_DISABLE_PLUGIN_AUTOLOAD", "1")
    env["POSTGRES_ALERT_STORE_REAL_SMOKE"] = "1"
    env.setdefault("ESM_ALERT_STORE_BACKEND", "postgres")
    env["ESM_POSTGRES_ALERT_DATABASE_URL"] = database_url
    return env


def _build_pytest_command() -> list[str]:
    """Return the focused live-Postgres pytest command for the confidence slice."""
    return [str(PYTEST_PATH), "-q", *LIVE_POSTGRES_TESTS]


def _print_run_plan(env: dict[str, str]) -> None:
    """Print the exact tests and env knobs used by the manual confidence slice."""
    print("Running weekly/manual live Postgres alert confidence slice:")
    for test_path in LIVE_POSTGRES_TESTS:
        print(f"- {test_path}")
    print()
    print(f"ESM_ALERT_STORE_BACKEND={env['ESM_ALERT_STORE_BACKEND']}")
    print("POSTGRES_ALERT_STORE_REAL_SMOKE=1")
    print("ESM_POSTGRES_ALERT_DATABASE_URL=<set>")
    print()


def main() -> int:
    _require_pytest_executable()
    database_url = _require_database_url()
    env = _build_live_postgres_env(database_url)
    command = _build_pytest_command()
    _print_run_plan(env)
    completed = subprocess.run(command, cwd=REPO_ROOT, env=env, check=False)
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
