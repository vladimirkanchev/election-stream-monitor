"""Focused service tests for grouped incident summary behavior.

This file owns the summary-oriented incident layer built on top of grouped
timeline entries:

- grouped incident counts
- detector and severity totals
- top incident categories
- narrative output
- empty and bad-timestamp summary edge cases
"""

from pathlib import Path

from session_alert_incidents import build_session_incident_summary
from tests.session_alert_test_support import (
    assert_narrative_contains,
    build_incident_summary_payload,
    build_persisted_alert,
    configure_session_alert_test,
    write_alert_log,
    write_known_session,
)


def test_build_session_incident_summary_reports_grouped_incident_counts_and_narrative(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Incident summary should combine raw alert counts with grouped incident totals."""
    session_root = configure_session_alert_test(monkeypatch, tmp_path)
    write_known_session(
        session_root,
        "session-incident-summary",
        alert_rows=[
            build_persisted_alert(
                "session-incident-summary",
                timestamp_utc="2026-05-06 10:00:00",
                detector_id="video_metrics",
                title="Black screen detected",
                message="Black segment started.",
                severity="warning",
                source_name="segment_0001.ts",
            ),
            build_persisted_alert(
                "session-incident-summary",
                timestamp_utc="2026-05-06 10:00:30",
                detector_id="video_metrics",
                title="Black screen detected",
                message="Black segment continued.",
                severity="warning",
                source_name="segment_0002.ts",
            ),
            build_persisted_alert(
                "session-incident-summary",
                timestamp_utc="2026-05-06 10:02:00",
                detector_id="video_blur",
                title="Blur increased",
                message="Blur threshold exceeded.",
                severity="info",
                source_name="segment_0003.ts",
            ),
        ],
    )

    summary = build_session_incident_summary("session-incident-summary")

    assert summary == build_incident_summary_payload(
        "session-incident-summary",
        total_alerts=3,
        total_incidents=2,
        counts_by_detector={"video_metrics": 2, "video_blur": 1},
        counts_by_severity={"warning": 2, "info": 1},
        top_incident_categories={"Black screen detected": 1, "Blur increased": 1},
        first_alert_timestamp_utc="2026-05-06 10:00:00",
        last_alert_timestamp_utc="2026-05-06 10:02:00",
        narrative_summary=summary["narrative_summary"],
    )
    assert_narrative_contains(
        summary["narrative_summary"],
        "session-incident-summary",
        "2 grouped incidents",
        "3 alerts",
        "video_metrics",
        "blur increased",
        "2 warning alerts",
        "1 info alerts",
    )


def test_build_session_incident_summary_returns_empty_summary_for_known_empty_session(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Known sessions without alerts should keep a stable empty incident summary."""
    session_root = configure_session_alert_test(monkeypatch, tmp_path)
    write_known_session(session_root, "session-incident-empty")

    assert build_session_incident_summary("session-incident-empty") == (
        build_incident_summary_payload(
            "session-incident-empty",
            total_alerts=0,
            total_incidents=0,
            counts_by_detector={},
            counts_by_severity={},
            top_incident_categories={},
            first_alert_timestamp_utc=None,
            last_alert_timestamp_utc=None,
            narrative_summary="Session session-incident-empty had no alerts.",
        )
    )


def test_build_session_incident_summary_filters_top_categories_and_narrative(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Filtered incident summaries should update categories and narrative consistently."""
    session_root = configure_session_alert_test(monkeypatch, tmp_path)
    write_known_session(
        session_root,
        "session-incident-summary-filtered",
        alert_rows=[
            build_persisted_alert(
                "session-incident-summary-filtered",
                timestamp_utc="2026-05-06 10:00:00",
                detector_id="video_metrics",
                title="Black screen detected",
                message="First black incident.",
                severity="warning",
                source_name="segment_0001.ts",
            ),
            build_persisted_alert(
                "session-incident-summary-filtered",
                timestamp_utc="2026-05-06 10:02:00",
                detector_id="video_metrics",
                title="Black screen detected",
                message="Second black incident.",
                severity="warning",
                source_name="segment_0002.ts",
            ),
            build_persisted_alert(
                "session-incident-summary-filtered",
                timestamp_utc="2026-05-06 10:04:10",
                detector_id="video_metrics",
                title="Black screen detected",
                message="Third black incident.",
                severity="warning",
                source_name="segment_0003.ts",
            ),
            build_persisted_alert(
                "session-incident-summary-filtered",
                timestamp_utc="2026-05-06 10:04:20",
                detector_id="video_metrics",
                title="Frame freeze detected",
                message="Different warning category.",
                severity="warning",
                source_name="segment_0004.ts",
            ),
            build_persisted_alert(
                "session-incident-summary-filtered",
                timestamp_utc="2026-05-06 10:05:00",
                detector_id="video_blur",
                title="Blur increased",
                message="Filtered out by detector and severity.",
                severity="info",
                source_name="segment_0005.ts",
            ),
        ],
    )

    summary = build_session_incident_summary(
        "session-incident-summary-filtered",
        detector_id="video_metrics",
        severity="warning",
        start_time_utc="2026-05-06 10:00:00",
        end_time_utc="2026-05-06 10:04:30",
    )

    assert summary == build_incident_summary_payload(
        "session-incident-summary-filtered",
        total_alerts=4,
        total_incidents=4,
        counts_by_detector={"video_metrics": 4},
        counts_by_severity={"warning": 4},
        top_incident_categories={
            "Black screen detected": 3,
            "Frame freeze detected": 1,
        },
        first_alert_timestamp_utc="2026-05-06 10:00:00",
        last_alert_timestamp_utc="2026-05-06 10:04:20",
        narrative_summary=summary["narrative_summary"],
    )
    assert_narrative_contains(
        summary["narrative_summary"],
        "session-incident-summary-filtered",
        "4 grouped incidents",
        "4 alerts",
        "video_metrics",
        "black screen detected",
        "4 warning alerts",
        "0 info alerts",
    )


def test_build_session_incident_summary_ignores_malformed_rows_without_failing(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Summary should only reflect valid rows from a mixed alert log."""
    session_root = configure_session_alert_test(monkeypatch, tmp_path)
    session_dir = write_known_session(session_root, "session-incident-malformed")
    write_alert_log(
        session_dir,
        [
            build_persisted_alert(
                "session-incident-malformed",
                timestamp_utc="2026-05-06 10:00:00",
                detector_id="video_metrics",
                title="Black screen detected",
                message="First valid row.",
                severity="warning",
                source_name="segment_0001.ts",
            ),
            "{bad json",
            build_persisted_alert(
                "session-incident-malformed",
                timestamp_utc="2026-05-06 10:00:10",
                detector_id="",
                title="Invalid detector id",
                message="Should be ignored.",
                severity="warning",
                source_name="segment_0002.ts",
            ),
            build_persisted_alert(
                "session-incident-malformed",
                timestamp_utc="2026-05-06 10:00:30",
                detector_id="video_metrics",
                title="Black screen detected",
                message="Second valid row in same incident.",
                severity="warning",
                source_name="segment_0003.ts",
            ),
        ],
    )

    summary = build_session_incident_summary("session-incident-malformed")

    assert summary == build_incident_summary_payload(
        "session-incident-malformed",
        total_alerts=2,
        total_incidents=1,
        counts_by_detector={"video_metrics": 2},
        counts_by_severity={"warning": 2},
        top_incident_categories={"Black screen detected": 1},
        first_alert_timestamp_utc="2026-05-06 10:00:00",
        last_alert_timestamp_utc="2026-05-06 10:00:30",
        narrative_summary=summary["narrative_summary"],
    )
    assert_narrative_contains(
        summary["narrative_summary"],
        "session-incident-malformed",
        "1 grouped incidents",
        "2 alerts",
        "video_metrics",
        "black screen detected",
        "2 warning alerts",
        "0 info alerts",
    )


def test_build_session_incident_summary_reports_no_incidents_when_timestamps_are_unusable(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Incident summaries should stay honest when filtered alerts cannot be grouped."""
    session_root = configure_session_alert_test(monkeypatch, tmp_path)
    write_known_session(
        session_root,
        "session-incident-summary-bad-time",
        alert_rows=[
            build_persisted_alert(
                "session-incident-summary-bad-time",
                timestamp_utc="bad-time",
                detector_id="video_metrics",
                title="Black screen detected",
                message="Cannot build a timeline entry from this row.",
                severity="warning",
                source_name="segment_0001.ts",
            )
        ],
    )

    assert build_session_incident_summary("session-incident-summary-bad-time") == (
        build_incident_summary_payload(
            "session-incident-summary-bad-time",
            total_alerts=1,
            total_incidents=0,
            counts_by_detector={"video_metrics": 1},
            counts_by_severity={"warning": 1},
            top_incident_categories={},
            first_alert_timestamp_utc=None,
            last_alert_timestamp_utc=None,
            narrative_summary=(
                "Session session-incident-summary-bad-time had 1 alert but no grouped "
                "incidents with valid timestamps."
            ),
        )
    )
