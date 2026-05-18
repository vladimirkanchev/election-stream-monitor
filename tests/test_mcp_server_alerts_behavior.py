"""Behavior tests for raw MCP alert-query tools.

This file owns the usable raw MCP payload surface:

- raw query and raw summary success payloads
- known-session no-alert behavior
- filtered raw list and raw summary behavior
- known-session unknown-filter empty results

It intentionally keeps success-path tool behavior separate from MCP-facing
error translation so regressions in raw payload shaping are easier to localize.
Negative-path MCP transport mapping lives in
``test_mcp_server_alerts_errors.py``. FastAPI-versus-MCP trust-boundary and
parity coverage lives in ``test_mcp_fastapi_boundary_split.py``,
``test_mcp_fastapi_parity_behavior.py``, and
``test_mcp_fastapi_parity_edges.py``.
"""

from pathlib import Path

import esm_mcp.alert_tools as alert_tools
from tests.mcp_alert_test_support import call_mcp_tool
from tests.mcp_server_alerts_test_support import (
    assert_mcp_tool_success,
    write_empty_raw_alert_session,
    write_known_raw_alert_session,
    write_raw_alert_tool_session,
)
from tests.session_alert_test_support import (
    build_alert_summary_payload,
    build_normalized_alert,
    build_persisted_alert,
    write_known_session,
)


def test_query_session_alerts_tool_forwards_filters_and_preserves_payload(
    monkeypatch,
) -> None:
    """The raw query tool should stay a thin MCP adapter over the shared service."""

    def fake_filter_session_alert_events(
        session_id: str,
        *,
        detector_id: str | None = None,
        severity: str | None = None,
        start_time_utc: str | None = None,
        end_time_utc: str | None = None,
    ) -> list[dict[str, object]]:
        assert session_id == "session-mcp-e2e"
        assert detector_id == "video_metrics"
        assert severity == "warning"
        assert start_time_utc == "2026-05-06 10:00:05"
        assert end_time_utc == "2026-05-06 10:00:15"
        return [
            {
                "session_id": session_id,
                "timestamp_utc": "2026-05-06 10:00:10",
                "detector_id": "video_metrics",
                "title": "Black screen detected",
                "message": "Black segment again.",
                "severity": "warning",
                "source_name": "segment_0002.ts",
            }
        ]

    monkeypatch.setattr(
        alert_tools,
        "filter_session_alert_events",
        fake_filter_session_alert_events,
    )

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

    assert_mcp_tool_success(
        result,
        expected_payload={
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
        },
    )


def test_summarize_session_alerts_tool_returns_structured_summary(
    monkeypatch,
) -> None:
    """The summary tool should expose the stable raw numeric summary contract."""

    def fake_summarize_session_alert_events(
        session_id: str,
        *,
        detector_id: str | None = None,
        severity: str | None = None,
        start_time_utc: str | None = None,
        end_time_utc: str | None = None,
    ) -> dict[str, object]:
        assert session_id == "session-mcp-summary"
        assert detector_id is None
        assert severity is None
        assert start_time_utc is None
        assert end_time_utc is None
        return {
            "session_id": session_id,
            "total_alerts": 2,
            "counts_by_detector": {"video_metrics": 1, "video_blur": 1},
            "counts_by_severity": {"warning": 1, "info": 1},
            "first_alert_timestamp_utc": "2026-05-06 10:00:00",
            "last_alert_timestamp_utc": "2026-05-06 10:00:20",
        }

    monkeypatch.setattr(
        alert_tools,
        "summarize_session_alert_events",
        fake_summarize_session_alert_events,
    )

    result = call_mcp_tool(
        "summarize_session_alerts",
        {"session_id": "session-mcp-summary"},
    )

    assert_mcp_tool_success(
        result,
        expected_payload={
            "session_id": "session-mcp-summary",
            "total_alerts": 2,
            "counts_by_detector": {"video_metrics": 1, "video_blur": 1},
            "counts_by_severity": {"warning": 1, "info": 1},
            "first_alert_timestamp_utc": "2026-05-06 10:00:00",
            "last_alert_timestamp_utc": "2026-05-06 10:00:20",
        },
    )


def test_query_session_alerts_tool_returns_empty_payload_for_known_session_without_alerts(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Known no-alert sessions should still expose the stable empty list payload."""
    write_empty_raw_alert_session(
        monkeypatch,
        tmp_path,
        "session-mcp-empty-alert-list",
    )

    result = call_mcp_tool(
        "query_session_alerts",
        {"session_id": "session-mcp-empty-alert-list"},
    )

    assert_mcp_tool_success(
        result,
        expected_payload={
            "session_id": "session-mcp-empty-alert-list",
            "alerts": [],
        },
    )


def test_summarize_session_alerts_tool_returns_empty_summary_for_known_session_without_alerts(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Known no-alert sessions should still expose the stable empty summary."""
    write_empty_raw_alert_session(
        monkeypatch,
        tmp_path,
        "session-mcp-empty-alert-summary",
    )

    result = call_mcp_tool(
        "summarize_session_alerts",
        {"session_id": "session-mcp-empty-alert-summary"},
    )

    assert_mcp_tool_success(
        result,
        expected_payload=build_alert_summary_payload(
            "session-mcp-empty-alert-summary",
            total_alerts=0,
            counts_by_detector={},
            counts_by_severity={},
            first_alert_timestamp_utc=None,
            last_alert_timestamp_utc=None,
        ),
    )


def test_raw_mcp_alert_tools_preserve_filtered_query_results(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """The raw MCP tools should keep filtered list and summary outputs aligned."""
    session_root = write_raw_alert_tool_session(monkeypatch, tmp_path)
    write_known_session(
        session_root,
        "session-mcp-filtered-alerts",
        alert_rows=[
            build_persisted_alert(
                "session-mcp-filtered-alerts",
                timestamp_utc="2026-05-06 10:00:00",
                detector_id="video_blur",
                title="Blur increased",
                message="Wrong detector for the filtered query.",
                severity="info",
                source_name="segment_0001.ts",
            ),
            build_persisted_alert(
                "session-mcp-filtered-alerts",
                timestamp_utc="2026-05-06 10:00:10",
                detector_id="video_metrics",
                title="Black screen detected",
                message="Expected filtered result.",
                severity="warning",
                source_name="segment_0002.ts",
            ),
            build_persisted_alert(
                "session-mcp-filtered-alerts",
                timestamp_utc="2026-05-06 10:00:20",
                detector_id="video_metrics",
                title="Black screen detected",
                message="Wrong severity for the filtered query.",
                severity="info",
                source_name="segment_0003.ts",
            ),
        ],
    )

    query_result = call_mcp_tool(
        "query_session_alerts",
        {
            "session_id": "session-mcp-filtered-alerts",
            "detector_id": "video_metrics",
            "severity": "warning",
        },
    )
    summary_result = call_mcp_tool(
        "summarize_session_alerts",
        {
            "session_id": "session-mcp-filtered-alerts",
            "detector_id": "video_metrics",
            "severity": "warning",
        },
    )

    assert_mcp_tool_success(
        query_result,
        expected_payload={
            "session_id": "session-mcp-filtered-alerts",
            "alerts": [
                build_normalized_alert(
                    "session-mcp-filtered-alerts",
                    timestamp_utc="2026-05-06 10:00:10",
                    detector_id="video_metrics",
                    title="Black screen detected",
                    message="Expected filtered result.",
                    severity="warning",
                    source_name="segment_0002.ts",
                )
            ],
        },
    )
    assert_mcp_tool_success(
        summary_result,
        expected_payload=build_alert_summary_payload(
            "session-mcp-filtered-alerts",
            total_alerts=1,
            counts_by_detector={"video_metrics": 1},
            counts_by_severity={"warning": 1},
            first_alert_timestamp_utc="2026-05-06 10:00:10",
            last_alert_timestamp_utc="2026-05-06 10:00:10",
        ),
    )


def test_query_session_alerts_tool_returns_empty_payload_for_unknown_filter_values(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Unknown raw-query filters should degrade to a stable empty list payload.

    This stays separate from the no-alert-session case because the persisted
    session exists and contains data; only the filter set fails to match.
    """
    write_known_raw_alert_session(
        monkeypatch,
        tmp_path,
        "session-mcp-unknown-raw-query-filters",
    )

    result = call_mcp_tool(
        "query_session_alerts",
        {
            "session_id": "session-mcp-unknown-raw-query-filters",
            "detector_id": "unknown_detector",
        },
    )

    assert_mcp_tool_success(
        result,
        expected_payload={
            "session_id": "session-mcp-unknown-raw-query-filters",
            "alerts": [],
        },
    )


def test_summarize_session_alerts_tool_returns_empty_summary_for_unknown_filter_values(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Unknown raw-summary filters should degrade to the stable empty summary.

    Together with the raw-query no-match test, this keeps the list/summary
    parity explicit for the "known session, unmatched filters" contract.
    """
    write_known_raw_alert_session(
        monkeypatch,
        tmp_path,
        "session-mcp-unknown-raw-summary-filters",
    )

    result = call_mcp_tool(
        "summarize_session_alerts",
        {
            "session_id": "session-mcp-unknown-raw-summary-filters",
            "detector_id": "unknown_detector",
        },
    )

    assert_mcp_tool_success(
        result,
        expected_payload=build_alert_summary_payload(
            "session-mcp-unknown-raw-summary-filters",
            total_alerts=0,
            counts_by_detector={},
            counts_by_severity={},
            first_alert_timestamp_utc=None,
            last_alert_timestamp_utc=None,
        ),
    )
