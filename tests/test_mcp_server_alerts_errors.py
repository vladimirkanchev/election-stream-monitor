"""Negative-path tests for raw MCP alert-query tools.

This file owns raw MCP tool-level error mapping:

- missing-session failures
- invalid time-range failures
- invalid timestamp-format failures
- list/summary parity where both raw tools should expose the same MCP error contract

Keeping these checks apart from the usable payload file makes raw MCP adapter
drift easier to spot: payload regressions fail in one place, error-translation
regressions fail in another.
"""

from collections.abc import Iterator

import esm_mcp.alert_tools as alert_tools
import pytest
from session_alert_store import clear_default_session_alert_store_cache
from session_alert_store_runtime_config import ALERT_STORE_BACKEND_ENV
from session_alerts import SessionAlertsNotFoundError
from tests.mcp_alert_test_support import call_mcp_tool
from tests.mcp_server_alerts_test_support import assert_mcp_tool_error


@pytest.fixture(autouse=True)
def _clear_default_alert_store_cache() -> Iterator[None]:
    """Keep runtime-selected default-store caching isolated in raw MCP error tests."""
    clear_default_session_alert_store_cache()
    yield
    clear_default_session_alert_store_cache()


def _assert_raw_tool_maps_service_error(
    monkeypatch,
    *,
    tool_name: str,
    service_attr: str,
    session_id: str,
    tool_arguments: dict[str, str],
    service_error: Exception,
    expected_message: str,
) -> None:
    """Assert one raw MCP tool maps a shared-service error into MCP error text."""

    def fake_alert_service(
        current_session_id: str,
        **_: object,
    ) -> object:
        assert current_session_id == session_id
        raise service_error

    monkeypatch.setattr(alert_tools, service_attr, fake_alert_service)

    result = call_mcp_tool(
        tool_name,
        {"session_id": session_id, **tool_arguments},
    )

    assert_mcp_tool_error(result, expected_message=expected_message)


def test_query_session_alerts_tool_reports_missing_session_as_tool_error(
    monkeypatch,
) -> None:
    """Unknown sessions should become MCP tool errors, not transport crashes."""
    _assert_raw_tool_maps_service_error(
        monkeypatch,
        tool_name="query_session_alerts",
        service_attr="filter_session_alert_events",
        session_id="missing-session",
        tool_arguments={},
        service_error=SessionAlertsNotFoundError("missing-session"),
        expected_message="Session not found: missing-session",
    )


def test_summarize_session_alerts_tool_reports_invalid_time_range_as_tool_error(
    monkeypatch,
) -> None:
    """Service validation failures should surface as readable MCP tool errors."""
    expected_message = "start_time_utc must be earlier than or equal to end_time_utc"
    _assert_raw_tool_maps_service_error(
        monkeypatch,
        tool_name="summarize_session_alerts",
        service_attr="summarize_session_alert_events",
        session_id="session-mcp-invalid-range",
        tool_arguments={
            "start_time_utc": "2026-05-06 10:10:00",
            "end_time_utc": "2026-05-06 10:00:00",
        },
        service_error=ValueError(expected_message),
        expected_message=expected_message,
    )


@pytest.mark.parametrize(
    ("tool_name", "service_attr", "session_id"),
    [
        (
            "query_session_alerts",
            "filter_session_alert_events",
            "session-mcp-invalid-query-format",
        ),
        (
            "summarize_session_alerts",
            "summarize_session_alert_events",
            "session-mcp-invalid-summary-format",
        ),
    ],
)
def test_raw_mcp_alert_tools_report_invalid_timestamp_format_as_tool_error(
    monkeypatch,
    tool_name: str,
    service_attr: str,
    session_id: str,
) -> None:
    """Malformed raw-tool timestamp filters should stay readable and aligned."""
    expected_message = (
        "start_time_utc must use UTC timestamp format '%Y-%m-%d %H:%M:%S'"
    )
    _assert_raw_tool_maps_service_error(
        monkeypatch,
        tool_name=tool_name,
        service_attr=service_attr,
        session_id=session_id,
        tool_arguments={"start_time_utc": "not-a-time"},
        service_error=ValueError(expected_message),
        expected_message=expected_message,
    )


def test_query_session_alerts_tool_reports_runtime_postgres_bootstrap_failure(
    monkeypatch,
) -> None:
    """Explicit Postgres mode should surface bootstrap failures as MCP tool errors."""
    monkeypatch.setenv(ALERT_STORE_BACKEND_ENV, "postgres")
    monkeypatch.setattr(
        "session_alert_store._build_postgres_default_session_alert_store",
        lambda: (_ for _ in ()).throw(RuntimeError("postgres bootstrap failed")),
    )
    clear_default_session_alert_store_cache()

    result = call_mcp_tool(
        "query_session_alerts",
        {"session_id": "session-runtime-postgres-mcp-error"},
    )

    assert_mcp_tool_error(result, expected_message="postgres bootstrap failed")
