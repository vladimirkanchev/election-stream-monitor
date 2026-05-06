"""Behavior tests for MCP alert tools over the real in-memory MCP session.

These tests complement the MCP contract file by proving that the registered
tools call the shared alert-query service correctly and surface operator-meaningful
success and error results.
"""

from pathlib import Path

import anyio

from esm_mcp.server import build_mcp_server
from mcp.shared.memory import create_connected_server_and_client_session
from tests.session_alert_test_support import (
    build_normalized_alert,
    build_persisted_alert,
    configure_session_alert_test,
    write_known_session,
)


def _text_content(result) -> str:
    """Flatten MCP text content blocks for concise error assertions."""
    return "\n".join(
        content.text for content in result.content if hasattr(content, "text")
    )


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

    async def run() -> None:
        async with create_connected_server_and_client_session(build_mcp_server()) as session:
            tools = await session.list_tools()
            assert any(tool.name == "query_session_alerts" for tool in tools.tools)

            result = await session.call_tool(
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

    anyio.run(run)


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

    async def run() -> None:
        async with create_connected_server_and_client_session(build_mcp_server()) as session:
            result = await session.call_tool(
                "summarize_session_alerts",
                {
                    "session_id": "session-mcp-summary",
                },
            )
            assert result.isError is False
            assert result.structuredContent == {
                "session_id": "session-mcp-summary",
                "total_alerts": 2,
                "counts_by_detector": {
                    "video_metrics": 1,
                    "video_blur": 1,
                },
                "counts_by_severity": {
                    "warning": 1,
                    "info": 1,
                },
                "first_alert_timestamp_utc": "2026-05-06 10:00:00",
                "last_alert_timestamp_utc": "2026-05-06 10:00:20",
            }

    anyio.run(run)


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

    async def run() -> None:
        async with create_connected_server_and_client_session(build_mcp_server()) as session:
            result = await session.call_tool(
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
            assert result.structuredContent == {
                "session_id": "session-mcp-summary-filtered",
                "total_alerts": 1,
                "counts_by_detector": {
                    "video_metrics": 1,
                },
                "counts_by_severity": {
                    "warning": 1,
                },
                "first_alert_timestamp_utc": "2026-05-06 10:00:10",
                "last_alert_timestamp_utc": "2026-05-06 10:00:10",
            }

    anyio.run(run)


def test_query_session_alerts_tool_reports_missing_session_as_tool_error() -> None:
    """Unknown sessions should become MCP tool errors, not transport crashes."""
    async def run() -> None:
        async with create_connected_server_and_client_session(build_mcp_server()) as session:
            result = await session.call_tool(
                "query_session_alerts",
                {"session_id": "missing-session"},
            )
            assert result.isError is True
            assert "Session not found: missing-session" in _text_content(result)

    anyio.run(run)


def test_summarize_session_alerts_tool_reports_invalid_time_range_as_tool_error(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Service validation failures should surface as readable MCP tool errors."""
    session_root = configure_session_alert_test(monkeypatch, tmp_path)
    write_known_session(session_root, "session-mcp-invalid-range")

    async def run() -> None:
        async with create_connected_server_and_client_session(build_mcp_server()) as session:
            result = await session.call_tool(
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
                in _text_content(result)
            )

    anyio.run(run)
