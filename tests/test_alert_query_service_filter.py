"""Focused service tests for raw alert filtering behavior.

This suite owns the raw filtered-alert contract:

- composing detector, severity, and time filters
- preserving persisted ordering
- treating unknown filters as safe empty results
- validating malformed or inverted time filters
- keeping known-session semantics intact on the filtered entrypoint

It intentionally stops at raw filtered rows. Numeric aggregation belongs in the
summary suite so filter-edge failures stay easy to isolate.
"""

from pathlib import Path

import pytest

from session_alerts import filter_session_alert_events
from tests.alert_query_service_test_support import (
    assert_query_requires_known_session,
    write_known_session_without_alerts,
)
from tests.session_alert_test_support import (
    build_normalized_alert,
    build_persisted_alert,
    configure_session_alert_test,
    write_known_session,
)


def _alert_titles(alerts: list[dict[str, object]]) -> list[object]:
    """Return titles in service output order for compact ordering assertions."""
    return [alert["title"] for alert in alerts]


def test_filter_session_alert_events_applies_detector_severity_and_time_filters(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Filtering should combine detector, severity, and inclusive time bounds."""
    session_root = configure_session_alert_test(monkeypatch, tmp_path)
    write_known_session(
        session_root,
        "session-filter",
        alert_rows=[
            build_persisted_alert(
                "session-filter",
                timestamp_utc="2026-05-06 10:00:00",
                detector_id="video_metrics",
                title="Black screen detected",
                message="Black segment.",
                severity="warning",
                source_name="segment_0001.ts",
            ),
            build_persisted_alert(
                "session-filter",
                timestamp_utc="2026-05-06 10:00:10",
                detector_id="video_blur",
                title="Blur increased",
                message="Blur threshold exceeded.",
                severity="info",
                source_name="segment_0002.ts",
            ),
            build_persisted_alert(
                "session-filter",
                timestamp_utc="2026-05-06 10:00:20",
                detector_id="video_metrics",
                title="Black screen detected",
                message="Black segment again.",
                severity="warning",
                source_name="segment_0003.ts",
            ),
        ],
    )

    filtered = filter_session_alert_events(
        "session-filter",
        detector_id="video_metrics",
        severity="warning",
        start_time_utc="2026-05-06 10:00:05",
        end_time_utc="2026-05-06 10:00:25",
    )

    assert filtered == [
        build_normalized_alert(
            "session-filter",
            timestamp_utc="2026-05-06 10:00:20",
            detector_id="video_metrics",
            title="Black screen detected",
            message="Black segment again.",
            severity="warning",
            source_name="segment_0003.ts",
        )
    ]


def test_filter_session_alert_events_ignores_rows_with_unparseable_persisted_timestamps(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Time-filtered queries should skip rows whose persisted timestamps are invalid."""
    session_root = configure_session_alert_test(monkeypatch, tmp_path)
    write_known_session(
        session_root,
        "session-bad-time-filter",
        alert_rows=[
            build_persisted_alert(
                "session-bad-time-filter",
                timestamp_utc="not-a-time",
                detector_id="video_metrics",
                title="Bad timestamp",
                message="Should be ignored for time filtering.",
                severity="warning",
                source_name="segment_0001.ts",
            ),
            build_persisted_alert(
                "session-bad-time-filter",
                timestamp_utc="2026-05-06 10:00:10",
                detector_id="video_metrics",
                title="Good timestamp",
                message="Should survive filtering.",
                severity="warning",
                source_name="segment_0002.ts",
            ),
        ],
    )

    filtered = filter_session_alert_events(
        "session-bad-time-filter",
        start_time_utc="2026-05-06 10:00:00",
        end_time_utc="2026-05-06 10:00:20",
    )

    assert filtered == [
        build_normalized_alert(
            "session-bad-time-filter",
            timestamp_utc="2026-05-06 10:00:10",
            detector_id="video_metrics",
            title="Good timestamp",
            message="Should survive filtering.",
            severity="warning",
            source_name="segment_0002.ts",
        )
    ]


def test_filter_session_alert_events_rejects_inverted_time_range(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Validation stays in the service layer for obviously invalid time ranges."""
    session_root = configure_session_alert_test(monkeypatch, tmp_path)
    write_known_session(session_root, "session-invalid-range")

    with pytest.raises(ValueError, match="start_time_utc"):
        filter_session_alert_events(
            "session-invalid-range",
            start_time_utc="2026-05-06 10:00:10",
            end_time_utc="2026-05-06 10:00:00",
        )


@pytest.mark.parametrize(
    ("session_id", "query_kwargs", "expected_field"),
    [
        (
            "session-invalid-start-time",
            {"start_time_utc": "2026/05/06 10:00:00"},
            "start_time_utc",
        ),
        (
            "session-invalid-end-time",
            {"end_time_utc": "2026/05/06 10:00:00"},
            "end_time_utc",
        ),
    ],
)
def test_filter_session_alert_events_rejects_invalid_time_filter_formats(
    monkeypatch,
    tmp_path: Path,
    session_id: str,
    query_kwargs: dict[str, str],
    expected_field: str,
) -> None:
    """Invalid raw-filter timestamps should fail with field-specific validation errors."""
    write_known_session_without_alerts(
        monkeypatch,
        tmp_path,
        session_id,
    )

    with pytest.raises(ValueError, match=expected_field):
        filter_session_alert_events(session_id, **query_kwargs)


def test_filter_session_alert_events_requires_known_session(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """The filtered-alert entrypoint should preserve the shared unknown-session contract."""
    configure_session_alert_test(monkeypatch, tmp_path)

    assert_query_requires_known_session(
        filter_session_alert_events,
        "missing-filter-session",
    )


def test_filter_session_alert_events_combines_detector_and_time_filters_without_severity(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Detector and time filters should compose cleanly without requiring severity."""
    session_root = configure_session_alert_test(monkeypatch, tmp_path)
    write_known_session(
        session_root,
        "session-mixed-filters",
        alert_rows=[
            build_persisted_alert(
                "session-mixed-filters",
                timestamp_utc="2026-05-06 10:00:00",
                detector_id="video_metrics",
                title="Early metric event",
                message="Outside the requested time window.",
                severity="warning",
                source_name="segment_0001.ts",
            ),
            build_persisted_alert(
                "session-mixed-filters",
                timestamp_utc="2026-05-06 10:00:10",
                detector_id="video_blur",
                title="Blur event",
                message="Wrong detector.",
                severity="warning",
                source_name="segment_0002.ts",
            ),
            build_persisted_alert(
                "session-mixed-filters",
                timestamp_utc="2026-05-06 10:00:20",
                detector_id="video_metrics",
                title="Late metric event",
                message="Should survive the mixed filter query.",
                severity="info",
                source_name="segment_0003.ts",
            ),
        ],
    )

    filtered = filter_session_alert_events(
        "session-mixed-filters",
        detector_id="video_metrics",
        start_time_utc="2026-05-06 10:00:15",
        end_time_utc="2026-05-06 10:00:25",
    )

    assert filtered == [
        build_normalized_alert(
            "session-mixed-filters",
            timestamp_utc="2026-05-06 10:00:20",
            detector_id="video_metrics",
            title="Late metric event",
            message="Should survive the mixed filter query.",
            severity="info",
            source_name="segment_0003.ts",
        )
    ]


@pytest.mark.parametrize(
    ("detector_id", "severity"),
    [
        ("unknown_detector", None),
        (None, "critical"),
        ("unknown_detector", "critical"),
    ],
)
def test_filter_session_alert_events_returns_empty_list_for_unknown_filter_values(
    monkeypatch,
    tmp_path: Path,
    detector_id: str | None,
    severity: str | None,
) -> None:
    """Unknown filter values should fail safely by returning an empty filtered result."""
    session_root = configure_session_alert_test(monkeypatch, tmp_path)
    write_known_session(
        session_root,
        "session-unknown-filters",
        alert_rows=[
            build_persisted_alert(
                "session-unknown-filters",
                timestamp_utc="2026-05-06 10:00:00",
                detector_id="video_metrics",
                title="Known detector alert",
                message="Persisted baseline row.",
                severity="warning",
                source_name="segment_0001.ts",
            )
        ],
    )

    filtered = filter_session_alert_events(
        "session-unknown-filters",
        detector_id=detector_id,
        severity=severity,
    )

    assert filtered == []


def test_filter_session_alert_events_preserves_persisted_alert_order(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Raw alert queries should preserve persisted row order for stable downstream consumers."""
    session_root = configure_session_alert_test(monkeypatch, tmp_path)
    write_known_session(
        session_root,
        "session-ordering",
        alert_rows=[
            build_persisted_alert(
                "session-ordering",
                timestamp_utc="2026-05-06 10:00:20",
                detector_id="video_metrics",
                title="First persisted row",
                message="Persisted first even though the timestamp is later.",
                severity="warning",
                source_name="segment_0003.ts",
            ),
            build_persisted_alert(
                "session-ordering",
                timestamp_utc="2026-05-06 10:00:00",
                detector_id="video_metrics",
                title="Second persisted row",
                message="Persisted second even though the timestamp is earlier.",
                severity="warning",
                source_name="segment_0001.ts",
            ),
        ],
    )

    filtered = filter_session_alert_events(
        "session-ordering",
        detector_id="video_metrics",
    )

    assert _alert_titles(filtered) == [
        "First persisted row",
        "Second persisted row",
    ]


def test_filter_session_alert_events_applies_inclusive_time_bounds(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Start and end timestamps should both be inclusive."""
    session_root = configure_session_alert_test(monkeypatch, tmp_path)
    write_known_session(
        session_root,
        "session-inclusive-bounds",
        alert_rows=[
            build_persisted_alert(
                "session-inclusive-bounds",
                timestamp_utc="2026-05-06 10:00:00",
                detector_id="video_metrics",
                title="Start bound",
                message="Should be included.",
                severity="warning",
                source_name="segment_0001.ts",
            ),
            build_persisted_alert(
                "session-inclusive-bounds",
                timestamp_utc="2026-05-06 10:00:10",
                detector_id="video_metrics",
                title="End bound",
                message="Should also be included.",
                severity="warning",
                source_name="segment_0002.ts",
            ),
        ],
    )

    filtered = filter_session_alert_events(
        "session-inclusive-bounds",
        start_time_utc="2026-05-06 10:00:00",
        end_time_utc="2026-05-06 10:00:10",
    )

    assert _alert_titles(filtered) == [
        "Start bound",
        "End bound",
    ]


def test_filter_session_alert_events_applies_start_only_time_filter(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """A start-only time filter should keep alerts at or after the boundary."""
    session_root = configure_session_alert_test(monkeypatch, tmp_path)
    write_known_session(
        session_root,
        "session-start-only",
        alert_rows=[
            build_persisted_alert(
                "session-start-only",
                timestamp_utc="2026-05-06 09:59:59",
                detector_id="video_metrics",
                title="Before start",
                message="Should be excluded.",
                severity="warning",
                source_name="segment_0001.ts",
            ),
            build_persisted_alert(
                "session-start-only",
                timestamp_utc="2026-05-06 10:00:00",
                detector_id="video_metrics",
                title="At start",
                message="Should be included.",
                severity="warning",
                source_name="segment_0002.ts",
            ),
            build_persisted_alert(
                "session-start-only",
                timestamp_utc="2026-05-06 10:00:05",
                detector_id="video_blur",
                title="After start",
                message="Should also be included.",
                severity="info",
                source_name="segment_0003.ts",
            ),
        ],
    )

    filtered = filter_session_alert_events(
        "session-start-only",
        start_time_utc="2026-05-06 10:00:00",
    )

    assert _alert_titles(filtered) == [
        "At start",
        "After start",
    ]


def test_filter_session_alert_events_applies_end_only_time_filter(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """An end-only time filter should keep alerts at or before the boundary."""
    session_root = configure_session_alert_test(monkeypatch, tmp_path)
    write_known_session(
        session_root,
        "session-end-only",
        alert_rows=[
            build_persisted_alert(
                "session-end-only",
                timestamp_utc="2026-05-06 10:00:00",
                detector_id="video_metrics",
                title="Before end",
                message="Should be included.",
                severity="warning",
                source_name="segment_0001.ts",
            ),
            build_persisted_alert(
                "session-end-only",
                timestamp_utc="2026-05-06 10:00:10",
                detector_id="video_blur",
                title="At end",
                message="Should also be included.",
                severity="info",
                source_name="segment_0002.ts",
            ),
            build_persisted_alert(
                "session-end-only",
                timestamp_utc="2026-05-06 10:00:11",
                detector_id="video_metrics",
                title="After end",
                message="Should be excluded.",
                severity="warning",
                source_name="segment_0003.ts",
            ),
        ],
    )

    filtered = filter_session_alert_events(
        "session-end-only",
        end_time_utc="2026-05-06 10:00:10",
    )

    assert _alert_titles(filtered) == [
        "Before end",
        "At end",
    ]


def test_filter_session_alert_events_returns_empty_list_for_known_session_without_alerts(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Known sessions without persisted alerts should filter as an empty result."""
    write_known_session_without_alerts(
        monkeypatch,
        tmp_path,
        "session-empty-filter",
    )

    filtered = filter_session_alert_events(
        "session-empty-filter",
        detector_id="video_metrics",
        severity="warning",
    )

    assert filtered == []
