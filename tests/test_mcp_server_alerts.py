"""Behavior tests for raw MCP alert-query tools.

These tests complement the MCP contract file by proving that the registered
tools call the shared raw alert-query service correctly and surface readable
success and error results through the real in-memory MCP transport seam.

This file owns:

- raw alert list and summary tool success payloads
- shared filter propagation into the raw read model
- tool-level error mapping for raw alert queries

Incident-oriented MCP behavior lives in ``test_mcp_server_incidents.py``.
FastAPI-versus-MCP boundary-split behavior lives in
``test_mcp_fastapi_boundary_split.py``.

The file stays intentionally free of FastAPI auth/rate-limit assertions so the
raw tool behavior is easy to review on its own.
"""

from pathlib import Path

from tests.mcp_alert_test_support import call_mcp_tool, list_mcp_tools, tool_error_text
from tests.session_alert_test_support import (
    build_alert_summary_payload,
    build_normalized_alert,
    build_persisted_alert,
    configure_session_alert_test,
    write_known_session,
)


# Raw MCP behavior over the shared alert-query service


def test_list_tools_then_call_query_session_alerts_end_to_end_with_filters(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Listing then calling the query tool should work with real filter inputs."""
    session_root = configure_session_alert_test(monkeypatch, tmp_path)
    write_known_session(
        session_root,
        "session-mcp-e2e",
        alert_rows=[
            build_persisted_alert(
                "session-mcp-e2e",
                timestamp_utc="2026-05-06 10:00:00",
                detector_id="video_metrics",
                title="Black screen detected",
                message="Black segment.",
                severity="warning",
                source_name="segment_0001.ts",
            ),
            build_persisted_alert(
                "session-mcp-e2e",
                timestamp_utc="2026-05-06 10:00:10",
                detector_id="video_metrics",
                title="Black screen detected",
                message="Black segment again.",
                severity="warning",
                source_name="segment_0002.ts",
            ),
            build_persisted_alert(
                "session-mcp-e2e",
                timestamp_utc="2026-05-06 10:00:20",
                detector_id="video_blur",
                title="Blur increased",
                message="Blur threshold exceeded.",
                severity="info",
                source_name="segment_0003.ts",
            ),
        ],
    )

    tools = list_mcp_tools()
    assert any(tool.name == "query_session_alerts" for tool in tools.tools)

    result = call_mcp_tool(
        "query_session_alerts",
        {
            "session_id": "session-mcp-e2e",
            "detector_id": "video_metrics",
            "severity": "warning",
            "start_time_utc": "2026-05-06 10:00:05",
            "end_time_utc": "2026-05-06 10:00:15",
        },
    )

    assert result.isError is False
    assert result.structuredContent == {
        "session_id": "session-mcp-e2e",
        "alerts": [
            build_normalized_alert(
                "session-mcp-e2e",
                timestamp_utc="2026-05-06 10:00:10",
                detector_id="video_metrics",
                title="Black screen detected",
                message="Black segment again.",
                severity="warning",
                source_name="segment_0002.ts",
            )
        ],
    }


# Raw alert summary behavior


def test_summarize_session_alerts_tool_returns_structured_summary(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """The summary tool should return the stable numeric summary contract."""
    session_root = configure_session_alert_test(monkeypatch, tmp_path)
    write_known_session(
        session_root,
        "session-mcp-summary",
        alert_rows=[
            build_persisted_alert(
                "session-mcp-summary",
                timestamp_utc="2026-05-06 10:00:00",
                detector_id="video_metrics",
                title="Black screen detected",
                message="Black segment.",
                severity="warning",
                source_name="segment_0001.ts",
            ),
            build_persisted_alert(
                "session-mcp-summary",
                timestamp_utc="2026-05-06 10:00:20",
                detector_id="video_blur",
                title="Blur increased",
                message="Blur threshold exceeded.",
                severity="info",
                source_name="segment_0002.ts",
            ),
        ],
    )

    result = call_mcp_tool(
        "summarize_session_alerts",
        {"session_id": "session-mcp-summary"},
    )

    assert result.isError is False
    assert result.structuredContent == build_alert_summary_payload(
        "session-mcp-summary",
        total_alerts=2,
        counts_by_detector={"video_metrics": 1, "video_blur": 1},
        counts_by_severity={"warning": 1, "info": 1},
        first_alert_timestamp_utc="2026-05-06 10:00:00",
        last_alert_timestamp_utc="2026-05-06 10:00:20",
    )


def test_summarize_session_alerts_tool_applies_filters(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """The summary tool should respect detector, severity, and time-range filters."""
    session_root = configure_session_alert_test(monkeypatch, tmp_path)
    write_known_session(
        session_root,
        "session-mcp-summary-filtered",
        alert_rows=[
            build_persisted_alert(
                "session-mcp-summary-filtered",
                timestamp_utc="2026-05-06 10:00:00",
                detector_id="video_metrics",
                title="Black screen detected",
                message="Outside the time window.",
                severity="warning",
                source_name="segment_0001.ts",
            ),
            build_persisted_alert(
                "session-mcp-summary-filtered",
                timestamp_utc="2026-05-06 10:00:10",
                detector_id="video_metrics",
                title="Black screen detected",
                message="Should match.",
                severity="warning",
                source_name="segment_0002.ts",
            ),
            build_persisted_alert(
                "session-mcp-summary-filtered",
                timestamp_utc="2026-05-06 10:00:20",
                detector_id="video_blur",
                title="Blur increased",
                message="Wrong detector and severity.",
                severity="info",
                source_name="segment_0003.ts",
            ),
        ],
    )

    result = call_mcp_tool(
        "summarize_session_alerts",
        {
            "session_id": "session-mcp-summary-filtered",
            "detector_id": "video_metrics",
            "severity": "warning",
            "start_time_utc": "2026-05-06 10:00:05",
            "end_time_utc": "2026-05-06 10:00:15",
        },
    )

    assert result.isError is False
    assert result.structuredContent == build_alert_summary_payload(
        "session-mcp-summary-filtered",
        total_alerts=1,
        counts_by_detector={"video_metrics": 1},
        counts_by_severity={"warning": 1},
        first_alert_timestamp_utc="2026-05-06 10:00:10",
        last_alert_timestamp_utc="2026-05-06 10:00:10",
    )


# Tool-level error mapping


def test_query_session_alerts_tool_reports_missing_session_as_tool_error() -> None:
    """Unknown sessions should become MCP tool errors, not transport crashes."""
    result = call_mcp_tool(
        "query_session_alerts",
        {"session_id": "missing-session"},
    )

    assert result.isError is True
    assert "Session not found: missing-session" in tool_error_text(result)


def test_summarize_session_alerts_tool_reports_invalid_time_range_as_tool_error(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Service validation failures should surface as readable MCP tool errors."""
    session_root = configure_session_alert_test(monkeypatch, tmp_path)
    write_known_session(session_root, "session-mcp-invalid-range")

    result = call_mcp_tool(
        "summarize_session_alerts",
        {
            "session_id": "session-mcp-invalid-range",
            "start_time_utc": "2026-05-06 10:10:00",
            "end_time_utc": "2026-05-06 10:00:00",
        },
    )

    assert result.isError is True
    assert (
        "start_time_utc must be earlier than or equal to end_time_utc"
        in tool_error_text(result)
    )
