"""Negative-path tests for grouped MCP incident timeline and summary tools.

This file owns grouped MCP tool-level error mapping:

- missing-session failures
- invalid time-range failures
- invalid timestamp-format failures
- timeline/summary parity where both grouped tools should expose the same MCP
  error contract

Keeping these checks apart from the grouped payload file makes incident/timeline
output regressions and grouped error-translation regressions fail in distinct,
easy-to-scan places.
"""

import esm_mcp.alert_tools as alert_tools
import pytest
from session_alerts import SessionAlertsNotFoundError
from tests.mcp_alert_test_support import call_mcp_tool
from tests.mcp_server_incidents_test_support import assert_mcp_tool_error


def _assert_grouped_tool_maps_service_error(
    monkeypatch,
    *,
    tool_name: str,
    service_attr: str,
    session_id: str,
    tool_arguments: dict[str, str],
    service_error: Exception,
    expected_message: str,
) -> None:
    """Assert one grouped MCP tool maps a shared-service error into MCP error text."""

    def fake_grouped_service(
        current_session_id: str,
        **_: object,
    ) -> dict[str, object]:
        assert current_session_id == session_id
        raise service_error

    monkeypatch.setattr(alert_tools, service_attr, fake_grouped_service)

    result = call_mcp_tool(
        tool_name,
        {"session_id": session_id, **tool_arguments},
    )

    assert_mcp_tool_error(result, expected_message=expected_message)


def test_query_session_alert_timeline_tool_reports_missing_session_as_tool_error(
    monkeypatch,
) -> None:
    """Timeline tool failures should reuse the ordinary MCP tool error contract."""
    _assert_grouped_tool_maps_service_error(
        monkeypatch,
        tool_name="query_session_alert_timeline",
        service_attr="build_session_timeline",
        session_id="missing-session",
        tool_arguments={},
        service_error=SessionAlertsNotFoundError("missing-session"),
        expected_message="Session not found: missing-session",
    )


@pytest.mark.parametrize(
    ("tool_name", "service_attr", "session_id"),
    [
        (
            "query_session_alert_timeline",
            "build_session_timeline",
            "session-mcp-timeline-invalid-range",
        ),
        (
            "summarize_session_alert_incidents",
            "build_session_incident_summary",
            "session-mcp-incident-invalid-range",
        ),
    ],
)
def test_grouped_mcp_tools_report_invalid_time_range_as_tool_error(
    monkeypatch,
    tool_name: str,
    service_attr: str,
    session_id: str,
) -> None:
    """Grouped MCP tools should keep the same invalid-range error contract."""
    expected_message = "start_time_utc must be earlier than or equal to end_time_utc"
    _assert_grouped_tool_maps_service_error(
        monkeypatch,
        tool_name=tool_name,
        service_attr=service_attr,
        session_id=session_id,
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
            "query_session_alert_timeline",
            "build_session_timeline",
            "session-mcp-timeline-invalid-format",
        ),
        (
            "summarize_session_alert_incidents",
            "build_session_incident_summary",
            "session-mcp-incident-invalid-format",
        ),
    ],
)
def test_grouped_mcp_tools_report_invalid_timestamp_format_as_tool_error(
    monkeypatch,
    tool_name: str,
    service_attr: str,
    session_id: str,
) -> None:
    """Malformed grouped MCP timestamp filters should stay readable and aligned."""
    expected_message = (
        "start_time_utc must use UTC timestamp format '%Y-%m-%d %H:%M:%S'"
    )
    _assert_grouped_tool_maps_service_error(
        monkeypatch,
        tool_name=tool_name,
        service_attr=service_attr,
        session_id=session_id,
        tool_arguments={"start_time_utc": "not-a-time"},
        service_error=ValueError(expected_message),
        expected_message=expected_message,
    )
