"""Focused grouped timeline tests for grouping, ordering, and degradation behavior.

This file owns the positive and edge-heavy grouped timeline seam after any raw
alert filters have already selected candidate rows:

- incident grouping and non-merge rules
- chronological ordering and same-timestamp tie-break behavior
- grouped `source_names` shaping
- malformed or unusable row degradation during grouping
- a light scaling guard against pathological regressions
"""

from pathlib import Path
from time import perf_counter
from typing import cast

import pytest

from session_alert_incidents import build_session_timeline
from session_alerts import AlertEventPayload
from tests.alert_incident_service_test_support import (
    assert_single_timeline_entry,
    timeline_entries,
    timeline_titles,
)
from tests.session_alert_test_support import (
    build_persisted_alert,
    build_timeline_entry,
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
    """The grouping threshold should merge at 60 seconds and split at 61."""
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


@pytest.mark.parametrize(
    ("session_id", "second_alert", "expected_entries"),
    [
        (
            "session-timeline-title-split",
            build_persisted_alert(
                "session-timeline-title-split",
                timestamp_utc="2026-05-06 10:00:20",
                detector_id="video_metrics",
                title="Frame freeze detected",
                message="Different title in the same minute.",
                severity="warning",
                source_name="segment_0002.ts",
            ),
            [
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
            ],
        ),
        (
            "session-timeline-severity-split",
            build_persisted_alert(
                "session-timeline-severity-split",
                timestamp_utc="2026-05-06 10:00:20",
                detector_id="video_metrics",
                title="Black screen detected",
                message="Same title but different severity.",
                severity="info",
                source_name="segment_0002.ts",
            ),
            [
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
                    severity="info",
                    title="Black screen detected",
                    alert_count=1,
                    source_names=["segment_0002.ts"],
                    sample_message="Same title but different severity.",
                ),
            ],
        ),
        (
            "session-timeline-detector-split",
            build_persisted_alert(
                "session-timeline-detector-split",
                timestamp_utc="2026-05-06 10:00:20",
                detector_id="video_blur",
                title="Black screen detected",
                message="Different detector, same title and severity.",
                severity="warning",
                source_name="segment_0002.ts",
            ),
            [
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
                    detector_id="video_blur",
                    severity="warning",
                    title="Black screen detected",
                    alert_count=1,
                    source_names=["segment_0002.ts"],
                    sample_message="Different detector, same title and severity.",
                ),
            ],
        ),
    ],
)
def test_build_session_timeline_keeps_nearby_alerts_separate_when_a_grouping_key_changes(
    monkeypatch,
    tmp_path: Path,
    session_id: str,
    second_alert: AlertEventPayload,
    expected_entries: list[AlertEventPayload],
) -> None:
    """Nearby alerts should stay separate whenever one grouping key changes."""
    session_root = configure_session_alert_test(monkeypatch, tmp_path)
    write_known_session(
        session_root,
        session_id,
        alert_rows=[
            build_persisted_alert(
                session_id,
                timestamp_utc="2026-05-06 10:00:00",
                detector_id="video_metrics",
                title="Black screen detected",
                message="First warning.",
                severity="warning",
                source_name="segment_0001.ts",
            ),
            second_alert,
        ],
    )

    assert build_session_timeline(session_id) == {
        "session_id": session_id,
        "entries": expected_entries,
    }


def test_build_session_timeline_keeps_stable_order_for_same_timestamp_distinct_incidents(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Distinct same-timestamp incidents should keep the persisted-row tie-break order."""
    session_root = configure_session_alert_test(monkeypatch, tmp_path)
    write_known_session(
        session_root,
        "session-timeline-same-time",
        alert_rows=[
            build_persisted_alert(
                "session-timeline-same-time",
                timestamp_utc="2026-05-06 10:00:00",
                detector_id="video_blur",
                title="Blur increased",
                message="Persisted first.",
                severity="info",
                source_name="segment_0002.ts",
            ),
            build_persisted_alert(
                "session-timeline-same-time",
                timestamp_utc="2026-05-06 10:00:00",
                detector_id="video_metrics",
                title="Black screen detected",
                message="Persisted second.",
                severity="warning",
                source_name="segment_0001.ts",
            ),
        ],
    )

    timeline = build_session_timeline("session-timeline-same-time")

    assert timeline_titles(timeline) == [
        "Blur increased",
        "Black screen detected",
    ]


def test_build_session_timeline_deduplicates_source_names_while_preserving_first_seen_order(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Grouped entries should keep unique source names in first-seen order."""
    session_root = configure_session_alert_test(monkeypatch, tmp_path)
    write_known_session(
        session_root,
        "session-timeline-source-names",
        alert_rows=[
            build_persisted_alert(
                "session-timeline-source-names",
                timestamp_utc="2026-05-06 10:00:00",
                detector_id="video_metrics",
                title="Black screen detected",
                message="First row.",
                severity="warning",
                source_name="segment_0002.ts",
            ),
            build_persisted_alert(
                "session-timeline-source-names",
                timestamp_utc="2026-05-06 10:00:20",
                detector_id="video_metrics",
                title="Black screen detected",
                message="Duplicate source name should not repeat.",
                severity="warning",
                source_name="segment_0002.ts",
            ),
            build_persisted_alert(
                "session-timeline-source-names",
                timestamp_utc="2026-05-06 10:00:40",
                detector_id="video_metrics",
                title="Black screen detected",
                message="New source name should append.",
                severity="warning",
                source_name="segment_0003.ts",
            ),
        ],
    )

    timeline = build_session_timeline("session-timeline-source-names")

    assert timeline_entries(timeline)[0]["source_names"] == [
        "segment_0002.ts",
        "segment_0003.ts",
    ]


def test_build_session_timeline_merges_transitive_adjacent_alert_chain(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Grouping should chain across adjacent alerts by previous-alert gap."""
    session_root = configure_session_alert_test(monkeypatch, tmp_path)
    write_known_session(
        session_root,
        "session-timeline-transitive-chain",
        alert_rows=[
            build_persisted_alert(
                "session-timeline-transitive-chain",
                timestamp_utc="2026-05-06 10:00:00",
                detector_id="video_metrics",
                title="Black screen detected",
                message="First alert.",
                severity="warning",
                source_name="segment_0001.ts",
            ),
            build_persisted_alert(
                "session-timeline-transitive-chain",
                timestamp_utc="2026-05-06 10:00:50",
                detector_id="video_metrics",
                title="Black screen detected",
                message="Still the same incident.",
                severity="warning",
                source_name="segment_0002.ts",
            ),
            build_persisted_alert(
                "session-timeline-transitive-chain",
                timestamp_utc="2026-05-06 10:01:40",
                detector_id="video_metrics",
                title="Black screen detected",
                message="Still same incident by previous-alert gap.",
                severity="warning",
                source_name="segment_0003.ts",
            ),
        ],
    )

    assert_single_timeline_entry(
        build_session_timeline("session-timeline-transitive-chain"),
        expected_entry=build_timeline_entry(
            start_time_utc="2026-05-06 10:00:00",
            end_time_utc="2026-05-06 10:01:40",
            detector_id="video_metrics",
            severity="warning",
            title="Black screen detected",
            alert_count=3,
            source_names=["segment_0001.ts", "segment_0002.ts", "segment_0003.ts"],
            sample_message="First alert.",
        ),
    )


def test_build_session_timeline_ignores_invalid_timestamp_rows_without_splitting_valid_incident(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Invalid timestamps should be skipped without splitting neighboring valid incidents."""
    session_root = configure_session_alert_test(monkeypatch, tmp_path)
    write_known_session(
        session_root,
        "session-timeline-invalid-middle-row",
        alert_rows=[
            build_persisted_alert(
                "session-timeline-invalid-middle-row",
                timestamp_utc="2026-05-06 10:00:00",
                detector_id="video_metrics",
                title="Black screen detected",
                message="First valid row.",
                severity="warning",
                source_name="segment_0001.ts",
            ),
            build_persisted_alert(
                "session-timeline-invalid-middle-row",
                timestamp_utc="bad-time",
                detector_id="video_metrics",
                title="Black screen detected",
                message="Should be ignored for grouping.",
                severity="warning",
                source_name="segment_0002.ts",
            ),
            build_persisted_alert(
                "session-timeline-invalid-middle-row",
                timestamp_utc="2026-05-06 10:00:30",
                detector_id="video_metrics",
                title="Black screen detected",
                message="Second valid row in same incident.",
                severity="warning",
                source_name="segment_0003.ts",
            ),
        ],
    )

    assert_single_timeline_entry(
        build_session_timeline("session-timeline-invalid-middle-row"),
        expected_entry=build_timeline_entry(
            start_time_utc="2026-05-06 10:00:00",
            end_time_utc="2026-05-06 10:00:30",
            detector_id="video_metrics",
            severity="warning",
            title="Black screen detected",
            alert_count=2,
            source_names=["segment_0001.ts", "segment_0003.ts"],
            sample_message="First valid row.",
        ),
    )


def test_build_session_timeline_ignores_malformed_rows_without_failing(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Grouped timelines should ignore malformed rows and reflect only valid alerts."""
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
    """A moderately large alert log should still group correctly and finish quickly."""
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
        for second in [((group_index * 2) % 60) + (alert_index % 2)]
    ]
    write_known_session(
        session_root,
        "session-timeline-large",
        alert_rows=cast(list[AlertEventPayload | str], alert_rows),
    )

    started_at = perf_counter()
    timeline = build_session_timeline("session-timeline-large")
    entries = timeline_entries(timeline)
    elapsed_seconds = perf_counter() - started_at

    assert len(entries) == 500
    assert entries[0] == build_timeline_entry(
        start_time_utc="2026-05-06 10:00:00",
        end_time_utc="2026-05-06 10:00:01",
        detector_id="video_metrics",
        severity="warning",
        title="Incident category 0",
        alert_count=2,
        source_names=["segment_0000.ts", "segment_0001.ts"],
        sample_message="Alert 0 in grouped incident 0.",
    )
    assert entries[-1] == build_timeline_entry(
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
