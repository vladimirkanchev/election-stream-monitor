"""Stateful black-screen rule scenarios for the production ``video_metrics`` path."""

import pytest

from alert_rules import (
    BlackWindowSummary,
    _has_black_rule_recovered,
    evaluate_alerts,
    reset_session_rule_state,
    should_alert_video_black,
)

from tests.alert_rules_test_support import assert_no_alerts, black_row, evaluate_detector_rows


def test_video_black_rule_raises_alert_for_long_black_interval() -> None:
    """Long continuous black duration should trigger entry without a full window."""
    reset_session_rule_state("session-1")
    alerts = evaluate_alerts(
        session_id="session-1",
        detector_id="video_metrics",
        row=black_row(
            source_group="playlist-a",
            source_name="segment_001.ts",
            black_ratio=0.25,
            longest_black_sec=1.2,
        ),
    )

    assert len(alerts) == 1
    assert alerts[0].title == "Black screen detected"
    assert "entered a black-screen state" in alerts[0].message
    assert "Longest black interval 1.2 sec" in alerts[0].message


def test_video_black_rule_raises_alert_for_rolling_black_ratio() -> None:
    """Sustained high black ratio should enter on the third slice of the window."""
    reset_session_rule_state("session-rolling")

    first, second, third = evaluate_detector_rows(
        session_id="session-rolling",
        detector_id="video_metrics",
        rows=[
            black_row(
                timestamp_utc="2026-03-31 10:00:00",
                source_group="playlist-a",
                source_name="segment_001.ts",
                black_ratio=0.9,
                longest_black_sec=0.4,
            ),
            black_row(
                timestamp_utc="2026-03-31 10:00:01",
                source_group="playlist-a",
                source_name="segment_002.ts",
                black_ratio=0.9,
                longest_black_sec=0.4,
            ),
            black_row(
                timestamp_utc="2026-03-31 10:00:02",
                source_group="playlist-a",
                source_name="segment_003.ts",
                black_ratio=0.9,
                longest_black_sec=0.4,
            ),
        ],
    )

    assert_no_alerts(first, second)
    assert len(third) == 1
    assert "entered a black-screen state" in third[0].message
    assert "Rolling black ratio across the last 3 sec was 0.9" in third[0].message


def test_video_black_rule_tolerates_malformed_rows_before_valid_rolling_entry() -> None:
    """Malformed early rows should fail closed without blocking a later valid rolling-ratio alert."""
    reset_session_rule_state("session-rolling-malformed")

    first, second, third, fourth = evaluate_detector_rows(
        session_id="session-rolling-malformed",
        detector_id="video_metrics",
        rows=[
            black_row(
                timestamp_utc="2026-03-31 10:00:00",
                source_group="playlist-malformed",
                source_name="segment_000.ts",
                duration_sec=0.1,
                black_ratio="not-a-number",
                longest_black_sec="bad",
            ),
            black_row(
                timestamp_utc="2026-03-31 10:00:01",
                source_group="playlist-malformed",
                source_name="segment_001.ts",
                black_ratio=1.0,
                longest_black_sec=0.4,
            ),
            black_row(
                timestamp_utc="2026-03-31 10:00:02",
                source_group="playlist-malformed",
                source_name="segment_002.ts",
                black_ratio=1.0,
                longest_black_sec=0.4,
            ),
            black_row(
                timestamp_utc="2026-03-31 10:00:03",
                source_group="playlist-malformed",
                source_name="segment_003.ts",
                black_ratio=1.0,
                longest_black_sec=0.4,
            ),
        ],
    )

    assert_no_alerts(first, second, third)
    assert len(fourth) == 1
    assert "entered a black-screen state" in fourth[0].message
    assert "Rolling black ratio across the last 3 sec was 1.0" in fourth[0].message


def test_video_black_rule_does_not_alert_before_rolling_window_is_full() -> None:
    """Rolling-ratio entry should stay quiet until the configured window is full."""
    reset_session_rule_state("session-black-short")

    first, second = evaluate_detector_rows(
        session_id="session-black-short",
        detector_id="video_metrics",
        rows=[
            black_row(
                timestamp_utc="2026-03-31 10:00:00",
                source_group="playlist-short",
                source_name="segment_001.ts",
                black_ratio=0.95,
                longest_black_sec=0.4,
            ),
            black_row(
                timestamp_utc="2026-03-31 10:00:01",
                source_group="playlist-short",
                source_name="segment_002.ts",
                black_ratio=0.95,
                longest_black_sec=0.4,
            ),
        ],
    )

    assert_no_alerts(first, second)


def test_video_black_rule_does_not_repeat_until_recovery_then_alerts_again() -> None:
    """An active black episode should suppress duplicates until full recovery occurs."""
    reset_session_rule_state("session-black-repeat")

    first_alert = evaluate_alerts(
        session_id="session-black-repeat",
        detector_id="video_metrics",
        row=black_row(
            timestamp_utc="2026-03-31 10:00:00",
            source_group="playlist-c",
            source_name="segment_001.ts",
            black_ratio=0.95,
            longest_black_sec=1.2,
        ),
    )
    assert len(first_alert) == 1

    still_black = evaluate_alerts(
        session_id="session-black-repeat",
        detector_id="video_metrics",
        row=black_row(
            timestamp_utc="2026-03-31 10:00:01",
            source_group="playlist-c",
            source_name="segment_002.ts",
            black_ratio=0.95,
            longest_black_sec=1.2,
        ),
    )
    assert_no_alerts(still_black)

    recoveries = evaluate_detector_rows(
        session_id="session-black-repeat",
        detector_id="video_metrics",
        rows=[
            black_row(
                timestamp_utc=f"2026-03-31 10:00:0{index}",
                source_group="playlist-c",
                source_name=f"segment_00{index + 1}.ts",
                black_detected=False,
                black_ratio=ratio,
                longest_black_sec=0.0,
            )
            for index, ratio in enumerate((0.0, 0.0, 0.0), start=2)
        ],
    )
    assert_no_alerts(*recoveries)

    second_alert = evaluate_alerts(
        session_id="session-black-repeat",
        detector_id="video_metrics",
        row=black_row(
            timestamp_utc="2026-03-31 10:00:05",
            source_group="playlist-c",
            source_name="segment_006.ts",
            black_ratio=0.95,
            longest_black_sec=1.2,
        ),
    )
    assert len(second_alert) == 1
    assert second_alert[0].timestamp_utc == "2026-03-31 10:00:05"


def test_video_black_rule_emits_separate_alerts_before_and_after_recovery() -> None:
    """A black episode should ring once, recover, and ring again later in the timeline."""
    reset_session_rule_state("session-black-separated-alerts")

    first_episode = evaluate_detector_rows(
        session_id="session-black-separated-alerts",
        detector_id="video_metrics",
        rows=[
            black_row(
                timestamp_utc="2026-03-31 10:00:00",
                source_group="playlist-separated",
                source_name="segment_001.ts",
                black_ratio=0.95,
                longest_black_sec=1.2,
            ),
            black_row(
                timestamp_utc="2026-03-31 10:00:01",
                source_group="playlist-separated",
                source_name="segment_002.ts",
                black_ratio=0.95,
                longest_black_sec=1.2,
            ),
        ],
    )
    assert len(first_episode[0]) == 1
    assert_no_alerts(first_episode[1])

    recovery_batches = evaluate_detector_rows(
        session_id="session-black-separated-alerts",
        detector_id="video_metrics",
        rows=[
            black_row(
                timestamp_utc="2026-03-31 10:00:02",
                source_group="playlist-separated",
                source_name="segment_003.ts",
                black_detected=False,
                black_ratio=0.0,
                longest_black_sec=0.0,
            ),
            black_row(
                timestamp_utc="2026-03-31 10:00:03",
                source_group="playlist-separated",
                source_name="segment_004.ts",
                black_detected=False,
                black_ratio=0.0,
                longest_black_sec=0.0,
            ),
            black_row(
                timestamp_utc="2026-03-31 10:00:04",
                source_group="playlist-separated",
                source_name="segment_005.ts",
                black_detected=False,
                black_ratio=0.0,
                longest_black_sec=0.0,
            ),
        ],
    )
    assert_no_alerts(*recovery_batches)

    second_episode = evaluate_detector_rows(
        session_id="session-black-separated-alerts",
        detector_id="video_metrics",
        rows=[
            black_row(
                timestamp_utc="2026-03-31 10:00:08",
                source_group="playlist-separated",
                source_name="segment_008.ts",
                black_ratio=0.95,
                longest_black_sec=1.2,
            ),
            black_row(
                timestamp_utc="2026-03-31 10:00:09",
                source_group="playlist-separated",
                source_name="segment_009.ts",
                black_ratio=0.95,
                longest_black_sec=1.2,
            ),
        ],
    )
    assert len(second_episode[0]) == 1
    assert second_episode[0][0].timestamp_utc == "2026-03-31 10:00:08"
    assert_no_alerts(second_episode[1])


@pytest.mark.parametrize(
    ("session_id", "longest_black_sec", "expected_count", "expected_message_part"),
    [
        (
            "session-black-boundary",
            1.0,
            1,
            "Longest black interval 1.0 sec",
        ),
        (
            "session-black-below-boundary",
            0.99,
            0,
            "",
        ),
    ],
)
def test_video_black_rule_continuous_duration_boundary_behavior(
    session_id: str,
    longest_black_sec: float,
    expected_count: int,
    expected_message_part: str,
) -> None:
    """Continuous-black entry should stay inclusive at the boundary and fail closed below it."""
    reset_session_rule_state(session_id)

    alerts = evaluate_alerts(
        session_id=session_id,
        detector_id="video_metrics",
        row=black_row(longest_black_sec=longest_black_sec, black_ratio=0.25),
    )

    assert len(alerts) == expected_count
    if expected_count:
        assert expected_message_part in alerts[0].message


def test_video_black_rule_does_not_alert_when_rolling_ratio_is_just_below_threshold() -> None:
    """Rolling-ratio entry should fail closed when the ratio stays just below threshold."""
    reset_session_rule_state("session-black-rolling-below")

    first, second, third = evaluate_detector_rows(
        session_id="session-black-rolling-below",
        detector_id="video_metrics",
        rows=[
            black_row(
                timestamp_utc="2026-03-31 10:00:00",
                source_group="playlist-threshold",
                source_name="segment_001.ts",
                longest_black_sec=0.4,
                black_ratio=0.79,
            ),
            black_row(
                timestamp_utc="2026-03-31 10:00:01",
                source_group="playlist-threshold",
                source_name="segment_002.ts",
                longest_black_sec=0.4,
                black_ratio=0.79,
            ),
            black_row(
                timestamp_utc="2026-03-31 10:00:02",
                source_group="playlist-threshold",
                source_name="segment_003.ts",
                longest_black_sec=0.4,
                black_ratio=0.79,
            ),
        ],
    )

    assert_no_alerts(first, second, third)


def test_video_black_rule_records_full_window_metrics_just_below_rolling_threshold() -> None:
    """A full just-below rolling black window should stay normal and record the expected metrics."""
    reset_session_rule_state("session-black-rolling-below-metrics")

    first_row = black_row(
        timestamp_utc="2026-03-31 10:00:00",
        source_group="playlist-threshold-metrics",
        source_name="segment_001.ts",
        longest_black_sec=0.4,
        black_ratio=0.799,
    )
    second_row = black_row(
        timestamp_utc="2026-03-31 10:00:01",
        source_group="playlist-threshold-metrics",
        source_name="segment_002.ts",
        longest_black_sec=0.4,
        black_ratio=0.799,
    )
    third_row = black_row(
        timestamp_utc="2026-03-31 10:00:02",
        source_group="playlist-threshold-metrics",
        source_name="segment_003.ts",
        longest_black_sec=0.4,
        black_ratio=0.799,
    )

    assert should_alert_video_black("session-black-rolling-below-metrics", first_row) is False
    assert should_alert_video_black("session-black-rolling-below-metrics", second_row) is False
    assert should_alert_video_black("session-black-rolling-below-metrics", third_row) is False

    assert third_row["rolling_black_ratio"] == 0.799
    assert third_row["rolling_window_sec"] == 3.0
    assert third_row["black_rule_state"] == "normal"
    assert third_row["black_rule_reason"] == "none"


def test_video_black_rule_alerts_at_exact_rolling_ratio_threshold() -> None:
    """Rolling-ratio entry should be inclusive at the configured threshold."""
    reset_session_rule_state("session-black-rolling-boundary")

    first, second, third = evaluate_detector_rows(
        session_id="session-black-rolling-boundary",
        detector_id="video_metrics",
        rows=[
            black_row(
                timestamp_utc="2026-03-31 10:00:00",
                source_group="playlist-threshold",
                source_name="segment_001.ts",
                longest_black_sec=0.4,
                black_ratio=0.8,
            ),
            black_row(
                timestamp_utc="2026-03-31 10:00:01",
                source_group="playlist-threshold",
                source_name="segment_002.ts",
                longest_black_sec=0.4,
                black_ratio=0.8,
            ),
            black_row(
                timestamp_utc="2026-03-31 10:00:02",
                source_group="playlist-threshold",
                source_name="segment_003.ts",
                longest_black_sec=0.4,
                black_ratio=0.8,
            ),
        ],
    )

    assert_no_alerts(first, second)
    assert len(third) == 1


def test_video_black_rule_resets_between_sessions() -> None:
    """Per-session black rolling state should not leak into a fresh session id."""
    reset_session_rule_state("session-black-a")
    first_session = evaluate_alerts(
        session_id="session-black-a",
        detector_id="video_metrics",
        row=black_row(
            timestamp_utc="2026-03-31 10:00:00",
            source_group="playlist-reset",
            source_name="segment_001.ts",
            black_ratio=0.95,
            longest_black_sec=0.4,
        ),
    )
    assert_no_alerts(first_session)

    reset_session_rule_state("session-black-b")
    second_session = evaluate_alerts(
        session_id="session-black-b",
        detector_id="video_metrics",
        row=black_row(
            timestamp_utc="2026-03-31 10:01:00",
            source_group="playlist-reset",
            source_name="segment_001.ts",
            black_ratio=0.95,
            longest_black_sec=0.4,
        ),
    )
    assert_no_alerts(second_session)


def test_video_black_rule_keeps_rolling_state_isolated_per_source_group() -> None:
    """Interleaved source groups should not contribute to another group's rolling window."""
    reset_session_rule_state("session-black-groups")

    first_a, only_b, second_a, third_a = evaluate_detector_rows(
        session_id="session-black-groups",
        detector_id="video_metrics",
        rows=[
            black_row(
                timestamp_utc="2026-03-31 10:00:00",
                source_group="playlist-a",
                source_name="a-segment-001.ts",
                black_ratio=0.95,
                longest_black_sec=0.4,
            ),
            black_row(
                timestamp_utc="2026-03-31 10:00:01",
                source_group="playlist-b",
                source_name="b-segment-001.ts",
                black_ratio=0.95,
                longest_black_sec=0.4,
            ),
            black_row(
                timestamp_utc="2026-03-31 10:00:02",
                source_group="playlist-a",
                source_name="a-segment-002.ts",
                black_ratio=0.95,
                longest_black_sec=0.4,
            ),
            black_row(
                timestamp_utc="2026-03-31 10:00:03",
                source_group="playlist-a",
                source_name="a-segment-003.ts",
                black_ratio=0.95,
                longest_black_sec=0.4,
            ),
        ],
    )

    assert_no_alerts(first_a, only_b, second_a)
    assert len(third_a) == 1


def test_video_black_rule_does_not_recover_from_other_source_groups() -> None:
    """Recovery on one source group should not clear an active black state on another."""
    reset_session_rule_state("session-black-cross-recovery")

    entered = evaluate_alerts(
        session_id="session-black-cross-recovery",
        detector_id="video_metrics",
        row=black_row(
            timestamp_utc="2026-03-31 10:00:00",
            source_group="playlist-a",
            source_name="a-segment-001.ts",
            black_ratio=0.95,
            longest_black_sec=1.2,
        ),
    )
    assert len(entered) == 1

    recovered_other_batches = evaluate_detector_rows(
        session_id="session-black-cross-recovery",
        detector_id="video_metrics",
        rows=[
            black_row(
                timestamp_utc=f"2026-03-31 10:00:0{index}",
                source_group="playlist-b",
                source_name=f"b-segment-00{index}.ts",
                black_detected=False,
                black_ratio=0.0,
                longest_black_sec=0.0,
            )
            for index in range(1, 4)
        ],
    )
    assert_no_alerts(*recovered_other_batches)

    still_active_on_a = evaluate_alerts(
        session_id="session-black-cross-recovery",
        detector_id="video_metrics",
        row=black_row(
            timestamp_utc="2026-03-31 10:00:04",
            source_group="playlist-a",
            source_name="a-segment-002.ts",
            black_ratio=0.95,
            longest_black_sec=1.2,
        ),
    )

    assert_no_alerts(still_active_on_a)


def test_video_black_rule_recovers_at_exact_recovery_ratio_threshold() -> None:
    """Black recovery should be inclusive at the exact configured ratio boundary."""
    assert _has_black_rule_recovered(
        summary=BlackWindowSummary(
            rolling_ratio=0.2,
            observed_window_sec=3.0,
        ),
        longest_black_sec=0.0,
    ) is True


def test_video_black_rule_does_not_recover_when_longest_black_stays_at_duration_boundary() -> None:
    """A black episode should stay active when the longest black interval remains at the alert boundary."""
    reset_session_rule_state("session-black-recovery-duration-boundary")

    entered = evaluate_alerts(
        session_id="session-black-recovery-duration-boundary",
        detector_id="video_metrics",
        row=black_row(
            timestamp_utc="2026-03-31 10:00:00",
            source_group="playlist-recovery-duration-boundary",
            source_name="segment_001.ts",
            black_ratio=0.95,
            longest_black_sec=1.2,
        ),
    )
    assert len(entered) == 1

    almost_recovered_batches = evaluate_detector_rows(
        session_id="session-black-recovery-duration-boundary",
        detector_id="video_metrics",
        rows=[
            black_row(
                timestamp_utc="2026-03-31 10:00:01",
                source_group="playlist-recovery-duration-boundary",
                source_name="segment_002.ts",
                black_detected=False,
                black_ratio=0.2,
                longest_black_sec=1.0,
            ),
            black_row(
                timestamp_utc="2026-03-31 10:00:02",
                source_group="playlist-recovery-duration-boundary",
                source_name="segment_003.ts",
                black_detected=False,
                black_ratio=0.2,
                longest_black_sec=1.0,
            ),
            black_row(
                timestamp_utc="2026-03-31 10:00:03",
                source_group="playlist-recovery-duration-boundary",
                source_name="segment_004.ts",
                black_detected=False,
                black_ratio=0.2,
                longest_black_sec=1.0,
            ),
        ],
    )
    assert_no_alerts(*almost_recovered_batches)

    still_active = evaluate_alerts(
        session_id="session-black-recovery-duration-boundary",
        detector_id="video_metrics",
        row=black_row(
            timestamp_utc="2026-03-31 10:00:04",
            source_group="playlist-recovery-duration-boundary",
            source_name="segment_005.ts",
            black_ratio=0.95,
            longest_black_sec=1.2,
        ),
    )

    assert_no_alerts(still_active)
