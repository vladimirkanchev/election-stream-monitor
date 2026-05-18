"""Behavior tests for grouped MCP incident timeline and summary tools.

This file owns the usable grouped MCP payload surface:

- grouped timeline and grouped incident-summary success payloads
- known-session no-alert grouped outputs
- filtered grouped outputs
- known-session unknown-filter empty grouped outputs

It intentionally keeps grouped payload behavior separate from grouped MCP
error translation so incident/timeline output drift is easier to review on its
own. Negative-path grouped MCP transport mapping lives in
``test_mcp_server_incidents_errors.py``.
"""

from pathlib import Path

import esm_mcp.alert_tools as alert_tools
from tests.mcp_alert_test_support import call_mcp_tool
from tests.mcp_server_incidents_test_support import (
    assert_mcp_tool_success,
    write_empty_incident_session,
    write_known_incident_alert_session,
    write_incident_tool_session,
)
from tests.session_alert_test_support import (
    build_incident_summary_payload,
    build_persisted_alert,
    build_timeline_entry,
    write_known_session,
)


def test_query_session_alert_timeline_tool_returns_grouped_entries(
    monkeypatch,
) -> None:
    """The timeline tool should expose the grouped incident timeline contract."""

    def fake_build_session_timeline(
        session_id: str,
        *,
        detector_id: str | None = None,
        severity: str | None = None,
        start_time_utc: str | None = None,
        end_time_utc: str | None = None,
    ) -> dict[str, object]:
        assert session_id == "session-mcp-timeline"
        assert detector_id is None
        assert severity is None
        assert start_time_utc is None
        assert end_time_utc is None
        return {
            "session_id": session_id,
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
                )
            ],
        }

    monkeypatch.setattr(
        alert_tools,
        "build_session_timeline",
        fake_build_session_timeline,
    )

    result = call_mcp_tool(
        "query_session_alert_timeline",
        {"session_id": "session-mcp-timeline"},
    )

    assert_mcp_tool_success(
        result,
        expected_payload={
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
            ],
        },
    )


def test_summarize_session_alert_incidents_tool_returns_grouped_summary(
    monkeypatch,
) -> None:
    """The incident summary tool should expose grouped counts and categories."""

    def fake_build_session_incident_summary(
        session_id: str,
        *,
        detector_id: str | None = None,
        severity: str | None = None,
        start_time_utc: str | None = None,
        end_time_utc: str | None = None,
    ) -> dict[str, object]:
        assert session_id == "session-mcp-incident-summary"
        assert detector_id is None
        assert severity is None
        assert start_time_utc is None
        assert end_time_utc is None
        return build_incident_summary_payload(
            session_id,
            total_alerts=1,
            total_incidents=1,
            counts_by_detector={"video_metrics": 1},
            counts_by_severity={"warning": 1},
            top_incident_categories={"Black screen detected": 1},
            first_alert_timestamp_utc="2026-05-06 10:00:00",
            last_alert_timestamp_utc="2026-05-06 10:00:00",
            narrative_summary=(
                "Session session-mcp-incident-summary had 1 grouped incidents "
                "across 1 alerts."
            ),
        )

    monkeypatch.setattr(
        alert_tools,
        "build_session_incident_summary",
        fake_build_session_incident_summary,
    )

    result = call_mcp_tool(
        "summarize_session_alert_incidents",
        {"session_id": "session-mcp-incident-summary"},
    )

    assert_mcp_tool_success(
        result,
        expected_payload=build_incident_summary_payload(
            "session-mcp-incident-summary",
            total_alerts=1,
            total_incidents=1,
            counts_by_detector={"video_metrics": 1},
            counts_by_severity={"warning": 1},
            top_incident_categories={"Black screen detected": 1},
            first_alert_timestamp_utc="2026-05-06 10:00:00",
            last_alert_timestamp_utc="2026-05-06 10:00:00",
            narrative_summary=(
                "Session session-mcp-incident-summary had 1 grouped incidents "
                "across 1 alerts."
            ),
        ),
    )


def test_query_session_alert_timeline_tool_returns_empty_entries_for_known_session_without_alerts(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Known no-alert sessions should still expose a usable empty grouped timeline."""
    write_empty_incident_session(monkeypatch, tmp_path, "session-mcp-empty-timeline")

    result = call_mcp_tool(
        "query_session_alert_timeline",
        {"session_id": "session-mcp-empty-timeline"},
    )

    assert_mcp_tool_success(
        result,
        expected_payload={
            "session_id": "session-mcp-empty-timeline",
            "entries": [],
        },
    )


def test_summarize_session_alert_incidents_tool_returns_empty_summary_for_known_session_without_alerts(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Known no-alert sessions should still expose the stable empty grouped summary."""
    write_empty_incident_session(
        monkeypatch,
        tmp_path,
        "session-mcp-empty-incident-summary",
    )

    result = call_mcp_tool(
        "summarize_session_alert_incidents",
        {"session_id": "session-mcp-empty-incident-summary"},
    )

    assert_mcp_tool_success(
        result,
        expected_payload=build_incident_summary_payload(
            "session-mcp-empty-incident-summary",
            total_alerts=0,
            total_incidents=0,
            counts_by_detector={},
            counts_by_severity={},
            top_incident_categories={},
            first_alert_timestamp_utc=None,
            last_alert_timestamp_utc=None,
            narrative_summary="Session session-mcp-empty-incident-summary had no alerts.",
        ),
    )


def test_grouped_mcp_alert_tools_read_the_real_file_backed_seam(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """The grouped MCP tools should work over the real file-backed alert seam."""
    session_root = write_incident_tool_session(monkeypatch, tmp_path)
    write_known_session(
        session_root,
        "session-mcp-real-incidents",
        alert_rows=[
            build_persisted_alert(
                "session-mcp-real-incidents",
                timestamp_utc="2026-05-06 10:00:00",
                detector_id="video_metrics",
                title="Black screen detected",
                message="First grouped MCP row.",
                severity="warning",
                source_name="segment_0001.ts",
            ),
            build_persisted_alert(
                "session-mcp-real-incidents",
                timestamp_utc="2026-05-06 10:00:30",
                detector_id="video_metrics",
                title="Black screen detected",
                message="Second grouped MCP row.",
                severity="warning",
                source_name="segment_0002.ts",
            ),
            build_persisted_alert(
                "session-mcp-real-incidents",
                timestamp_utc="2026-05-06 10:02:00",
                detector_id="video_blur",
                title="Blur increased",
                message="Separate grouped MCP incident.",
                severity="info",
                source_name="segment_0003.ts",
            ),
        ],
    )

    timeline_result = call_mcp_tool(
        "query_session_alert_timeline",
        {"session_id": "session-mcp-real-incidents"},
    )
    summary_result = call_mcp_tool(
        "summarize_session_alert_incidents",
        {"session_id": "session-mcp-real-incidents"},
    )

    assert_mcp_tool_success(
        timeline_result,
        expected_payload={
            "session_id": "session-mcp-real-incidents",
            "entries": [
                build_timeline_entry(
                    start_time_utc="2026-05-06 10:00:00",
                    end_time_utc="2026-05-06 10:00:30",
                    detector_id="video_metrics",
                    severity="warning",
                    title="Black screen detected",
                    alert_count=2,
                    source_names=["segment_0001.ts", "segment_0002.ts"],
                    sample_message="First grouped MCP row.",
                ),
                build_timeline_entry(
                    start_time_utc="2026-05-06 10:02:00",
                    end_time_utc="2026-05-06 10:02:00",
                    detector_id="video_blur",
                    severity="info",
                    title="Blur increased",
                    alert_count=1,
                    source_names=["segment_0003.ts"],
                    sample_message="Separate grouped MCP incident.",
                ),
            ],
        },
    )
    summary_payload = summary_result.structuredContent
    assert_mcp_tool_success(
        summary_result,
        expected_payload=build_incident_summary_payload(
            "session-mcp-real-incidents",
            total_alerts=3,
            total_incidents=2,
            counts_by_detector={"video_metrics": 2, "video_blur": 1},
            counts_by_severity={"warning": 2, "info": 1},
            top_incident_categories={"Black screen detected": 1, "Blur increased": 1},
            first_alert_timestamp_utc="2026-05-06 10:00:00",
            last_alert_timestamp_utc="2026-05-06 10:02:00",
            narrative_summary=summary_payload["narrative_summary"],
        ),
    )


def test_grouped_mcp_alert_tools_preserve_filtered_query_results(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Grouped MCP tools should keep filtered timeline and summary outputs aligned."""
    session_root = write_incident_tool_session(monkeypatch, tmp_path)
    write_known_session(
        session_root,
        "session-mcp-filtered-incidents",
        alert_rows=[
            build_persisted_alert(
                "session-mcp-filtered-incidents",
                timestamp_utc="2026-05-06 10:00:00",
                detector_id="video_metrics",
                title="Black screen detected",
                message="Wrong severity for the filtered incident view.",
                severity="info",
                source_name="segment_0001.ts",
            ),
            build_persisted_alert(
                "session-mcp-filtered-incidents",
                timestamp_utc="2026-05-06 10:00:10",
                detector_id="video_metrics",
                title="Black screen detected",
                message="Expected warning incident start.",
                severity="warning",
                source_name="segment_0002.ts",
            ),
            build_persisted_alert(
                "session-mcp-filtered-incidents",
                timestamp_utc="2026-05-06 10:00:40",
                detector_id="video_metrics",
                title="Black screen detected",
                message="Expected warning incident continuation.",
                severity="warning",
                source_name="segment_0003.ts",
            ),
        ],
    )

    timeline_result = call_mcp_tool(
        "query_session_alert_timeline",
        {
            "session_id": "session-mcp-filtered-incidents",
            "severity": "warning",
        },
    )
    summary_result = call_mcp_tool(
        "summarize_session_alert_incidents",
        {
            "session_id": "session-mcp-filtered-incidents",
            "severity": "warning",
        },
    )

    assert_mcp_tool_success(
        timeline_result,
        expected_payload={
            "session_id": "session-mcp-filtered-incidents",
            "entries": [
                build_timeline_entry(
                    start_time_utc="2026-05-06 10:00:10",
                    end_time_utc="2026-05-06 10:00:40",
                    detector_id="video_metrics",
                    severity="warning",
                    title="Black screen detected",
                    alert_count=2,
                    source_names=["segment_0002.ts", "segment_0003.ts"],
                    sample_message="Expected warning incident start.",
                )
            ],
        },
    )
    assert_mcp_tool_success(
        summary_result,
        expected_payload=build_incident_summary_payload(
            "session-mcp-filtered-incidents",
            total_alerts=2,
            total_incidents=1,
            counts_by_detector={"video_metrics": 2},
            counts_by_severity={"warning": 2},
            top_incident_categories={"Black screen detected": 1},
            first_alert_timestamp_utc="2026-05-06 10:00:10",
            last_alert_timestamp_utc="2026-05-06 10:00:40",
            narrative_summary=(
                "Session session-mcp-filtered-incidents had 1 grouped incidents "
                "across 2 alerts, mostly from video_metrics, led by black screen "
                "detected, with 2 warning alerts and 0 info alerts."
            ),
        ),
    )


def test_query_session_alert_timeline_tool_returns_empty_entries_for_unknown_filter_values(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Unknown grouped-query filters should degrade to an empty timeline payload.

    This stays separate from the no-alert-session case because the grouped
    session exists and contains persisted data; only the filter set matches
    nothing.
    """
    write_known_incident_alert_session(
        monkeypatch,
        tmp_path,
        "session-mcp-unknown-timeline-filters",
    )

    result = call_mcp_tool(
        "query_session_alert_timeline",
        {
            "session_id": "session-mcp-unknown-timeline-filters",
            "detector_id": "unknown_detector",
        },
    )

    assert_mcp_tool_success(
        result,
        expected_payload={
            "session_id": "session-mcp-unknown-timeline-filters",
            "entries": [],
        },
    )


def test_summarize_session_alert_incidents_tool_returns_empty_summary_for_unknown_filter_values(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Unknown grouped-summary filters should degrade to the stable empty summary.

    Together with the grouped-query no-match test, this keeps the grouped
    timeline/summary parity explicit for the "known session, unmatched
    filters" contract.
    """
    write_known_incident_alert_session(
        monkeypatch,
        tmp_path,
        "session-mcp-unknown-incident-filters",
    )

    result = call_mcp_tool(
        "summarize_session_alert_incidents",
        {
            "session_id": "session-mcp-unknown-incident-filters",
            "detector_id": "unknown_detector",
        },
    )

    assert_mcp_tool_success(
        result,
        expected_payload=build_incident_summary_payload(
            "session-mcp-unknown-incident-filters",
            total_alerts=0,
            total_incidents=0,
            counts_by_detector={},
            counts_by_severity={},
            top_incident_categories={},
            first_alert_timestamp_utc=None,
            last_alert_timestamp_utc=None,
            narrative_summary="Session session-mcp-unknown-incident-filters had no alerts.",
        ),
    )
