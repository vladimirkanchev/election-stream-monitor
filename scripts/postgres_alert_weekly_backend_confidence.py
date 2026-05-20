#!/usr/bin/env python3
"""Run the weekly/manual live Postgres backend alert-confidence bundle."""

from __future__ import annotations

from postgres_alert_weekly_confidence_support import run_live_postgres_test_group


BACKEND_CONFIDENCE_TESTS: tuple[str, ...] = (
    "tests/test_session_alert_store_postgres.py::test_real_postgres_alert_store_smoke_round_trip",
    "tests/test_session_alert_store_postgres.py::test_real_postgres_alert_store_preserves_exact_timestamp_round_trip",
    "tests/test_session_alert_store_postgres.py::test_real_postgres_alert_store_preserves_append_order_for_same_timestamp_alerts",
    "tests/test_session_alert_store_postgres.py::test_real_postgres_bootstrap_succeeds_without_auto_create_when_schema_already_exists",
    "tests/test_api_session_alerts.py::test_live_runtime_postgres_alert_routes_follow_actual_startup_path",
    "tests/test_api_session_alert_incidents.py::test_live_runtime_postgres_grouped_routes_follow_actual_startup_path",
    "tests/test_api_session_alert_incidents.py::test_live_runtime_postgres_grouped_routes_preserve_filtered_results",
    "tests/test_mcp_server_incidents_behavior.py::test_live_runtime_postgres_mcp_raw_and_grouped_tools_agree",
)


def main() -> int:
    """Run the seeded live-Postgres backend confidence bundle."""
    return run_live_postgres_test_group(
        "weekly/manual live Postgres backend confidence bundle",
        BACKEND_CONFIDENCE_TESTS,
    )


if __name__ == "__main__":
    raise SystemExit(main())
