#!/usr/bin/env python3
"""Shared helpers for weekly/manual live Postgres alert confidence runners."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
PYTEST_PATH = REPO_ROOT / ".venv" / "bin" / "pytest"


def require_pytest_executable() -> None:
    """Fail clearly when the project virtualenv has not been created yet."""
    if PYTEST_PATH.exists():
        return
    print(f"Pytest executable not found: {PYTEST_PATH}", file=sys.stderr)
    print("Create the project virtualenv before running this helper.", file=sys.stderr)
    raise SystemExit(1)


def require_database_url() -> str:
    """Return the live Postgres URL or fail with one clear setup hint."""
    database_url = os.environ.get("ESM_POSTGRES_ALERT_DATABASE_URL", "").strip()
    if database_url:
        return database_url
    print(
        "Set ESM_POSTGRES_ALERT_DATABASE_URL before running the live Postgres confidence slice.",
        file=sys.stderr,
    )
    raise SystemExit(1)


def build_live_postgres_env(database_url: str) -> dict[str, str]:
    """Return the shared opt-in env for weekly/manual live Postgres validation."""
    env = os.environ.copy()
    env.setdefault("PYTEST_DISABLE_PLUGIN_AUTOLOAD", "1")
    env["POSTGRES_ALERT_STORE_REAL_SMOKE"] = "1"
    env.setdefault("ESM_ALERT_STORE_BACKEND", "postgres")
    env["ESM_POSTGRES_ALERT_DATABASE_URL"] = database_url
    return env


def build_pytest_command(test_paths: tuple[str, ...]) -> list[str]:
    """Return the focused pytest command for one live Postgres confidence group."""
    return [str(PYTEST_PATH), "-q", *test_paths]


def print_run_plan(
    title: str,
    test_paths: tuple[str, ...],
    env: dict[str, str],
) -> None:
    """Print the tests and env knobs used by one live confidence group."""
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
    """Run one named live-Postgres confidence group and return the pytest exit code."""
    require_pytest_executable()
    database_url = require_database_url()
    env = build_live_postgres_env(database_url)
    command = build_pytest_command(test_paths)
    print_run_plan(title, test_paths, env)
    completed = subprocess.run(command, cwd=REPO_ROOT, env=env, check=False)
    return completed.returncode
