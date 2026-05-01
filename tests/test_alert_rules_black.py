"""Black-screen rule scenarios for `video_metrics` alert evaluation.

This file owns the black-rule state machine: threshold entry, rolling-window
behavior, recovery, and per-session/per-source-group isolation.
"""

from alert_rules import evaluate_alerts, reset_session_rule_state

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


def test_video_black_rule_respects_continuous_duration_boundary() -> None:
    """Continuous-black entry should be inclusive at the configured duration boundary."""
    reset_session_rule_state("session-black-boundary")

    alerts = evaluate_alerts(
        session_id="session-black-boundary",
        detector_id="video_metrics",
        row=black_row(longest_black_sec=1.0, black_ratio=0.25),
    )

    assert len(alerts) == 1
    assert "Longest black interval 1.0 sec" in alerts[0].message


def test_video_black_rule_does_not_alert_just_below_continuous_duration_boundary() -> None:
    """Continuous-black entry should fail closed just below the duration threshold."""
    reset_session_rule_state("session-black-below-boundary")

    alerts = evaluate_alerts(
        session_id="session-black-below-boundary",
        detector_id="video_metrics",
        row=black_row(longest_black_sec=0.99, black_ratio=0.25),
    )

    assert alerts == []


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
