"""Focused grouped-timeline tests layered on top of the raw alert seam.

This file keeps grouped filter reuse, validation, and empty-result behavior
separate from grouped summary aggregation.
"""

from pathlib import Path

import pytest

from session_alert_incidents import build_session_timeline
from session_alerts import SessionAlertsNotFoundError
from tests.alert_incident_service_test_support import (
    assert_empty_timeline,
    assert_single_timeline_entry,
    build_timeline_with_time_filters,
    single_time_filter_kwargs,
    timeline_titles,
    write_single_grouped_alert_session,
)
from tests.session_alert_test_support import (
    StaticAlertStore,
    build_normalized_alert,
    build_timeline_entry,
    build_persisted_alert,
    configure_session_alert_test,
    write_known_session,
)


def test_build_session_timeline_respects_shared_filters(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Timeline queries should apply raw alert filters before any incident grouping."""
    session_root = configure_session_alert_test(monkeypatch, tmp_path)
    write_known_session(
        session_root,
        "session-timeline-filtered",
        alert_rows=[
            build_persisted_alert(
                "session-timeline-filtered",
                timestamp_utc="2026-05-06 10:00:00",
                detector_id="video_metrics",
                title="Black screen detected",
                message="Should be excluded by time range.",
                severity="warning",
                source_name="segment_0001.ts",
            ),
            build_persisted_alert(
                "session-timeline-filtered",
                timestamp_utc="2026-05-06 10:00:30",
                detector_id="video_metrics",
                title="Black screen detected",
                message="Should survive.",
                severity="warning",
                source_name="segment_0002.ts",
            ),
            build_persisted_alert(
                "session-timeline-filtered",
                timestamp_utc="2026-05-06 10:00:40",
                detector_id="video_blur",
                title="Blur increased",
                message="Wrong detector.",
                severity="info",
                source_name="segment_0003.ts",
            ),
        ],
    )

    timeline = build_session_timeline(
        "session-timeline-filtered",
        detector_id="video_metrics",
        severity="warning",
        start_time_utc="2026-05-06 10:00:15",
        end_time_utc="2026-05-06 10:00:35",
    )

    assert timeline == {
        "session_id": "session-timeline-filtered",
        "entries": [
            build_timeline_entry(
                start_time_utc="2026-05-06 10:00:30",
                end_time_utc="2026-05-06 10:00:30",
                detector_id="video_metrics",
                severity="warning",
                title="Black screen detected",
                alert_count=1,
                source_names=["segment_0002.ts"],
                sample_message="Should survive.",
            )
        ],
    }


@pytest.mark.parametrize(
    ("filter_name", "filter_value"),
    [
        ("start_time_utc", "2026/05/06 10:00:00"),
        ("end_time_utc", "bad-time"),
    ],
)
def test_build_session_timeline_rejects_invalid_time_filter_formats(
    monkeypatch,
    tmp_path: Path,
    filter_name: str,
    filter_value: str,
) -> None:
    """Timeline queries should preserve raw-service invalid-time validation."""
    session_root = configure_session_alert_test(monkeypatch, tmp_path)
    write_known_session(session_root, "session-timeline-invalid-time")

    with pytest.raises(ValueError, match=filter_name):
        build_timeline_with_time_filters(
            "session-timeline-invalid-time",
            **single_time_filter_kwargs(filter_name, filter_value),
        )


def test_build_session_timeline_rejects_inverted_time_range(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Timeline queries should preserve raw-service inverted-range validation."""
    session_root = configure_session_alert_test(monkeypatch, tmp_path)
    write_known_session(session_root, "session-timeline-inverted-range")

    with pytest.raises(
        ValueError,
        match="start_time_utc must be earlier than or equal to end_time_utc",
    ):
        build_timeline_with_time_filters(
            "session-timeline-inverted-range",
            start_time_utc="2026-05-06 10:01:00",
            end_time_utc="2026-05-06 10:00:00",
        )


def test_build_session_timeline_requires_known_session(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Timeline queries should fail clearly for unknown sessions."""
    configure_session_alert_test(monkeypatch, tmp_path)

    with pytest.raises(SessionAlertsNotFoundError):
        build_session_timeline("missing-timeline-session")


@pytest.mark.parametrize(
    ("detector_id", "severity"),
    [
        ("unknown_detector", None),
        (None, "critical"),
        ("unknown_detector", "critical"),
    ],
)
def test_build_session_timeline_returns_empty_entries_for_unknown_filter_values(
    monkeypatch,
    tmp_path: Path,
    detector_id: str | None,
    severity: str | None,
) -> None:
    """Unknown grouped-query filters should degrade to the stable empty timeline."""
    session_root = configure_session_alert_test(monkeypatch, tmp_path)
    write_single_grouped_alert_session(
        session_root,
        "session-timeline-unknown-filters",
    )

    assert_empty_timeline(
        build_session_timeline(
            "session-timeline-unknown-filters",
            detector_id=detector_id,
            severity=severity,
        ),
        "session-timeline-unknown-filters",
    )


def test_build_session_timeline_applies_inclusive_time_bounds(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Grouped timeline queries should keep both time bounds inclusive."""
    session_root = configure_session_alert_test(monkeypatch, tmp_path)
    write_known_session(
        session_root,
        "session-timeline-inclusive-bounds",
        alert_rows=[
            build_persisted_alert(
                "session-timeline-inclusive-bounds",
                timestamp_utc="2026-05-06 10:00:00",
                detector_id="video_metrics",
                title="Black screen detected",
                message="At start bound.",
                severity="warning",
                source_name="segment_0001.ts",
            ),
            build_persisted_alert(
                "session-timeline-inclusive-bounds",
                timestamp_utc="2026-05-06 10:00:10",
                detector_id="video_metrics",
                title="Black screen detected",
                message="At end bound.",
                severity="warning",
                source_name="segment_0002.ts",
            ),
        ],
    )

    assert_single_timeline_entry(
        build_timeline_with_time_filters(
            "session-timeline-inclusive-bounds",
            start_time_utc="2026-05-06 10:00:00",
            end_time_utc="2026-05-06 10:00:10",
        ),
        expected_entry=build_timeline_entry(
            start_time_utc="2026-05-06 10:00:00",
            end_time_utc="2026-05-06 10:00:10",
            detector_id="video_metrics",
            severity="warning",
            title="Black screen detected",
            alert_count=2,
            source_names=["segment_0001.ts", "segment_0002.ts"],
            sample_message="At start bound.",
        ),
    )


def test_build_session_timeline_accepts_an_explicit_store_seam() -> None:
    """Grouped timelines should also be able to reuse the injected raw alert store."""
    store = StaticAlertStore(
        "store-timeline",
        [
            build_normalized_alert(
                "store-timeline",
                timestamp_utc="2026-05-06 10:00:00",
                detector_id="video_metrics",
                title="Black screen detected",
                message="First grouped alert.",
                severity="warning",
                source_name="segment_0001.ts",
            ),
            build_normalized_alert(
                "store-timeline",
                timestamp_utc="2026-05-06 10:00:20",
                detector_id="video_metrics",
                title="Black screen detected",
                message="Second grouped alert.",
                severity="warning",
                source_name="segment_0002.ts",
            ),
        ],
    )

    assert build_session_timeline("store-timeline", store=store) == {
        "session_id": "store-timeline",
        "entries": [
            build_timeline_entry(
                start_time_utc="2026-05-06 10:00:00",
                end_time_utc="2026-05-06 10:00:20",
                detector_id="video_metrics",
                severity="warning",
                title="Black screen detected",
                alert_count=2,
                source_names=["segment_0001.ts", "segment_0002.ts"],
                sample_message="First grouped alert.",
            )
        ],
    }


@pytest.mark.parametrize(
    ("filters", "expected_titles"),
    [
        (
            {"start_time_utc": "2026-05-06 10:00:10"},
            ["Black screen detected", "Blur increased"],
        ),
        (
            {"end_time_utc": "2026-05-06 10:00:10"},
            ["Black screen detected"],
        ),
    ],
)
def test_build_session_timeline_supports_open_ended_time_filters(
    monkeypatch,
    tmp_path: Path,
    filters: dict[str, str],
    expected_titles: list[str],
) -> None:
    """Grouped timeline queries should support start-only and end-only time bounds."""
    session_root = configure_session_alert_test(monkeypatch, tmp_path)
    write_known_session(
        session_root,
        "session-timeline-open-ended",
        alert_rows=[
            build_persisted_alert(
                "session-timeline-open-ended",
                timestamp_utc="2026-05-06 10:00:00",
                detector_id="video_metrics",
                title="Black screen detected",
                message="Before later incidents.",
                severity="warning",
                source_name="segment_0001.ts",
            ),
            build_persisted_alert(
                "session-timeline-open-ended",
                timestamp_utc="2026-05-06 10:00:10",
                detector_id="video_metrics",
                title="Black screen detected",
                message="Still same grouped incident.",
                severity="warning",
                source_name="segment_0002.ts",
            ),
            build_persisted_alert(
                "session-timeline-open-ended",
                timestamp_utc="2026-05-06 10:02:00",
                detector_id="video_blur",
                title="Blur increased",
                message="Later separate incident.",
                severity="info",
                source_name="segment_0003.ts",
            ),
        ],
    )

    timeline = build_timeline_with_time_filters(
        "session-timeline-open-ended",
        start_time_utc=filters.get("start_time_utc"),
        end_time_utc=filters.get("end_time_utc"),
    )

    assert timeline_titles(timeline) == expected_titles


def test_build_session_timeline_time_filters_exclude_invalid_timestamp_rows_safely(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Time-bounded timeline queries should skip invalid timestamps without failing."""
    session_root = configure_session_alert_test(monkeypatch, tmp_path)
    write_known_session(
        session_root,
        "session-timeline-filter-invalid-row",
        alert_rows=[
            build_persisted_alert(
                "session-timeline-filter-invalid-row",
                timestamp_utc="bad-time",
                detector_id="video_metrics",
                title="Black screen detected",
                message="Should be excluded by time filtering.",
                severity="warning",
                source_name="segment_0001.ts",
            ),
            build_persisted_alert(
                "session-timeline-filter-invalid-row",
                timestamp_utc="2026-05-06 10:00:10",
                detector_id="video_metrics",
                title="Black screen detected",
                message="Valid row in range.",
                severity="warning",
                source_name="segment_0002.ts",
            ),
        ],
    )

    assert_single_timeline_entry(
        build_timeline_with_time_filters(
            "session-timeline-filter-invalid-row",
            start_time_utc="2026-05-06 10:00:00",
            end_time_utc="2026-05-06 10:00:20",
        ),
        expected_entry=build_timeline_entry(
            start_time_utc="2026-05-06 10:00:10",
            end_time_utc="2026-05-06 10:00:10",
            detector_id="video_metrics",
            severity="warning",
            title="Black screen detected",
            alert_count=1,
            source_names=["segment_0002.ts"],
            sample_message="Valid row in range.",
        ),
    )


def test_build_session_timeline_returns_empty_entries_for_known_empty_session(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Known empty sessions should keep the stable grouped timeline envelope."""
    session_root = configure_session_alert_test(monkeypatch, tmp_path)
    write_known_session(session_root, "session-timeline-empty")

    assert_empty_timeline(
        build_session_timeline("session-timeline-empty"),
        "session-timeline-empty",
    )
