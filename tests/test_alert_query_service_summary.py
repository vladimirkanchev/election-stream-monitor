"""Focused service tests for raw alert summary behavior.

This suite owns the numeric summary contract shared by FastAPI and MCP:

- deterministic counts by detector and severity
- first/last timestamp bounds
- safe degradation on bad persisted timestamps
- empty-summary behavior for empty or unmatched sessions
- summary-specific validation of filter input
- keeping known-session semantics intact on the summary entrypoint

Raw persisted reads and raw filtered-row behavior live in the sibling suites so
summary regressions can be understood as aggregation failures, not mixed
read/filter concerns.
"""

from pathlib import Path

import pytest

from session_alerts import summarize_session_alert_events
from tests.alert_query_service_test_support import (
    assert_query_requires_known_session,
    write_known_session_without_alerts,
)
from tests.session_alert_test_support import (
    build_alert_summary_payload,
    build_persisted_alert,
    configure_session_alert_test,
    write_known_session,
)


def _assert_empty_summary(summary: dict[str, object], session_id: str) -> None:
    """Assert the stable zero-alert summary contract for one known session."""
    assert summary == build_alert_summary_payload(
        session_id,
        total_alerts=0,
        counts_by_detector={},
        counts_by_severity={},
        first_alert_timestamp_utc=None,
        last_alert_timestamp_utc=None,
    )


def test_summarize_session_alert_events_rejects_invalid_end_time_format(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Summary queries should reject invalid time filters the same way as raw filtered reads."""
    write_known_session_without_alerts(
        monkeypatch,
        tmp_path,
        "session-summary-invalid-end-time",
    )

    with pytest.raises(ValueError, match="end_time_utc"):
        summarize_session_alert_events(
            "session-summary-invalid-end-time",
            end_time_utc="bad-time",
        )


def test_summarize_session_alert_events_requires_known_session(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """The summary entrypoint should preserve the shared unknown-session contract."""
    configure_session_alert_test(monkeypatch, tmp_path)

    assert_query_requires_known_session(
        summarize_session_alert_events,
        "missing-summary-session",
    )


def test_summarize_session_alert_events_returns_counts_and_time_bounds(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """The summary contract should remain deterministic and numeric only."""
    session_root = configure_session_alert_test(monkeypatch, tmp_path)
    write_known_session(
        session_root,
        "session-summary",
        alert_rows=[
            build_persisted_alert(
                "session-summary",
                timestamp_utc="2026-05-06 10:00:00",
                detector_id="video_metrics",
                title="Black screen detected",
                message="Black segment.",
                severity="warning",
                source_name="segment_0001.ts",
            ),
            build_persisted_alert(
                "session-summary",
                timestamp_utc="2026-05-06 10:00:10",
                detector_id="video_blur",
                title="Blur increased",
                message="Blur threshold exceeded.",
                severity="info",
                source_name="segment_0002.ts",
            ),
            build_persisted_alert(
                "session-summary",
                timestamp_utc="2026-05-06 10:00:20",
                detector_id="video_metrics",
                title="Black screen detected",
                message="Black segment again.",
                severity="warning",
                source_name="segment_0003.ts",
            ),
        ],
    )

    summary = summarize_session_alert_events("session-summary")

    assert summary == build_alert_summary_payload(
        "session-summary",
        total_alerts=3,
        counts_by_detector={"video_metrics": 2, "video_blur": 1},
        counts_by_severity={"warning": 2, "info": 1},
        first_alert_timestamp_utc="2026-05-06 10:00:00",
        last_alert_timestamp_utc="2026-05-06 10:00:20",
    )


def test_summarize_session_alert_events_ignores_bad_timestamps_for_time_bounds(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Summary time bounds should ignore bad persisted timestamps but keep total counts."""
    session_root = configure_session_alert_test(monkeypatch, tmp_path)
    write_known_session(
        session_root,
        "session-summary-bad-time",
        alert_rows=[
            build_persisted_alert(
                "session-summary-bad-time",
                timestamp_utc="2026-05-06 10:00:00",
                detector_id="video_metrics",
                title="Good timestamp",
                message="Count this and use for bounds.",
                severity="warning",
                source_name="segment_0001.ts",
            ),
            build_persisted_alert(
                "session-summary-bad-time",
                timestamp_utc="bad-time",
                detector_id="video_blur",
                title="Bad timestamp",
                message="Count this but ignore it for bounds.",
                severity="info",
                source_name="segment_0002.ts",
            ),
        ],
    )

    summary = summarize_session_alert_events("session-summary-bad-time")

    assert summary == build_alert_summary_payload(
        "session-summary-bad-time",
        total_alerts=2,
        counts_by_detector={"video_metrics": 1, "video_blur": 1},
        counts_by_severity={"warning": 1, "info": 1},
        first_alert_timestamp_utc="2026-05-06 10:00:00",
        last_alert_timestamp_utc="2026-05-06 10:00:00",
    )


def test_summarize_session_alert_events_returns_empty_summary_when_filters_match_nothing(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Empty filtered summaries should keep the stable zero-alert contract."""
    session_root = configure_session_alert_test(monkeypatch, tmp_path)
    write_known_session(
        session_root,
        "session-summary-empty",
        alert_rows=[
            build_persisted_alert(
                "session-summary-empty",
                timestamp_utc="2026-05-06 10:00:00",
                detector_id="video_metrics",
                title="Black screen detected",
                message="Black segment.",
                severity="warning",
                source_name="segment_0001.ts",
            )
        ],
    )

    summary = summarize_session_alert_events(
        "session-summary-empty",
        severity="info",
    )

    _assert_empty_summary(summary, "session-summary-empty")


def test_summarize_session_alert_events_counts_same_severity_without_extra_keys(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Same-severity alert sets should keep a minimal stable severity breakdown."""
    session_root = configure_session_alert_test(monkeypatch, tmp_path)
    write_known_session(
        session_root,
        "session-same-severity",
        alert_rows=[
            build_persisted_alert(
                "session-same-severity",
                timestamp_utc="2026-05-06 10:00:00",
                detector_id="video_metrics",
                title="Metric alert",
                message="First warning.",
                severity="warning",
                source_name="segment_0001.ts",
            ),
            build_persisted_alert(
                "session-same-severity",
                timestamp_utc="2026-05-06 10:00:10",
                detector_id="video_blur",
                title="Blur alert",
                message="Second warning.",
                severity="warning",
                source_name="segment_0002.ts",
            ),
        ],
    )

    summary = summarize_session_alert_events("session-same-severity")

    assert summary == build_alert_summary_payload(
        "session-same-severity",
        total_alerts=2,
        counts_by_detector={"video_metrics": 1, "video_blur": 1},
        counts_by_severity={"warning": 2},
        first_alert_timestamp_utc="2026-05-06 10:00:00",
        last_alert_timestamp_utc="2026-05-06 10:00:10",
    )


def test_summarize_session_alert_events_returns_empty_summary_for_known_session_without_alerts(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Known sessions with no persisted alerts should still return the stable empty summary."""
    write_known_session_without_alerts(
        monkeypatch,
        tmp_path,
        "session-no-alerts-summary",
    )

    summary = summarize_session_alert_events("session-no-alerts-summary")

    _assert_empty_summary(summary, "session-no-alerts-summary")


def test_summarize_session_alert_events_counts_multiple_detectors_with_filtered_subset(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Filtered summaries should keep detector counts correct when multiple detectors contribute."""
    session_root = configure_session_alert_test(monkeypatch, tmp_path)
    write_known_session(
        session_root,
        "session-multi-detector-summary",
        alert_rows=[
            build_persisted_alert(
                "session-multi-detector-summary",
                timestamp_utc="2026-05-06 10:00:00",
                detector_id="video_metrics",
                title="Metric warning",
                message="Warning from metrics.",
                severity="warning",
                source_name="segment_0001.ts",
            ),
            build_persisted_alert(
                "session-multi-detector-summary",
                timestamp_utc="2026-05-06 10:00:05",
                detector_id="video_blur",
                title="Blur warning",
                message="Warning from blur.",
                severity="warning",
                source_name="segment_0002.ts",
            ),
            build_persisted_alert(
                "session-multi-detector-summary",
                timestamp_utc="2026-05-06 10:00:10",
                detector_id="video_blur",
                title="Blur info",
                message="Info from blur.",
                severity="info",
                source_name="segment_0003.ts",
            ),
        ],
    )

    summary = summarize_session_alert_events(
        "session-multi-detector-summary",
        severity="warning",
    )

    assert summary == build_alert_summary_payload(
        "session-multi-detector-summary",
        total_alerts=2,
        counts_by_detector={"video_metrics": 1, "video_blur": 1},
        counts_by_severity={"warning": 2},
        first_alert_timestamp_utc="2026-05-06 10:00:00",
        last_alert_timestamp_utc="2026-05-06 10:00:05",
    )


def test_summarize_session_alert_events_returns_empty_summary_for_unknown_filter_values(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Unknown summary filters should degrade to the stable empty summary."""
    session_root = configure_session_alert_test(monkeypatch, tmp_path)
    write_known_session(
        session_root,
        "session-summary-unknown-filters",
        alert_rows=[
            build_persisted_alert(
                "session-summary-unknown-filters",
                timestamp_utc="2026-05-06 10:00:00",
                detector_id="video_metrics",
                title="Known alert",
                message="Baseline persisted row.",
                severity="warning",
                source_name="segment_0001.ts",
            )
        ],
    )

    summary = summarize_session_alert_events(
        "session-summary-unknown-filters",
        detector_id="unknown_detector",
    )

    _assert_empty_summary(summary, "session-summary-unknown-filters")
