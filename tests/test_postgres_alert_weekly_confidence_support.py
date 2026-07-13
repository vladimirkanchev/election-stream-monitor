"""Focused tests for the opt-in live PostgreSQL alert confidence wrapper."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest


SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from postgres_alert_weekly_confidence_support import build_live_postgres_env  # noqa: E402
from postgres_alert_weekly_runtime_operator_confidence import (  # noqa: E402
    CANONICAL_RUNTIME_OPERATOR_SMOKE,
    RUNTIME_OPERATOR_CONFIDENCE_TESTS,
)


def test_live_postgres_env_overrides_a_stale_file_backend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An explicit live bundle must run Postgres tests instead of skipping in file mode."""
    database_url = "postgresql://postgres:postgres@localhost:5432/esm"
    monkeypatch.setenv("ESM_ALERT_STORE_BACKEND", "file")

    env = build_live_postgres_env(database_url)

    assert env["ESM_ALERT_STORE_BACKEND"] == "postgres"
    assert env["POSTGRES_ALERT_STORE_REAL_SMOKE"] == "1"
    assert env["ESM_POSTGRES_ALERT_DATABASE_URL"] == database_url


def test_runtime_operator_bundle_keeps_the_canonical_runner_smoke() -> None:
    """The weekly/manual runtime lane must retain its runner write-to-read proof."""
    assert RUNTIME_OPERATOR_CONFIDENCE_TESTS[0] == CANONICAL_RUNTIME_OPERATOR_SMOKE
