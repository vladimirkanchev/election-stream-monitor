"""Blur-rule scenarios for `video_blur` alert evaluation.

This file owns the blur-rule state machine: rolling-window entry, recovery,
re-entry, and per-session/per-source-group isolation.
"""

from alert_rules import evaluate_alerts, reset_session_rule_state

from tests.alert_rules_test_support import assert_no_alerts, blur_row, evaluate_detector_rows


def test_video_blur_rule_raises_alert_for_normalized_blur_score() -> None:
    """Two-above-one-below window should enter once the blur threshold is met."""
    reset_session_rule_state("session-blur")
    first, second, third = evaluate_detector_rows(
        session_id="session-blur",
        detector_id="video_blur",
        rows=[
            blur_row(
                timestamp_utc="2026-03-31 10:00:00",
                source_group="playlist-a",
                source_name="segment_001.ts",
                blur_score=0.80,
                threshold_used=0.72,
            ),
            blur_row(
                timestamp_utc="2026-03-31 10:00:01",
                source_group="playlist-a",
                source_name="segment_002.ts",
                blur_score=0.76,
                threshold_used=0.72,
            ),
            blur_row(
                timestamp_utc="2026-03-31 10:00:02",
                source_group="playlist-a",
                source_name="segment_003.ts",
                blur_score=0.60,
                threshold_used=0.72,
            ),
        ],
    )

    assert_no_alerts(first, second)
    assert len(third) == 1
    assert "entered a blurry state" in third[0].message
    assert "2 of 3 slices above the threshold 0.72" in third[0].message


def test_video_blur_rule_does_not_alert_before_rolling_window_is_full() -> None:
    """Blur entry should stay quiet until the rolling window is fully populated."""
    reset_session_rule_state("session-blur-short")

    first, second = evaluate_detector_rows(
        session_id="session-blur-short",
        detector_id="video_blur",
        rows=[
            blur_row(
                timestamp_utc="2026-03-31 10:00:00",
                source_group="playlist-short",
                source_name="segment_001.ts",
                blur_score=0.9,
                threshold_used=0.72,
            ),
            blur_row(
                timestamp_utc="2026-03-31 10:00:01",
                source_group="playlist-short",
                source_name="segment_002.ts",
                blur_score=0.9,
                threshold_used=0.72,
            ),
        ],
    )

    assert_no_alerts(first, second)


def test_video_blur_rule_respects_threshold_boundary() -> None:
    """Blur threshold comparison should be inclusive at the exact configured boundary."""
    reset_session_rule_state("session-blur-boundary")

    first, second, third = evaluate_detector_rows(
        session_id="session-blur-boundary",
        detector_id="video_blur",
        rows=[
            blur_row(
                timestamp_utc="2026-03-31 10:00:00",
                source_group="playlist-boundary",
                source_name="segment_001.ts",
                blur_score=0.72,
                threshold_used=0.72,
            ),
            blur_row(
                timestamp_utc="2026-03-31 10:00:01",
                source_group="playlist-boundary",
                source_name="segment_002.ts",
                blur_score=0.72,
                threshold_used=0.72,
            ),
            blur_row(
                timestamp_utc="2026-03-31 10:00:02",
                source_group="playlist-boundary",
                source_name="segment_003.ts",
                blur_score=0.60,
                threshold_used=0.72,
            ),
        ],
    )

    assert_no_alerts(first, second)
    assert len(third) == 1


def test_video_blur_rule_does_not_repeat_until_recovery_then_alerts_again() -> None:
    """An active blur episode should suppress duplicates until the window fully recovers."""
    reset_session_rule_state("session-blur-repeat")

    entering_scores = [0.82, 0.79, 0.60]
    entering_alerts = evaluate_detector_rows(
        session_id="session-blur-repeat",
        detector_id="video_blur",
        rows=[
            blur_row(
                timestamp_utc=f"2026-03-31 10:00:0{index}",
                source_group="playlist-b",
                source_name=f"segment_00{index + 1}.ts",
                blur_score=score,
                threshold_used=0.72,
            )
            for index, score in enumerate(entering_scores)
        ],
    )
    alerts = entering_alerts[-1]

    assert len(alerts) == 1

    still_blurry = evaluate_alerts(
        session_id="session-blur-repeat",
        detector_id="video_blur",
        row=blur_row(
            timestamp_utc="2026-03-31 10:00:04",
            source_group="playlist-b",
            source_name="segment_004.ts",
            blur_score=0.90,
            threshold_used=0.72,
        ),
    )
    assert_no_alerts(still_blurry)

    recoveries = evaluate_detector_rows(
        session_id="session-blur-repeat",
        detector_id="video_blur",
        rows=[
            blur_row(
                timestamp_utc=f"2026-03-31 10:00:{index:02d}",
                source_group="playlist-b",
                source_name=f"segment_{index:03d}.ts",
                blur_detected=False,
                blur_score=score,
                threshold_used=0.72,
            )
            for index, score in enumerate((0.40, 0.42, 0.45), start=5)
        ],
    )
    assert_no_alerts(*recoveries)

    reenter_alert_batches = evaluate_detector_rows(
        session_id="session-blur-repeat",
        detector_id="video_blur",
        rows=[
            blur_row(
                timestamp_utc=f"2026-03-31 10:00:{index:02d}",
                source_group="playlist-b",
                source_name=f"segment_{index:03d}.ts",
                blur_score=score,
                threshold_used=0.72,
            )
            for index, score in enumerate((0.81, 0.77, 0.78), start=8)
        ],
    )
    reenter_alert_counts = [len(alerts) for alerts in reenter_alert_batches]

    assert reenter_alert_counts == [0, 1, 0]


def test_video_blur_rule_emits_separate_alerts_before_and_after_recovery() -> None:
    """A blur episode should ring once, recover, and ring again later in the timeline."""
    reset_session_rule_state("session-blur-separated-alerts")

    first_episode = evaluate_detector_rows(
        session_id="session-blur-separated-alerts",
        detector_id="video_blur",
        rows=[
            blur_row(
                timestamp_utc="2026-03-31 10:00:00",
                source_group="playlist-separated",
                source_name="segment_001.ts",
                blur_score=0.82,
                threshold_used=0.72,
            ),
            blur_row(
                timestamp_utc="2026-03-31 10:00:01",
                source_group="playlist-separated",
                source_name="segment_002.ts",
                blur_score=0.79,
                threshold_used=0.72,
            ),
            blur_row(
                timestamp_utc="2026-03-31 10:00:02",
                source_group="playlist-separated",
                source_name="segment_003.ts",
                blur_score=0.60,
                threshold_used=0.72,
            ),
        ],
    )
    assert_no_alerts(first_episode[0], first_episode[1])
    assert len(first_episode[2]) == 1
    assert first_episode[2][0].timestamp_utc == "2026-03-31 10:00:02"

    recovery_batches = evaluate_detector_rows(
        session_id="session-blur-separated-alerts",
        detector_id="video_blur",
        rows=[
            blur_row(
                timestamp_utc="2026-03-31 10:00:03",
                source_group="playlist-separated",
                source_name="segment_004.ts",
                blur_detected=False,
                blur_score=0.40,
                threshold_used=0.72,
            ),
            blur_row(
                timestamp_utc="2026-03-31 10:00:04",
                source_group="playlist-separated",
                source_name="segment_005.ts",
                blur_detected=False,
                blur_score=0.42,
                threshold_used=0.72,
            ),
            blur_row(
                timestamp_utc="2026-03-31 10:00:05",
                source_group="playlist-separated",
                source_name="segment_006.ts",
                blur_detected=False,
                blur_score=0.45,
                threshold_used=0.72,
            ),
        ],
    )
    assert_no_alerts(*recovery_batches)

    second_episode = evaluate_detector_rows(
        session_id="session-blur-separated-alerts",
        detector_id="video_blur",
        rows=[
            blur_row(
                timestamp_utc="2026-03-31 10:00:08",
                source_group="playlist-separated",
                source_name="segment_008.ts",
                blur_score=0.81,
                threshold_used=0.72,
            ),
            blur_row(
                timestamp_utc="2026-03-31 10:00:09",
                source_group="playlist-separated",
                source_name="segment_009.ts",
                blur_score=0.77,
                threshold_used=0.72,
            ),
            blur_row(
                timestamp_utc="2026-03-31 10:00:10",
                source_group="playlist-separated",
                source_name="segment_010.ts",
                blur_score=0.78,
                threshold_used=0.72,
            ),
        ],
    )
    assert_no_alerts(second_episode[0])
    assert len(second_episode[1]) == 1
    assert second_episode[1][0].timestamp_utc == "2026-03-31 10:00:09"
    assert_no_alerts(second_episode[2])


def test_video_blur_rule_resets_between_sessions() -> None:
    """Per-session blur rolling state should not leak into a fresh session id."""
    reset_session_rule_state("session-blur-a")
    first_session = evaluate_alerts(
        session_id="session-blur-a",
        detector_id="video_blur",
        row=blur_row(
            timestamp_utc="2026-03-31 10:00:00",
            source_group="playlist-reset",
            source_name="segment_001.ts",
            blur_score=0.90,
            threshold_used=0.72,
        ),
    )
    assert_no_alerts(first_session)

    reset_session_rule_state("session-blur-b")
    second_session = evaluate_alerts(
        session_id="session-blur-b",
        detector_id="video_blur",
        row=blur_row(
            timestamp_utc="2026-03-31 10:01:00",
            source_group="playlist-reset",
            source_name="segment_001.ts",
            blur_score=0.90,
            threshold_used=0.72,
        ),
    )
    assert_no_alerts(second_session)


def test_video_blur_rule_keeps_rolling_state_isolated_per_source_group() -> None:
    """Interleaved source groups should not contribute to another group's blur window."""
    reset_session_rule_state("session-blur-groups")

    first_a, only_b, second_a, third_a = evaluate_detector_rows(
        session_id="session-blur-groups",
        detector_id="video_blur",
        rows=[
            blur_row(
                timestamp_utc="2026-03-31 10:00:00",
                source_group="playlist-a",
                source_name="a-segment-001.ts",
                blur_score=0.82,
                threshold_used=0.72,
            ),
            blur_row(
                timestamp_utc="2026-03-31 10:00:01",
                source_group="playlist-b",
                source_name="b-segment-001.ts",
                blur_score=0.88,
                threshold_used=0.72,
            ),
            blur_row(
                timestamp_utc="2026-03-31 10:00:02",
                source_group="playlist-a",
                source_name="a-segment-002.ts",
                blur_score=0.79,
                threshold_used=0.72,
            ),
            blur_row(
                timestamp_utc="2026-03-31 10:00:03",
                source_group="playlist-a",
                source_name="a-segment-003.ts",
                blur_score=0.60,
                threshold_used=0.72,
            ),
        ],
    )

    assert_no_alerts(first_a, only_b, second_a)
    assert len(third_a) == 1


def test_video_blur_rule_does_not_recover_from_other_source_groups() -> None:
    """Recovery on one source group should not clear an active blur state on another."""
    reset_session_rule_state("session-blur-cross-recovery")

    entered_batches = evaluate_detector_rows(
        session_id="session-blur-cross-recovery",
        detector_id="video_blur",
        rows=[
            blur_row(
                timestamp_utc=f"2026-03-31 10:00:0{index}",
                source_group="playlist-a",
                source_name=f"a-segment-00{index + 1}.ts",
                blur_score=score,
                threshold_used=0.72,
            )
            for index, score in enumerate((0.82, 0.79, 0.60))
        ],
    )
    entered = entered_batches[-1]

    assert len(entered) == 1

    recovered_other_batches = evaluate_detector_rows(
        session_id="session-blur-cross-recovery",
        detector_id="video_blur",
        rows=[
            blur_row(
                timestamp_utc=f"2026-03-31 10:00:0{index}",
                source_group="playlist-b",
                source_name=f"b-segment-00{index}.ts",
                blur_detected=False,
                blur_score=score,
                threshold_used=0.72,
            )
            for index, score in enumerate((0.40, 0.42, 0.45), start=3)
        ],
    )
    assert_no_alerts(*recovered_other_batches)

    still_active_on_a = evaluate_alerts(
        session_id="session-blur-cross-recovery",
        detector_id="video_blur",
        row=blur_row(
            timestamp_utc="2026-03-31 10:00:06",
            source_group="playlist-a",
            source_name="a-segment-004.ts",
            blur_score=0.90,
            threshold_used=0.72,
        ),
    )

    assert_no_alerts(still_active_on_a)
