"""Behavior-focused FastAPI/MCP parity tests.

This file owns the normal cross-surface meaning checks for the current project
stage:

- unfiltered raw and grouped parity
- filtered raw and grouped parity
- known empty-session parity
- unknown-filter no-match parity
- one shared time-bounded parity slice

Validation-heavy and ordering-heavy parity edges live in
``tests/test_mcp_fastapi_parity_edges.py``. Trust-boundary independence stays
in ``tests/test_mcp_fastapi_boundary_split.py``. Shared parity setup and
meaning helpers stay in ``tests/mcp_fastapi_parity_test_support.py``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.mcp_fastapi_parity_test_support import (
    assert_grouped_parity_meaning,
    assert_raw_parity_meaning,
    clear_boundary_test_state,  # noqa: F401
    empty_incident_summary_meaning,
    empty_raw_summary_meaning,
    enable_fastapi_alert_route_for_cross_surface_reads,
    fetch_grouped_parity_payloads,
    fetch_raw_parity_payloads,
    write_parity_session,
)
from tests.session_alert_test_support import build_persisted_alert

pytestmark = pytest.mark.usefixtures("clear_boundary_test_state")


def test_fastapi_and_mcp_raw_alert_views_keep_equivalent_meaning_for_one_session(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """FastAPI and MCP raw reads should expose the same raw-alert meaning."""

    session_id = "session-parity-raw"
    write_parity_session(
        monkeypatch,
        tmp_path,
        session_id,
        alert_rows=(
            build_persisted_alert(
                session_id,
                timestamp_utc="2026-05-06 10:00:00",
                detector_id="video_metrics",
                title="Black screen detected",
                message="First warning alert.",
                severity="warning",
                source_name="segment_0001.ts",
            ),
            build_persisted_alert(
                session_id,
                timestamp_utc="2026-05-06 10:00:15",
                detector_id="video_blur",
                title="Blur increased",
                message="Second info alert.",
                severity="info",
                source_name="segment_0002.ts",
            ),
            build_persisted_alert(
                session_id,
                timestamp_utc="2026-05-06 10:00:30",
                detector_id="video_metrics",
                title="Black screen detected",
                message="Third warning alert.",
                severity="warning",
                source_name="segment_0003.ts",
            ),
        ),
    )
    enable_fastapi_alert_route_for_cross_surface_reads(monkeypatch)
    (
        fastapi_alert_payload,
        fastapi_summary_payload,
        mcp_alert_payload,
        mcp_summary_payload,
    ) = fetch_raw_parity_payloads(session_id)

    assert_raw_parity_meaning(
        fastapi_alert_payload,
        fastapi_summary_payload,
        mcp_alert_payload,
        mcp_summary_payload,
        expected_count=3,
        expected_summary_meaning={
            "total_alerts": 3,
            "counts_by_detector": {"video_metrics": 2, "video_blur": 1},
            "counts_by_severity": {"warning": 2, "info": 1},
            "first_alert_timestamp_utc": "2026-05-06 10:00:00",
            "last_alert_timestamp_utc": "2026-05-06 10:00:30",
        },
    )


def test_fastapi_and_mcp_grouped_incident_views_keep_equivalent_meaning_for_one_session(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """FastAPI and MCP grouped reads should expose the same grouped meaning."""

    session_id = "session-parity-grouped"
    write_parity_session(
        monkeypatch,
        tmp_path,
        session_id,
        alert_rows=(
            build_persisted_alert(
                session_id,
                timestamp_utc="2026-05-06 10:00:00",
                detector_id="video_metrics",
                title="Black screen detected",
                message="Incident one, first row.",
                severity="warning",
                source_name="segment_0001.ts",
            ),
            build_persisted_alert(
                session_id,
                timestamp_utc="2026-05-06 10:00:30",
                detector_id="video_metrics",
                title="Black screen detected",
                message="Incident one, second row.",
                severity="warning",
                source_name="segment_0002.ts",
            ),
            build_persisted_alert(
                session_id,
                timestamp_utc="2026-05-06 10:02:00",
                detector_id="video_blur",
                title="Blur increased",
                message="Incident two.",
                severity="info",
                source_name="segment_0003.ts",
            ),
        ),
    )
    enable_fastapi_alert_route_for_cross_surface_reads(monkeypatch)
    (
        fastapi_timeline_payload,
        fastapi_summary_payload,
        mcp_timeline_payload,
        mcp_summary_payload,
    ) = fetch_grouped_parity_payloads(session_id)

    assert_grouped_parity_meaning(
        fastapi_timeline_payload,
        fastapi_summary_payload,
        mcp_timeline_payload,
        mcp_summary_payload,
        expected_count=2,
        expected_summary_meaning={
            "total_incidents": 2,
            "total_alerts": 3,
            "counts_by_detector": {"video_metrics": 2, "video_blur": 1},
            "counts_by_severity": {"warning": 2, "info": 1},
            "top_incident_categories": {
                "Black screen detected": 1,
                "Blur increased": 1,
            },
        },
    )


def test_fastapi_and_mcp_raw_alert_views_keep_equivalent_meaning_for_filtered_query(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """FastAPI and MCP raw reads should stay aligned for one filtered query.

    This keeps filter forwarding parity explicit at the raw read layer instead
    of relying on the adapter suites separately.
    """

    session_id = "session-parity-filtered-raw"
    write_parity_session(
        monkeypatch,
        tmp_path,
        session_id,
        alert_rows=(
            build_persisted_alert(
                session_id,
                timestamp_utc="2026-05-06 10:00:00",
                detector_id="video_blur",
                title="Blur increased",
                message="Wrong detector for the filtered view.",
                severity="warning",
                source_name="segment_0001.ts",
            ),
            build_persisted_alert(
                session_id,
                timestamp_utc="2026-05-06 10:00:10",
                detector_id="video_metrics",
                title="Black screen detected",
                message="Expected filtered warning.",
                severity="warning",
                source_name="segment_0002.ts",
            ),
            build_persisted_alert(
                session_id,
                timestamp_utc="2026-05-06 10:00:20",
                detector_id="video_metrics",
                title="Black screen detected",
                message="Wrong severity for the filtered view.",
                severity="info",
                source_name="segment_0003.ts",
            ),
        ),
    )
    enable_fastapi_alert_route_for_cross_surface_reads(monkeypatch)
    (
        fastapi_alert_payload,
        fastapi_summary_payload,
        mcp_alert_payload,
        mcp_summary_payload,
    ) = fetch_raw_parity_payloads(
        session_id,
        query_string="?detector_id=video_metrics&severity=warning",
        mcp_arguments={
            "detector_id": "video_metrics",
            "severity": "warning",
        },
    )

    assert_raw_parity_meaning(
        fastapi_alert_payload,
        fastapi_summary_payload,
        mcp_alert_payload,
        mcp_summary_payload,
        expected_count=1,
        expected_summary_meaning={
            "total_alerts": 1,
            "counts_by_detector": {"video_metrics": 1},
            "counts_by_severity": {"warning": 1},
            "first_alert_timestamp_utc": "2026-05-06 10:00:10",
            "last_alert_timestamp_utc": "2026-05-06 10:00:10",
        },
    )


def test_fastapi_and_mcp_grouped_incident_views_keep_equivalent_meaning_for_filtered_query(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """FastAPI and MCP grouped reads should stay aligned for one filtered query.

    Grouping after filtering is a higher-risk drift seam than unfiltered reads,
    so this contract stays explicit here.
    """

    session_id = "session-parity-filtered-grouped"
    write_parity_session(
        monkeypatch,
        tmp_path,
        session_id,
        alert_rows=(
            build_persisted_alert(
                session_id,
                timestamp_utc="2026-05-06 10:00:00",
                detector_id="video_metrics",
                title="Black screen detected",
                message="Wrong severity for the grouped filtered view.",
                severity="info",
                source_name="segment_0001.ts",
            ),
            build_persisted_alert(
                session_id,
                timestamp_utc="2026-05-06 10:00:10",
                detector_id="video_metrics",
                title="Black screen detected",
                message="Expected warning incident start.",
                severity="warning",
                source_name="segment_0002.ts",
            ),
            build_persisted_alert(
                session_id,
                timestamp_utc="2026-05-06 10:00:40",
                detector_id="video_metrics",
                title="Black screen detected",
                message="Expected warning incident continuation.",
                severity="warning",
                source_name="segment_0003.ts",
            ),
        ),
    )
    enable_fastapi_alert_route_for_cross_surface_reads(monkeypatch)
    (
        fastapi_timeline_payload,
        fastapi_summary_payload,
        mcp_timeline_payload,
        mcp_summary_payload,
    ) = fetch_grouped_parity_payloads(
        session_id,
        query_string="?severity=warning",
        mcp_arguments={"severity": "warning"},
    )

    assert_grouped_parity_meaning(
        fastapi_timeline_payload,
        fastapi_summary_payload,
        mcp_timeline_payload,
        mcp_summary_payload,
        expected_count=1,
        expected_summary_meaning={
            "total_incidents": 1,
            "total_alerts": 2,
            "counts_by_detector": {"video_metrics": 2},
            "counts_by_severity": {"warning": 2},
            "top_incident_categories": {"Black screen detected": 1},
        },
    )


def test_fastapi_and_mcp_alert_views_keep_equivalent_meaning_for_known_empty_session(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """FastAPI and MCP should keep the same no-data meaning for one session.

    This covers the operator-visible state where the session exists but no
    alerts have been persisted yet.
    """

    session_id = "session-parity-empty"
    write_parity_session(monkeypatch, tmp_path, session_id)
    enable_fastapi_alert_route_for_cross_surface_reads(monkeypatch)
    (
        fastapi_alert_payload,
        fastapi_summary_payload,
        mcp_alert_payload,
        mcp_summary_payload,
    ) = fetch_raw_parity_payloads(session_id)
    (
        fastapi_timeline_payload,
        fastapi_incident_summary_payload,
        mcp_timeline_payload,
        mcp_incident_summary_payload,
    ) = fetch_grouped_parity_payloads(session_id)

    assert_raw_parity_meaning(
        fastapi_alert_payload,
        fastapi_summary_payload,
        mcp_alert_payload,
        mcp_summary_payload,
        expected_count=0,
        expected_summary_meaning=empty_raw_summary_meaning(),
    )
    assert_grouped_parity_meaning(
        fastapi_timeline_payload,
        fastapi_incident_summary_payload,
        mcp_timeline_payload,
        mcp_incident_summary_payload,
        expected_count=0,
        expected_summary_meaning=empty_incident_summary_meaning(),
    )


def test_fastapi_and_mcp_alert_views_keep_equivalent_meaning_for_unknown_filter_values(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """FastAPI and MCP should agree on the no-match meaning for unknown filters.

    This keeps "known session, unmatched filters" distinct from "known empty
    session" while still locking down equivalent meaning.
    """

    session_id = "session-parity-unknown-filter"
    write_parity_session(
        monkeypatch,
        tmp_path,
        session_id,
        alert_rows=(
            build_persisted_alert(
                session_id,
                timestamp_utc="2026-05-06 10:00:00",
                detector_id="video_metrics",
                title="Black screen detected",
                message="Known row that should not match the filter.",
                severity="warning",
                source_name="segment_0001.ts",
            ),
        ),
    )
    enable_fastapi_alert_route_for_cross_surface_reads(monkeypatch)
    (
        fastapi_alert_payload,
        fastapi_summary_payload,
        mcp_alert_payload,
        mcp_summary_payload,
    ) = fetch_raw_parity_payloads(
        session_id,
        query_string="?detector_id=unknown_detector",
        mcp_arguments={"detector_id": "unknown_detector"},
    )
    (
        fastapi_timeline_payload,
        fastapi_incident_summary_payload,
        mcp_timeline_payload,
        mcp_incident_summary_payload,
    ) = fetch_grouped_parity_payloads(
        session_id,
        query_string="?detector_id=unknown_detector",
        mcp_arguments={"detector_id": "unknown_detector"},
    )

    assert_raw_parity_meaning(
        fastapi_alert_payload,
        fastapi_summary_payload,
        mcp_alert_payload,
        mcp_summary_payload,
        expected_count=0,
        expected_summary_meaning=empty_raw_summary_meaning(),
    )
    assert_grouped_parity_meaning(
        fastapi_timeline_payload,
        fastapi_incident_summary_payload,
        mcp_timeline_payload,
        mcp_incident_summary_payload,
        expected_count=0,
        expected_summary_meaning=empty_incident_summary_meaning(),
    )


def test_fastapi_and_mcp_alert_views_keep_equivalent_meaning_for_time_bounded_query(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """FastAPI and MCP should stay aligned for one shared time-bounded query.

    The test intentionally compares both raw and grouped meaning for the same
    window because time filtering is one of the easiest cross-surface drift
    seams.
    """

    session_id = "session-parity-time-bounded"
    write_parity_session(
        monkeypatch,
        tmp_path,
        session_id,
        alert_rows=(
            build_persisted_alert(
                session_id,
                timestamp_utc="2026-05-06 09:59:50",
                detector_id="video_metrics",
                title="Black screen detected",
                message="Outside the requested time window.",
                severity="warning",
                source_name="segment_0001.ts",
            ),
            build_persisted_alert(
                session_id,
                timestamp_utc="2026-05-06 10:00:05",
                detector_id="video_metrics",
                title="Black screen detected",
                message="Inside the requested time window.",
                severity="warning",
                source_name="segment_0002.ts",
            ),
            build_persisted_alert(
                session_id,
                timestamp_utc="2026-05-06 10:02:00",
                detector_id="video_blur",
                title="Blur increased",
                message="Later incident inside the requested time window.",
                severity="info",
                source_name="segment_0003.ts",
            ),
        ),
    )
    enable_fastapi_alert_route_for_cross_surface_reads(monkeypatch)
    time_filter_query = (
        "?start_time_utc=2026-05-06%2010:00:00"
        "&end_time_utc=2026-05-06%2010:05:00"
    )
    time_filter_args = {
        "start_time_utc": "2026-05-06 10:00:00",
        "end_time_utc": "2026-05-06 10:05:00",
    }
    (
        fastapi_alert_payload,
        fastapi_summary_payload,
        mcp_alert_payload,
        mcp_summary_payload,
    ) = fetch_raw_parity_payloads(
        session_id,
        query_string=time_filter_query,
        mcp_arguments=time_filter_args,
    )
    (
        fastapi_timeline_payload,
        fastapi_incident_summary_payload,
        mcp_timeline_payload,
        mcp_incident_summary_payload,
    ) = fetch_grouped_parity_payloads(
        session_id,
        query_string=time_filter_query,
        mcp_arguments=time_filter_args,
    )

    assert_raw_parity_meaning(
        fastapi_alert_payload,
        fastapi_summary_payload,
        mcp_alert_payload,
        mcp_summary_payload,
        expected_count=2,
        expected_summary_meaning={
            "total_alerts": 2,
            "counts_by_detector": {"video_metrics": 1, "video_blur": 1},
            "counts_by_severity": {"warning": 1, "info": 1},
            "first_alert_timestamp_utc": "2026-05-06 10:00:05",
            "last_alert_timestamp_utc": "2026-05-06 10:02:00",
        },
    )
    assert_grouped_parity_meaning(
        fastapi_timeline_payload,
        fastapi_incident_summary_payload,
        mcp_timeline_payload,
        mcp_incident_summary_payload,
        expected_count=2,
        expected_summary_meaning={
            "total_incidents": 2,
            "total_alerts": 2,
            "counts_by_detector": {"video_metrics": 1, "video_blur": 1},
            "counts_by_severity": {"warning": 1, "info": 1},
            "top_incident_categories": {
                "Black screen detected": 1,
                "Blur increased": 1,
            },
        },
    )
