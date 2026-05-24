#!/usr/bin/env python3
"""Run the weekly/manual live Postgres runtime and operator-flow bundle."""

from __future__ import annotations

from postgres_alert_weekly_confidence_support import run_live_postgres_test_group


RUNTIME_OPERATOR_CONFIDENCE_TESTS: tuple[str, ...] = (
    "tests/test_session_runner_execution_local.py::test_live_runtime_postgres_runner_written_alerts_stay_aligned_across_snapshot_and_api",
    "tests/test_api_boundary_sessions_read.py::test_live_runtime_postgres_session_snapshot_reads_alerts_from_the_active_backend",
    "tests/test_session_cli_tooling.py::test_live_runtime_postgres_read_session_reads_alerts_from_the_active_backend",
)


def main() -> int:
    """Run the live-Postgres runtime/operator flow confidence bundle."""
    return run_live_postgres_test_group(
        "weekly/manual live Postgres runtime/operator-flow confidence bundle",
        RUNTIME_OPERATOR_CONFIDENCE_TESTS,
    )


if __name__ == "__main__":
    raise SystemExit(main())
