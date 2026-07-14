#!/usr/bin/env python3
"""Shared setup for scheduled and manual live PostgreSQL alert confidence.

Each bundle requires a disposable database URL, forces PostgreSQL selection,
and invokes pytest through the current Python interpreter. Missing setup fails
before pytest; printed plans redact the database URL.
"""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]


def require_database_url() -> str:
    """Return the explicit disposable database URL or exit with a setup hint."""
    database_url = os.environ.get("ESM_POSTGRES_ALERT_DATABASE_URL", "").strip()
    if database_url:
        return database_url
    print(
        "Set ESM_POSTGRES_ALERT_DATABASE_URL before running the live Postgres confidence slice.",
        file=sys.stderr,
    )
    raise SystemExit(1)


def build_live_postgres_env(database_url: str) -> dict[str, str]:
    """Build the forced PostgreSQL live-test environment for one bundle."""
    env = os.environ.copy()
    env.setdefault("PYTEST_DISABLE_PLUGIN_AUTOLOAD", "1")
    env["POSTGRES_ALERT_STORE_REAL_SMOKE"] = "1"
    # An explicitly requested live bundle must not silently inherit file mode.
    env["ESM_ALERT_STORE_BACKEND"] = "postgres"
    env["ESM_POSTGRES_ALERT_DATABASE_URL"] = database_url
    return env


def build_pytest_command(test_paths: tuple[str, ...]) -> list[str]:
    """Build the focused pytest command with the invoking Python interpreter."""
    return [sys.executable, "-m", "pytest", "-q", *test_paths]


def print_run_plan(
    title: str,
    test_paths: tuple[str, ...],
    env: dict[str, str],
) -> None:
    """Print a redacted plan for one live PostgreSQL confidence group."""
    print(f"Running {title}:")
    for test_path in test_paths:
        print(f"- {test_path}")
    print()
    print(f"ESM_ALERT_STORE_BACKEND={env['ESM_ALERT_STORE_BACKEND']}")
    print("POSTGRES_ALERT_STORE_REAL_SMOKE=1")
    print("ESM_POSTGRES_ALERT_DATABASE_URL=<set>")
    print()


def run_live_postgres_test_group(
    title: str,
    test_paths: tuple[str, ...],
) -> int:
    """Run one named live PostgreSQL confidence group and return its exit code."""
    database_url = require_database_url()
    env = build_live_postgres_env(database_url)
    command = build_pytest_command(test_paths)
    print_run_plan(title, test_paths, env)
    completed = subprocess.run(command, cwd=REPO_ROOT, env=env, check=False)
    return completed.returncode
