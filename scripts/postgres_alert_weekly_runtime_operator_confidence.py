#!/usr/bin/env python3
"""Run the weekly/manual live PostgreSQL runtime and operator-flow bundle.

The first entry is the canonical runner-write-to-operator-read smoke. The
remaining entries extend confidence to the snapshot and CLI reader seams.
"""

from __future__ import annotations

from postgres_alert_weekly_confidence_support import run_live_postgres_test_group


RUNTIME_OPERATOR_CONFIDENCE_TITLE = (
    "weekly/manual live Postgres runtime/operator-flow confidence bundle"
)

CANONICAL_RUNTIME_OPERATOR_SMOKE = (
    "tests/test_session_runner_execution_local.py::"
    "test_live_runtime_postgres_runner_written_alerts_stay_aligned_across_snapshot_and_api"
)
SNAPSHOT_RUNTIME_SMOKE = (
    "tests/test_api_boundary_sessions_read.py::"
    "test_live_runtime_postgres_session_snapshot_reads_alerts_from_the_active_backend"
)
CLI_RUNTIME_SMOKE = (
    "tests/test_session_cli_tooling.py::"
    "test_live_runtime_postgres_read_session_reads_alerts_from_the_active_backend"
)

RUNTIME_OPERATOR_CONFIDENCE_TESTS: tuple[str, ...] = (
    CANONICAL_RUNTIME_OPERATOR_SMOKE,
    SNAPSHOT_RUNTIME_SMOKE,
    CLI_RUNTIME_SMOKE,
)


def main() -> int:
    """Run the live-Postgres runtime/operator flow confidence bundle."""
    return run_live_postgres_test_group(
        RUNTIME_OPERATOR_CONFIDENCE_TITLE,
        RUNTIME_OPERATOR_CONFIDENCE_TESTS,
    )


if __name__ == "__main__":
    raise SystemExit(main())
