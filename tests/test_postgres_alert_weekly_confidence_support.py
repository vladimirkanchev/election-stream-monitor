"""Deterministic contract tests for the opt-in PostgreSQL alert harness.

These tests validate environment forcing, bundle ownership, and fail-fast exit
behavior without connecting to PostgreSQL.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import postgres_alert_weekly_confidence as weekly_confidence  # noqa: E402
import postgres_alert_weekly_confidence_support as live_confidence_support  # noqa: E402
from postgres_alert_weekly_backend_confidence import (  # noqa: E402
    BACKEND_CONFIDENCE_TESTS,
    BACKEND_CONFIDENCE_TITLE,
    SEEDED_READER_CONFIDENCE_TESTS,
    STORE_CONFIDENCE_TESTS,
)
from postgres_alert_weekly_confidence_support import (  # noqa: E402
    build_live_postgres_env,
    print_run_plan,
    require_database_url,
    run_live_postgres_test_group,
)
from postgres_alert_weekly_runtime_operator_confidence import (  # noqa: E402
    CANONICAL_RUNTIME_OPERATOR_SMOKE,
    RUNTIME_OPERATOR_CONFIDENCE_TESTS,
    RUNTIME_OPERATOR_CONFIDENCE_TITLE,
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


def test_live_postgres_bundle_requires_an_explicit_database_url(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A requested live bundle must stop before pytest without a database URL."""
    monkeypatch.delenv("ESM_POSTGRES_ALERT_DATABASE_URL", raising=False)

    with pytest.raises(SystemExit, match="1"):
        require_database_url()

    assert "Set ESM_POSTGRES_ALERT_DATABASE_URL" in capsys.readouterr().err


def test_live_postgres_run_plan_never_prints_the_database_url(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Live helper plans should expose setup state without a database credential."""
    database_url = "postgresql://alerts:secret@db.example/esm?token=query-token"

    print_run_plan(
        "test bundle",
        ("tests/test_example.py",),
        build_live_postgres_env(database_url),
    )

    output = capsys.readouterr().out
    assert "ESM_POSTGRES_ALERT_DATABASE_URL=<set>" in output
    assert database_url not in output
    assert "secret" not in output
    assert "query-token" not in output


def test_live_postgres_group_uses_the_invoking_python_and_propagates_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The portable helper must preserve the focused pytest failure result."""
    database_url = "postgresql://postgres:postgres@localhost:5432/esm"
    observed: dict[str, object] = {}

    def fake_run(
        command: list[str],
        *,
        cwd: Path,
        env: dict[str, str],
        check: bool,
    ) -> SimpleNamespace:
        observed.update(command=command, cwd=cwd, env=env, check=check)
        return SimpleNamespace(returncode=17)

    monkeypatch.setenv("ESM_POSTGRES_ALERT_DATABASE_URL", database_url)
    monkeypatch.setattr(live_confidence_support.subprocess, "run", fake_run)

    assert (
        run_live_postgres_test_group("test bundle", ("tests/test_example.py",))
        == 17
    )
    assert observed["command"] == [
        sys.executable,
        "-m",
        "pytest",
        "-q",
        "tests/test_example.py",
    ]
    assert observed["cwd"] == live_confidence_support.REPO_ROOT
    assert observed["check"] is False
    environment = observed["env"]
    assert isinstance(environment, dict)
    assert environment["ESM_ALERT_STORE_BACKEND"] == "postgres"
    assert environment["ESM_POSTGRES_ALERT_DATABASE_URL"] == database_url
    assert environment["POSTGRES_ALERT_STORE_REAL_SMOKE"] == "1"


def test_umbrella_live_postgres_helper_stops_after_backend_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The runtime bundle must not obscure an earlier backend-confidence failure."""
    calls: list[tuple[str, tuple[str, ...]]] = []

    def fail_backend(
        title: str,
        test_paths: tuple[str, ...],
    ) -> int:
        calls.append((title, test_paths))
        return 17

    monkeypatch.setattr(
        weekly_confidence,
        "run_live_postgres_test_group",
        fail_backend,
    )

    assert weekly_confidence.main() == 17
    assert calls == [
        (
            BACKEND_CONFIDENCE_TITLE,
            weekly_confidence.BACKEND_CONFIDENCE_TESTS,
        )
    ]


def test_umbrella_live_postgres_helper_runs_backend_before_runtime(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A successful backend bundle must precede the runtime/operator bundle."""
    calls: list[tuple[str, tuple[str, ...]]] = []

    def succeed(
        title: str,
        test_paths: tuple[str, ...],
    ) -> int:
        calls.append((title, test_paths))
        return 0

    monkeypatch.setattr(
        weekly_confidence,
        "run_live_postgres_test_group",
        succeed,
    )

    assert weekly_confidence.main() == 0
    assert calls == [
        (
            BACKEND_CONFIDENCE_TITLE,
            weekly_confidence.BACKEND_CONFIDENCE_TESTS,
        ),
        (
            RUNTIME_OPERATOR_CONFIDENCE_TITLE,
            weekly_confidence.RUNTIME_OPERATOR_CONFIDENCE_TESTS,
        ),
    ]


def test_umbrella_live_postgres_helper_propagates_runtime_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A runtime/operator failure must remain visible after backend success."""
    exit_codes = iter((0, 23))

    def return_next_exit_code(_title: str, _test_paths: tuple[str, ...]) -> int:
        return next(exit_codes)

    monkeypatch.setattr(
        weekly_confidence,
        "run_live_postgres_test_group",
        return_next_exit_code,
    )

    assert weekly_confidence.main() == 23


def test_runtime_operator_bundle_keeps_the_canonical_runner_smoke() -> None:
    """The weekly/manual runtime lane must retain its runner write-to-read proof."""
    assert RUNTIME_OPERATOR_CONFIDENCE_TESTS[0] == CANONICAL_RUNTIME_OPERATOR_SMOKE


def test_live_postgres_bundles_keep_backend_and_runner_ownership_separate() -> None:
    """Seeded store/read checks and runner-write checks must not overlap."""
    assert BACKEND_CONFIDENCE_TESTS == (
        *STORE_CONFIDENCE_TESTS,
        *SEEDED_READER_CONFIDENCE_TESTS,
    )
    assert set(BACKEND_CONFIDENCE_TESTS).isdisjoint(
        RUNTIME_OPERATOR_CONFIDENCE_TESTS
    )
