"""Focused grouped incident-summary tests layered on top of the raw alert seam.

This suite owns grouped aggregation, top-category counting, and narrative
behavior after raw filtering has already selected the alert rows.
"""

from pathlib import Path

from session_alert_incidents import build_session_incident_summary
from tests.alert_incident_service_test_support import (
    assert_empty_incident_summary,
    summary_narrative,
)
from tests.session_alert_test_support import (
    StaticAlertStore,
    assert_narrative_contains,
    build_incident_summary_payload,
    build_normalized_alert,
    build_persisted_alert,
    configure_session_alert_test,
    write_alert_log,
    write_known_session,
)


def test_build_session_incident_summary_reports_grouped_incident_counts_and_narrative(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Incident summaries should combine raw alert totals with grouped incident totals."""
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
    narrative = summary_narrative(summary)

    assert summary == build_incident_summary_payload(
        "session-incident-summary",
        total_alerts=3,
        total_incidents=2,
        counts_by_detector={"video_metrics": 2, "video_blur": 1},
        counts_by_severity={"warning": 2, "info": 1},
        top_incident_categories={"Black screen detected": 1, "Blur increased": 1},
        first_alert_timestamp_utc="2026-05-06 10:00:00",
        last_alert_timestamp_utc="2026-05-06 10:02:00",
        narrative_summary=narrative,
    )
    assert_narrative_contains(
        narrative,
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

    assert_empty_incident_summary(
        build_session_incident_summary("session-incident-empty"),
        "session-incident-empty",
    )


def test_build_session_incident_summary_filters_top_categories_and_narrative(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Filtered summaries should update grouped categories and narrative consistently."""
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
    narrative = summary_narrative(summary)

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
        narrative_summary=narrative,
    )
    assert_narrative_contains(
        narrative,
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
    """Grouped summaries should ignore malformed rows and reflect only valid alerts."""
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
    narrative = summary_narrative(summary)

    assert summary == build_incident_summary_payload(
        "session-incident-malformed",
        total_alerts=2,
        total_incidents=1,
        counts_by_detector={"video_metrics": 2},
        counts_by_severity={"warning": 2},
        top_incident_categories={"Black screen detected": 1},
        first_alert_timestamp_utc="2026-05-06 10:00:00",
        last_alert_timestamp_utc="2026-05-06 10:00:30",
        narrative_summary=narrative,
    )
    assert_narrative_contains(
        narrative,
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
    """Grouped summaries should stay honest when alerts exist but cannot form incidents."""
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


def test_build_session_incident_summary_keeps_deterministic_narrative_when_counts_tie(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Narrative tie-breaking should stay deterministic for tied grouped counts."""
    session_root = configure_session_alert_test(monkeypatch, tmp_path)
    write_known_session(
        session_root,
        "session-incident-tied-narrative",
        alert_rows=[
            build_persisted_alert(
                "session-incident-tied-narrative",
                timestamp_utc="2026-05-06 10:00:00",
                detector_id="video_blur",
                title="Blur increased",
                message="Blur incident.",
                severity="warning",
                source_name="segment_0001.ts",
            ),
            build_persisted_alert(
                "session-incident-tied-narrative",
                timestamp_utc="2026-05-06 10:02:00",
                detector_id="video_metrics",
                title="Black screen detected",
                message="Black incident.",
                severity="info",
                source_name="segment_0002.ts",
            ),
        ],
    )

    summary = build_session_incident_summary("session-incident-tied-narrative")

    assert summary["total_incidents"] == 2
    assert_narrative_contains(
        summary_narrative(summary),
        "session-incident-tied-narrative",
        "2 grouped incidents",
        "2 alerts",
        "video_metrics",
        "blur increased",
        "1 warning alerts",
        "1 info alerts",
    )


def test_build_session_incident_summary_counts_all_filtered_alerts_even_when_some_cannot_group(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Grouped incident totals should stay separate from raw filtered alert totals."""
    session_root = configure_session_alert_test(monkeypatch, tmp_path)
    write_known_session(
        session_root,
        "session-incident-partial-grouping",
        alert_rows=[
            build_persisted_alert(
                "session-incident-partial-grouping",
                timestamp_utc="2026-05-06 10:00:00",
                detector_id="video_metrics",
                title="Black screen detected",
                message="Valid grouped row.",
                severity="warning",
                source_name="segment_0001.ts",
            ),
            build_persisted_alert(
                "session-incident-partial-grouping",
                timestamp_utc="bad-time",
                detector_id="video_metrics",
                title="Black screen detected",
                message="Counts toward alerts, not incidents.",
                severity="warning",
                source_name="segment_0002.ts",
            ),
        ],
    )

    summary = build_session_incident_summary("session-incident-partial-grouping")

    assert summary["total_alerts"] == 2
    assert summary["total_incidents"] == 1
    assert summary["counts_by_detector"] == {"video_metrics": 2}
    assert summary["counts_by_severity"] == {"warning": 2}


def test_build_session_incident_summary_accepts_an_explicit_store_seam() -> None:
    """Grouped incident summaries should preserve behavior over an injected store seam."""
    store = StaticAlertStore(
        "store-incident-summary",
        [
            build_normalized_alert(
                "store-incident-summary",
                timestamp_utc="2026-05-06 10:00:00",
                detector_id="video_metrics",
                title="Black screen detected",
                message="First grouped row.",
                severity="warning",
                source_name="segment_0001.ts",
            ),
            build_normalized_alert(
                "store-incident-summary",
                timestamp_utc="2026-05-06 10:00:30",
                detector_id="video_metrics",
                title="Black screen detected",
                message="Second grouped row in the same incident.",
                severity="warning",
                source_name="segment_0002.ts",
            ),
            build_normalized_alert(
                "store-incident-summary",
                timestamp_utc="2026-05-06 10:02:00",
                detector_id="video_blur",
                title="Blur increased",
                message="Separate grouped incident.",
                severity="info",
                source_name="segment_0003.ts",
            ),
        ],
    )

    summary = build_session_incident_summary("store-incident-summary", store=store)
    narrative = summary_narrative(summary)

    assert summary == build_incident_summary_payload(
        "store-incident-summary",
        total_alerts=3,
        total_incidents=2,
        counts_by_detector={"video_metrics": 2, "video_blur": 1},
        counts_by_severity={"warning": 2, "info": 1},
        top_incident_categories={"Black screen detected": 1, "Blur increased": 1},
        first_alert_timestamp_utc="2026-05-06 10:00:00",
        last_alert_timestamp_utc="2026-05-06 10:02:00",
        narrative_summary=narrative,
    )
    assert_narrative_contains(
        narrative,
        "store-incident-summary",
        "2 grouped incidents",
        "3 alerts",
        "video_metrics",
        "blur increased",
        "2 warning alerts",
        "1 info alerts",
    )
