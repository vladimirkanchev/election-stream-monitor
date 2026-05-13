"""Edge and validation-focused FastAPI/MCP parity tests.

This file owns the higher-risk cross-surface parity seams:

- invalid time-filter validation parity
- inverted time-range validation parity
- inclusive and open-ended time-bound parity
- deterministic same-timestamp grouped ordering parity

Normal filtered, empty, and time-bounded meaning checks live in
``tests/test_mcp_fastapi_parity_behavior.py``. Trust-boundary independence
stays in ``tests/test_mcp_fastapi_boundary_split.py``. Shared parity setup and
meaning helpers stay in ``tests/mcp_fastapi_parity_test_support.py``.
"""

from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest

from tests.mcp_fastapi_parity_test_support import (
    assert_cross_surface_validation_failure,
    assert_grouped_parity_meaning,
    assert_raw_parity_meaning,
    assert_timeline_order_parity,
    build_time_filter_parity_inputs,
    clear_boundary_test_state,  # noqa: F401
    enable_fastapi_alert_route_for_cross_surface_reads,
    fetch_full_parity_payloads,
    fetch_grouped_parity_payloads,
    single_category_incident_summary_meaning,
    write_parity_session,
)
from tests.session_alert_test_support import build_persisted_alert

pytestmark = pytest.mark.usefixtures("clear_boundary_test_state")


def test_fastapi_and_mcp_raw_alert_views_keep_equivalent_validation_meaning_for_invalid_timestamp_format(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """FastAPI and MCP raw reads should expose the same invalid-time meaning.

    This locks the client-visible validation contract across both surfaces, not
    just the underlying shared service validation.
    """

    session_id = "session-parity-invalid-raw-time"
    write_parity_session(monkeypatch, tmp_path, session_id)
    enable_fastapi_alert_route_for_cross_surface_reads(monkeypatch)

    assert_cross_surface_validation_failure(
        fastapi_path=f"/sessions/{session_id}/alerts/summary?start_time_utc=not-a-time",
        mcp_tool_name="summarize_session_alerts",
        mcp_arguments={
            "session_id": session_id,
            "start_time_utc": "not-a-time",
        },
        expected_detail=(
            "start_time_utc must use UTC timestamp format '%Y-%m-%d %H:%M:%S'"
        ),
    )


def test_fastapi_and_mcp_grouped_incident_views_keep_equivalent_validation_meaning_for_inverted_time_range(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """FastAPI and MCP grouped reads should expose the same inverted-range meaning.

    Grouped reads reuse the same service validation seam, but the wrapper
    mapping is still worth keeping explicit here.
    """

    session_id = "session-parity-inverted-grouped-range"
    write_parity_session(monkeypatch, tmp_path, session_id)
    enable_fastapi_alert_route_for_cross_surface_reads(monkeypatch)

    assert_cross_surface_validation_failure(
        fastapi_path=(
            f"/sessions/{session_id}/alerts/incident-summary"
            "?start_time_utc=2026-05-06%2010:10:00"
            "&end_time_utc=2026-05-06%2010:00:00"
        ),
        mcp_tool_name="summarize_session_alert_incidents",
        mcp_arguments={
            "session_id": session_id,
            "start_time_utc": "2026-05-06 10:10:00",
            "end_time_utc": "2026-05-06 10:00:00",
        },
        expected_detail="start_time_utc must be earlier than or equal to end_time_utc",
    )


def test_fastapi_and_mcp_alert_views_keep_equivalent_meaning_for_inclusive_time_bounds(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """FastAPI and MCP should both keep start and end bounds inclusive.

    This protects one of the most visible off-by-one parity seams across both
    raw and grouped reads.
    """

    session_id = "session-parity-inclusive-bounds"
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
                message="At the start bound.",
                severity="warning",
                source_name="segment_0001.ts",
            ),
            build_persisted_alert(
                session_id,
                timestamp_utc="2026-05-06 10:00:10",
                detector_id="video_metrics",
                title="Black screen detected",
                message="At the end bound.",
                severity="warning",
                source_name="segment_0002.ts",
            ),
        ),
    )
    enable_fastapi_alert_route_for_cross_surface_reads(monkeypatch)
    query_string, mcp_arguments = build_time_filter_parity_inputs(
        start_time_utc="2026-05-06 10:00:00",
        end_time_utc="2026-05-06 10:00:10",
    )
    (
        fastapi_alert_payload,
        fastapi_summary_payload,
        mcp_alert_payload,
        mcp_summary_payload,
        fastapi_timeline_payload,
        fastapi_incident_summary_payload,
        mcp_timeline_payload,
        mcp_incident_summary_payload,
    ) = fetch_full_parity_payloads(
        session_id,
        query_string=query_string,
        mcp_arguments=mcp_arguments,
    )

    assert_raw_parity_meaning(
        fastapi_alert_payload,
        fastapi_summary_payload,
        mcp_alert_payload,
        mcp_summary_payload,
        expected_count=2,
        expected_summary_meaning={
            "total_alerts": 2,
            "counts_by_detector": {"video_metrics": 2},
            "counts_by_severity": {"warning": 2},
            "first_alert_timestamp_utc": "2026-05-06 10:00:00",
            "last_alert_timestamp_utc": "2026-05-06 10:00:10",
        },
    )
    assert_grouped_parity_meaning(
        fastapi_timeline_payload,
        fastapi_incident_summary_payload,
        mcp_timeline_payload,
        mcp_incident_summary_payload,
        expected_count=1,
        expected_summary_meaning=single_category_incident_summary_meaning(
            total_incidents=1,
            total_alerts=2,
            detector_id="video_metrics",
            severity="warning",
            title="Black screen detected",
        ),
    )


@pytest.mark.parametrize(
    (
        "start_time_utc",
        "end_time_utc",
        "expected_raw_summary",
        "expected_incident_summary",
        "expected_incident_count",
    ),
    [
        (
            "2026-05-06 10:00:10",
            None,
            {
                "total_alerts": 2,
                "counts_by_detector": {"video_metrics": 1, "video_blur": 1},
                "counts_by_severity": {"warning": 1, "info": 1},
                "first_alert_timestamp_utc": "2026-05-06 10:00:10",
                "last_alert_timestamp_utc": "2026-05-06 10:02:00",
            },
            {
                "total_incidents": 2,
                "total_alerts": 2,
                "counts_by_detector": {"video_metrics": 1, "video_blur": 1},
                "counts_by_severity": {"warning": 1, "info": 1},
                "top_incident_categories": {
                    "Black screen detected": 1,
                    "Blur increased": 1,
                },
            },
            2,
        ),
        (
            None,
            "2026-05-06 10:00:10",
            {
                "total_alerts": 2,
                "counts_by_detector": {"video_metrics": 2},
                "counts_by_severity": {"warning": 2},
                "first_alert_timestamp_utc": "2026-05-06 10:00:00",
                "last_alert_timestamp_utc": "2026-05-06 10:00:10",
            },
            {
                "total_incidents": 1,
                "total_alerts": 2,
                "counts_by_detector": {"video_metrics": 2},
                "counts_by_severity": {"warning": 2},
                "top_incident_categories": {"Black screen detected": 1},
            },
            1,
        ),
    ],
)
def test_fastapi_and_mcp_alert_views_keep_equivalent_meaning_for_open_ended_time_filters(
    monkeypatch,
    tmp_path: Path,
    start_time_utc: str | None,
    end_time_utc: str | None,
    expected_raw_summary: dict[str, object],
    expected_incident_summary: dict[str, object],
    expected_incident_count: int,
) -> None:
    """FastAPI and MCP should stay aligned for start-only and end-only filters.

    Open-ended time windows are common operator queries and are easy to
    implement asymmetrically if parity is not locked down directly.
    """

    session_id = "session-parity-open-ended-bounds"
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
                message="Earlier warning alert.",
                severity="warning",
                source_name="segment_0001.ts",
            ),
            build_persisted_alert(
                session_id,
                timestamp_utc="2026-05-06 10:00:10",
                detector_id="video_metrics",
                title="Black screen detected",
                message="Boundary warning alert.",
                severity="warning",
                source_name="segment_0002.ts",
            ),
            build_persisted_alert(
                session_id,
                timestamp_utc="2026-05-06 10:02:00",
                detector_id="video_blur",
                title="Blur increased",
                message="Later info alert.",
                severity="info",
                source_name="segment_0003.ts",
            ),
        ),
    )
    enable_fastapi_alert_route_for_cross_surface_reads(monkeypatch)
    query_string, mcp_arguments = build_time_filter_parity_inputs(
        start_time_utc=start_time_utc,
        end_time_utc=end_time_utc,
    )
    (
        fastapi_alert_payload,
        fastapi_summary_payload,
        mcp_alert_payload,
        mcp_summary_payload,
        fastapi_timeline_payload,
        fastapi_incident_summary_payload,
        mcp_timeline_payload,
        mcp_incident_summary_payload,
    ) = fetch_full_parity_payloads(
        session_id,
        query_string=query_string,
        mcp_arguments=mcp_arguments,
    )

    assert_raw_parity_meaning(
        fastapi_alert_payload,
        fastapi_summary_payload,
        mcp_alert_payload,
        mcp_summary_payload,
        expected_count=cast(int, expected_raw_summary["total_alerts"]),
        expected_summary_meaning=expected_raw_summary,
    )
    assert_grouped_parity_meaning(
        fastapi_timeline_payload,
        fastapi_incident_summary_payload,
        mcp_timeline_payload,
        mcp_incident_summary_payload,
        expected_count=expected_incident_count,
        expected_summary_meaning=expected_incident_summary,
    )


def test_fastapi_and_mcp_grouped_incident_views_keep_equivalent_same_timestamp_ordering(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """FastAPI and MCP grouped reads should keep the same same-timestamp order.

    Equivalent meaning at the grouped layer includes deterministic operator-
    visible ordering, not just matching totals.
    """

    session_id = "session-parity-same-time-order"
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
                message="Persisted first.",
                severity="info",
                source_name="segment_0002.ts",
            ),
            build_persisted_alert(
                session_id,
                timestamp_utc="2026-05-06 10:00:00",
                detector_id="video_metrics",
                title="Black screen detected",
                message="Persisted second.",
                severity="warning",
                source_name="segment_0001.ts",
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
            "total_alerts": 2,
            "counts_by_detector": {"video_blur": 1, "video_metrics": 1},
            "counts_by_severity": {"info": 1, "warning": 1},
            "top_incident_categories": {
                "Blur increased": 1,
                "Black screen detected": 1,
            },
        },
    )
    assert_timeline_order_parity(
        fastapi_timeline_payload,
        mcp_timeline_payload,
        expected_order=[
            ("Blur increased", "video_blur"),
            ("Black screen detected", "video_metrics"),
        ],
    )
