#!/usr/bin/env python3
"""Run ordered, fail-fast weekly/manual PostgreSQL alert-confidence bundles."""

from __future__ import annotations

from postgres_alert_weekly_backend_confidence import (
    BACKEND_CONFIDENCE_TESTS,
    BACKEND_CONFIDENCE_TITLE,
)
from postgres_alert_weekly_confidence_support import run_live_postgres_test_group
from postgres_alert_weekly_runtime_operator_confidence import (
    RUNTIME_OPERATOR_CONFIDENCE_TESTS,
    RUNTIME_OPERATOR_CONFIDENCE_TITLE,
)


LIVE_CONFIDENCE_BUNDLES: tuple[tuple[str, tuple[str, ...]], ...] = (
    (BACKEND_CONFIDENCE_TITLE, BACKEND_CONFIDENCE_TESTS),
    (RUNTIME_OPERATOR_CONFIDENCE_TITLE, RUNTIME_OPERATOR_CONFIDENCE_TESTS),
)


def main() -> int:
    """Run each bundle in order and return the first non-zero exit code."""
    for title, test_paths in LIVE_CONFIDENCE_BUNDLES:
        exit_code = run_live_postgres_test_group(title, test_paths)
        if exit_code != 0:
            return exit_code
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
