"""Focused service tests for grouped alert timeline behavior.

This file owns the timeline-specific incident layer built on top of raw alert
reads:

- deterministic grouping rules
- chronological ordering
- shared filtering before grouping
- empty-state timeline behavior

Grouped incident-summary assertions live in
``test_alert_incident_summary_service.py`` so timeline behavior remains easy
to scan in one pass.
"""

from pathlib import Path
from time import perf_counter

from session_alerts import build_session_timeline
from tests.session_alert_test_support import (
    build_timeline_entry,
    build_persisted_alert,
    configure_session_alert_test,
    write_alert_log,
    write_known_session,
)


def test_build_session_timeline_groups_compatible_alerts_into_ordered_incidents(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Timeline entries should be grouped deterministically by incident rules."""
    session_root = configure_session_alert_test(monkeypatch, tmp_path)
    write_known_session(
        session_root,
        "session-timeline",
        alert_rows=[
            build_persisted_alert(
                "session-timeline",
                timestamp_utc="2026-05-06 10:00:00",
                detector_id="video_metrics",
                title="Black screen detected",
                message="Black segment started.",
                severity="warning",
                source_name="segment_0001.ts",
            ),
            build_persisted_alert(
                "session-timeline",
                timestamp_utc="2026-05-06 10:00:45",
                detector_id="video_metrics",
                title="Black screen detected",
                message="Black segment continued.",
                severity="warning",
                source_name="segment_0002.ts",
            ),
            build_persisted_alert(
                "session-timeline",
                timestamp_utc="2026-05-06 10:02:00",
                detector_id="video_metrics",
                title="Black screen detected",
                message="New black segment after a long gap.",
                severity="warning",
                source_name="segment_0003.ts",
            ),
            build_persisted_alert(
                "session-timeline",
                timestamp_utc="2026-05-06 10:02:10",
                detector_id="video_blur",
                title="Blur increased",
                message="Blur threshold exceeded.",
                severity="info",
                source_name="segment_0004.ts",
            ),
        ],
    )

    timeline = build_session_timeline("session-timeline")

    assert timeline == {
        "session_id": "session-timeline",
        "entries": [
            build_timeline_entry(
                start_time_utc="2026-05-06 10:00:00",
                end_time_utc="2026-05-06 10:00:45",
                detector_id="video_metrics",
                severity="warning",
                title="Black screen detected",
                alert_count=2,
                source_names=["segment_0001.ts", "segment_0002.ts"],
                sample_message="Black segment started.",
            ),
            build_timeline_entry(
                start_time_utc="2026-05-06 10:02:00",
                end_time_utc="2026-05-06 10:02:00",
                detector_id="video_metrics",
                severity="warning",
                title="Black screen detected",
                alert_count=1,
                source_names=["segment_0003.ts"],
                sample_message="New black segment after a long gap.",
            ),
            build_timeline_entry(
                start_time_utc="2026-05-06 10:02:10",
                end_time_utc="2026-05-06 10:02:10",
                detector_id="video_blur",
                severity="info",
                title="Blur increased",
                alert_count=1,
                source_names=["segment_0004.ts"],
                sample_message="Blur threshold exceeded.",
            ),
        ],
    }


def test_build_session_timeline_orders_incidents_by_timestamp_not_persisted_row_order(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Out-of-order persisted rows should still produce a chronologically ordered timeline."""
    session_root = configure_session_alert_test(monkeypatch, tmp_path)
    write_known_session(
        session_root,
        "session-timeline-out-of-order",
        alert_rows=[
            build_persisted_alert(
                "session-timeline-out-of-order",
                timestamp_utc="2026-05-06 10:00:30",
                detector_id="video_blur",
                title="Blur increased",
                message="Written first but happens later.",
                severity="info",
                source_name="segment_0003.ts",
            ),
            build_persisted_alert(
                "session-timeline-out-of-order",
                timestamp_utc="2026-05-06 10:00:00",
                detector_id="video_metrics",
                title="Black screen detected",
                message="Earlier black segment.",
                severity="warning",
                source_name="segment_0001.ts",
            ),
            build_persisted_alert(
                "session-timeline-out-of-order",
                timestamp_utc="2026-05-06 10:00:10",
                detector_id="video_metrics",
                title="Black screen detected",
                message="Same incident as the earlier alert.",
                severity="warning",
                source_name="segment_0002.ts",
            ),
        ],
    )

    timeline = build_session_timeline("session-timeline-out-of-order")

    assert timeline == {
        "session_id": "session-timeline-out-of-order",
        "entries": [
            build_timeline_entry(
                start_time_utc="2026-05-06 10:00:00",
                end_time_utc="2026-05-06 10:00:10",
                detector_id="video_metrics",
                severity="warning",
                title="Black screen detected",
                alert_count=2,
                source_names=["segment_0001.ts", "segment_0002.ts"],
                sample_message="Earlier black segment.",
            ),
            build_timeline_entry(
                start_time_utc="2026-05-06 10:00:30",
                end_time_utc="2026-05-06 10:00:30",
                detector_id="video_blur",
                severity="info",
                title="Blur increased",
                alert_count=1,
                source_names=["segment_0003.ts"],
                sample_message="Written first but happens later.",
            ),
        ],
    }


def test_build_session_timeline_merges_exact_sixty_second_gap_but_splits_sixty_one(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """The grouping threshold should be inclusive at 60 seconds and split at 61."""
    session_root = configure_session_alert_test(monkeypatch, tmp_path)
    write_known_session(
        session_root,
        "session-timeline-gap-boundary",
        alert_rows=[
            build_persisted_alert(
                "session-timeline-gap-boundary",
                timestamp_utc="2026-05-06 10:00:00",
                detector_id="video_metrics",
                title="Black screen detected",
                message="Incident started.",
                severity="warning",
                source_name="segment_0001.ts",
            ),
            build_persisted_alert(
                "session-timeline-gap-boundary",
                timestamp_utc="2026-05-06 10:01:00",
                detector_id="video_metrics",
                title="Black screen detected",
                message="Still the same incident at exactly sixty seconds.",
                severity="warning",
                source_name="segment_0002.ts",
            ),
            build_persisted_alert(
                "session-timeline-gap-boundary",
                timestamp_utc="2026-05-06 10:02:01",
                detector_id="video_metrics",
                title="Black screen detected",
                message="New incident after sixty-one seconds.",
                severity="warning",
                source_name="segment_0003.ts",
            ),
        ],
    )

    timeline = build_session_timeline("session-timeline-gap-boundary")

    assert timeline == {
        "session_id": "session-timeline-gap-boundary",
        "entries": [
            build_timeline_entry(
                start_time_utc="2026-05-06 10:00:00",
                end_time_utc="2026-05-06 10:01:00",
                detector_id="video_metrics",
                severity="warning",
                title="Black screen detected",
                alert_count=2,
                source_names=["segment_0001.ts", "segment_0002.ts"],
                sample_message="Incident started.",
            ),
            build_timeline_entry(
                start_time_utc="2026-05-06 10:02:01",
                end_time_utc="2026-05-06 10:02:01",
                detector_id="video_metrics",
                severity="warning",
                title="Black screen detected",
                alert_count=1,
                source_names=["segment_0003.ts"],
                sample_message="New incident after sixty-one seconds.",
            ),
        ],
    }


def test_build_session_timeline_respects_shared_filters(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Timeline should reuse the shared alert filters before grouping incidents."""
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


def test_build_session_timeline_does_not_merge_nearby_alerts_with_different_titles_or_severity(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Close timestamps alone should not collapse distinct alert types into one incident."""
    session_root = configure_session_alert_test(monkeypatch, tmp_path)
    write_known_session(
        session_root,
        "session-timeline-distinct-nearby",
        alert_rows=[
            build_persisted_alert(
                "session-timeline-distinct-nearby",
                timestamp_utc="2026-05-06 10:00:00",
                detector_id="video_metrics",
                title="Black screen detected",
                message="First warning.",
                severity="warning",
                source_name="segment_0001.ts",
            ),
            build_persisted_alert(
                "session-timeline-distinct-nearby",
                timestamp_utc="2026-05-06 10:00:20",
                detector_id="video_metrics",
                title="Frame freeze detected",
                message="Different title in the same minute.",
                severity="warning",
                source_name="segment_0002.ts",
            ),
            build_persisted_alert(
                "session-timeline-distinct-nearby",
                timestamp_utc="2026-05-06 10:00:40",
                detector_id="video_metrics",
                title="Black screen detected",
                message="Same title but different severity.",
                severity="info",
                source_name="segment_0003.ts",
            ),
        ],
    )

    timeline = build_session_timeline("session-timeline-distinct-nearby")

    assert timeline == {
        "session_id": "session-timeline-distinct-nearby",
        "entries": [
            build_timeline_entry(
                start_time_utc="2026-05-06 10:00:00",
                end_time_utc="2026-05-06 10:00:00",
                detector_id="video_metrics",
                severity="warning",
                title="Black screen detected",
                alert_count=1,
                source_names=["segment_0001.ts"],
                sample_message="First warning.",
            ),
            build_timeline_entry(
                start_time_utc="2026-05-06 10:00:20",
                end_time_utc="2026-05-06 10:00:20",
                detector_id="video_metrics",
                severity="warning",
                title="Frame freeze detected",
                alert_count=1,
                source_names=["segment_0002.ts"],
                sample_message="Different title in the same minute.",
            ),
            build_timeline_entry(
                start_time_utc="2026-05-06 10:00:40",
                end_time_utc="2026-05-06 10:00:40",
                detector_id="video_metrics",
                severity="info",
                title="Black screen detected",
                alert_count=1,
                source_names=["segment_0003.ts"],
                sample_message="Same title but different severity.",
            ),
        ],
    }


def test_build_session_timeline_returns_empty_entries_for_known_empty_session(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Known sessions without alerts should keep a stable empty timeline contract."""
    session_root = configure_session_alert_test(monkeypatch, tmp_path)
    write_known_session(session_root, "session-timeline-empty")

    assert build_session_timeline("session-timeline-empty") == {
        "session_id": "session-timeline-empty",
        "entries": [],
    }


def test_build_session_timeline_ignores_malformed_rows_without_failing(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Timeline should only reflect valid rows from a mixed alert log."""
    session_root = configure_session_alert_test(monkeypatch, tmp_path)
    session_dir = write_known_session(session_root, "session-timeline-malformed")
    write_alert_log(
        session_dir,
        [
            build_persisted_alert(
                "session-timeline-malformed",
                timestamp_utc="2026-05-06 10:00:00",
                detector_id="video_metrics",
                title="Black screen detected",
                message="First valid row.",
                severity="warning",
                source_name="segment_0001.ts",
            ),
            "{bad json",
            build_persisted_alert(
                "session-timeline-malformed",
                timestamp_utc="2026-05-06 10:00:10",
                detector_id="",
                title="Invalid detector id",
                message="Should be ignored.",
                severity="warning",
                source_name="segment_0002.ts",
            ),
            build_persisted_alert(
                "session-timeline-malformed",
                timestamp_utc="2026-05-06 10:00:30",
                detector_id="video_metrics",
                title="Black screen detected",
                message="Second valid row in same incident.",
                severity="warning",
                source_name="segment_0003.ts",
            ),
        ],
    )

    assert build_session_timeline("session-timeline-malformed") == {
        "session_id": "session-timeline-malformed",
        "entries": [
            build_timeline_entry(
                start_time_utc="2026-05-06 10:00:00",
                end_time_utc="2026-05-06 10:00:30",
                detector_id="video_metrics",
                severity="warning",
                title="Black screen detected",
                alert_count=2,
                source_names=["segment_0001.ts", "segment_0003.ts"],
                sample_message="First valid row.",
            )
        ],
    }


def test_build_session_timeline_handles_larger_alert_logs_without_pathological_slowdown(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """A moderately large alert log should still group correctly and finish quickly.

    This is a light scaling guard, not a microbenchmark. The threshold is
    intentionally generous so the test catches obvious regressions such as
    accidental quadratic grouping behavior without becoming flaky in CI.
    """
    session_root = configure_session_alert_test(monkeypatch, tmp_path)
    alert_rows = [
        build_persisted_alert(
            "session-timeline-large",
            timestamp_utc=f"2026-05-06 10:{minute:02d}:{second:02d}",
            detector_id="video_metrics",
            title=f"Incident category {group_index % 5}",
            message=f"Alert {alert_index} in grouped incident {group_index}.",
            severity="warning",
            source_name=f"segment_{alert_index:04d}.ts",
        )
        for alert_index in range(1000)
        for group_index in [alert_index // 2]
        for minute in [(group_index * 2) // 60]
        for second in [
            ((group_index * 2) % 60) + (alert_index % 2),
        ]
    ]
    write_known_session(
        session_root,
        "session-timeline-large",
        alert_rows=alert_rows,
    )

    started_at = perf_counter()
    timeline = build_session_timeline("session-timeline-large")
    elapsed_seconds = perf_counter() - started_at

    assert len(timeline["entries"]) == 500
    assert timeline["entries"][0] == build_timeline_entry(
        start_time_utc="2026-05-06 10:00:00",
        end_time_utc="2026-05-06 10:00:01",
        detector_id="video_metrics",
        severity="warning",
        title="Incident category 0",
        alert_count=2,
        source_names=["segment_0000.ts", "segment_0001.ts"],
        sample_message="Alert 0 in grouped incident 0.",
    )
    assert timeline["entries"][-1] == build_timeline_entry(
        start_time_utc="2026-05-06 10:16:38",
        end_time_utc="2026-05-06 10:16:39",
        detector_id="video_metrics",
        severity="warning",
        title="Incident category 4",
        alert_count=2,
        source_names=["segment_0998.ts", "segment_0999.ts"],
        sample_message="Alert 998 in grouped incident 499.",
    )
    assert elapsed_seconds < 1.5
