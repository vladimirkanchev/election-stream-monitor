"""Behavior tests for MCP incident timeline and summary tools.

This file owns the grouped-incident MCP surface:

- timeline tool payloads
- incident-summary payloads
- empty-state behavior
- readable tool-level error mapping for validation failures
- narrative-summary and grouped-category transport behavior
"""

from pathlib import Path

from tests.mcp_alert_test_support import call_mcp_tool, tool_error_text
from tests.session_alert_test_support import (
    assert_narrative_contains,
    build_incident_summary_payload,
    build_timeline_entry,
    build_persisted_alert,
    configure_session_alert_test,
    write_known_session,
)


def test_query_session_alert_timeline_tool_returns_grouped_entries(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """The timeline tool should expose the grouped incident timeline contract."""
    session_root = configure_session_alert_test(monkeypatch, tmp_path)
    write_known_session(
        session_root,
        "session-mcp-timeline",
        alert_rows=[
            build_persisted_alert(
                "session-mcp-timeline",
                timestamp_utc="2026-05-06 10:00:00",
                detector_id="video_metrics",
                title="Black screen detected",
                message="Black segment started.",
                severity="warning",
                source_name="segment_0001.ts",
            ),
            build_persisted_alert(
                "session-mcp-timeline",
                timestamp_utc="2026-05-06 10:00:30",
                detector_id="video_metrics",
                title="Black screen detected",
                message="Black segment continued.",
                severity="warning",
                source_name="segment_0002.ts",
            ),
            build_persisted_alert(
                "session-mcp-timeline",
                timestamp_utc="2026-05-06 10:02:00",
                detector_id="video_blur",
                title="Blur increased",
                message="Blur threshold exceeded.",
                severity="info",
                source_name="segment_0003.ts",
            ),
        ],
    )

    result = call_mcp_tool(
        "query_session_alert_timeline",
        {"session_id": "session-mcp-timeline"},
    )

    assert result.isError is False
    assert result.structuredContent == {
        "session_id": "session-mcp-timeline",
        "entries": [
            build_timeline_entry(
                start_time_utc="2026-05-06 10:00:00",
                end_time_utc="2026-05-06 10:00:30",
                detector_id="video_metrics",
                severity="warning",
                title="Black screen detected",
                alert_count=2,
                source_names=["segment_0001.ts", "segment_0002.ts"],
                sample_message="Black segment started.",
            ),
            build_timeline_entry(
                start_time_utc="2026-05-06 10:02:00",
                end_time_utc="2026-05-06 10:02:00",
                detector_id="video_blur",
                severity="info",
                title="Blur increased",
                alert_count=1,
                source_names=["segment_0003.ts"],
                sample_message="Blur threshold exceeded.",
            ),
        ],
    }


def test_query_session_alert_timeline_tool_returns_empty_entries_for_known_empty_session(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Known sessions without alerts should still produce an empty timeline payload."""
    session_root = configure_session_alert_test(monkeypatch, tmp_path)
    write_known_session(session_root, "session-mcp-empty-timeline")

    result = call_mcp_tool(
        "query_session_alert_timeline",
        {"session_id": "session-mcp-empty-timeline"},
    )

    assert result.isError is False
    assert result.structuredContent == {
        "session_id": "session-mcp-empty-timeline",
        "entries": [],
    }


def test_summarize_session_alert_incidents_tool_returns_grouped_summary(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """The incident summary tool should expose grouped counts and categories."""
    session_root = configure_session_alert_test(monkeypatch, tmp_path)
    write_known_session(
        session_root,
        "session-mcp-incident-summary",
        alert_rows=[
            build_persisted_alert(
                "session-mcp-incident-summary",
                timestamp_utc="2026-05-06 10:00:00",
                detector_id="video_metrics",
                title="Black screen detected",
                message="Black segment started.",
                severity="warning",
                source_name="segment_0001.ts",
            ),
            build_persisted_alert(
                "session-mcp-incident-summary",
                timestamp_utc="2026-05-06 10:00:30",
                detector_id="video_metrics",
                title="Black screen detected",
                message="Black segment continued.",
                severity="warning",
                source_name="segment_0002.ts",
            ),
            build_persisted_alert(
                "session-mcp-incident-summary",
                timestamp_utc="2026-05-06 10:02:00",
                detector_id="video_blur",
                title="Blur increased",
                message="Blur threshold exceeded.",
                severity="info",
                source_name="segment_0003.ts",
            ),
        ],
    )

    result = call_mcp_tool(
        "summarize_session_alert_incidents",
        {"session_id": "session-mcp-incident-summary"},
    )

    assert result.isError is False
    payload = result.structuredContent
    assert payload == build_incident_summary_payload(
        "session-mcp-incident-summary",
        total_alerts=3,
        total_incidents=2,
        counts_by_detector={"video_metrics": 2, "video_blur": 1},
        counts_by_severity={"warning": 2, "info": 1},
        top_incident_categories={
            "Black screen detected": 1,
            "Blur increased": 1,
        },
        first_alert_timestamp_utc="2026-05-06 10:00:00",
        last_alert_timestamp_utc="2026-05-06 10:02:00",
        narrative_summary=payload["narrative_summary"],
    )
    assert_narrative_contains(
        payload["narrative_summary"],
        "session-mcp-incident-summary",
        "2 grouped incidents",
        "3 alerts",
        "video_metrics",
        "blur increased",
        "2 warning alerts",
        "1 info alerts",
    )


def test_summarize_session_alert_incidents_tool_returns_empty_summary_for_known_empty_session(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Known sessions without alerts should keep the empty incident-summary contract."""
    session_root = configure_session_alert_test(monkeypatch, tmp_path)
    write_known_session(session_root, "session-mcp-empty-incident-summary")

    result = call_mcp_tool(
        "summarize_session_alert_incidents",
        {"session_id": "session-mcp-empty-incident-summary"},
    )

    assert result.isError is False
    assert result.structuredContent == build_incident_summary_payload(
        "session-mcp-empty-incident-summary",
        total_alerts=0,
        total_incidents=0,
        counts_by_detector={},
        counts_by_severity={},
        top_incident_categories={},
        first_alert_timestamp_utc=None,
        last_alert_timestamp_utc=None,
        narrative_summary="Session session-mcp-empty-incident-summary had no alerts.",
    )


def test_query_session_alert_timeline_tool_reports_missing_session_as_tool_error() -> None:
    """Timeline tool failures should reuse the ordinary MCP tool error contract."""
    result = call_mcp_tool(
        "query_session_alert_timeline",
        {"session_id": "missing-session"},
    )

    assert result.isError is True
    assert "Session not found: missing-session" in tool_error_text(result)


def test_summarize_session_alert_incidents_tool_reports_invalid_time_range_as_tool_error(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Incident-summary tool validation should stay readable to MCP clients."""
    session_root = configure_session_alert_test(monkeypatch, tmp_path)
    write_known_session(session_root, "session-mcp-incident-invalid-range")

    result = call_mcp_tool(
        "summarize_session_alert_incidents",
        {
            "session_id": "session-mcp-incident-invalid-range",
            "start_time_utc": "2026-05-06 10:10:00",
            "end_time_utc": "2026-05-06 10:00:00",
        },
    )

    assert result.isError is True
    assert (
        "start_time_utc must be earlier than or equal to end_time_utc"
        in tool_error_text(result)
    )


def test_summarize_session_alert_incidents_tool_reports_invalid_timestamp_format(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Malformed timestamp filters should stay readable to MCP clients."""
    session_root = configure_session_alert_test(monkeypatch, tmp_path)
    write_known_session(session_root, "session-mcp-incident-invalid-format")

    result = call_mcp_tool(
        "summarize_session_alert_incidents",
        {
            "session_id": "session-mcp-incident-invalid-format",
            "start_time_utc": "not-a-time",
        },
    )

    assert result.isError is True
    assert (
        "start_time_utc must use UTC timestamp format '%Y-%m-%d %H:%M:%S'"
        in tool_error_text(result)
    )
