#!/usr/bin/env python3
"""Run both weekly/manual live Postgres alert-confidence bundles."""

from __future__ import annotations

from postgres_alert_weekly_backend_confidence import BACKEND_CONFIDENCE_TESTS
from postgres_alert_weekly_confidence_support import run_live_postgres_test_group
from postgres_alert_weekly_runtime_operator_confidence import (
    RUNTIME_OPERATOR_CONFIDENCE_TESTS,
)


def main() -> int:
    """Run the backend bundle first, then the runtime/operator-flow bundle."""
    backend_exit_code = run_live_postgres_test_group(
        "weekly/manual live Postgres backend confidence bundle",
        BACKEND_CONFIDENCE_TESTS,
    )
    if backend_exit_code != 0:
        return backend_exit_code
    return run_live_postgres_test_group(
        "weekly/manual live Postgres runtime/operator-flow confidence bundle",
        RUNTIME_OPERATOR_CONFIDENCE_TESTS,
    )


if __name__ == "__main__":
    raise SystemExit(main())
