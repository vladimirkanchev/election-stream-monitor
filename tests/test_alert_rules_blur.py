"""Stateful blur-rule scenarios for the production ``video_blur`` path."""

import config
import pytest
from alert_rules import evaluate_alerts, reset_session_rule_state

from tests.alert_rules_test_support import assert_no_alerts, blur_row, evaluate_detector_rows


THRESHOLD = config.VIDEO_BLUR_ALERT_THRESHOLD
RECOVERY_THRESHOLD = config.VIDEO_BLUR_RECOVERY_THRESHOLD
AMBIGUOUS_MOTION_THRESHOLD = config.VIDEO_BLUR_MOTION_AMBIGUOUS_MEDIAN_THRESHOLD
HIGH_MOTION_THRESHOLD = config.VIDEO_BLUR_MOTION_GUARD_MEDIAN_THRESHOLD
HIGH_MOTION_PEAK_THRESHOLD = config.VIDEO_BLUR_MOTION_GUARD_PEAK_THRESHOLD
STRICT_MOTION_BLUR_THRESHOLD = config.VIDEO_BLUR_MOTION_AMBIGUOUS_ALERT_THRESHOLD
HIGH_SCORE = round(THRESHOLD + 0.04, 2)
MID_HIGH_SCORE = round(THRESHOLD + 0.01, 2)
BOUNDARY_SCORE = THRESHOLD
LOW_ENTRY_SCORE = round(THRESHOLD - 0.28, 2)
RECOVERY_SCORE = round(RECOVERY_THRESHOLD - 0.23, 2)
VERY_HIGH_SCORE = round(THRESHOLD + 0.12, 2)
REENTRY_SCORES = (HIGH_SCORE, MID_HIGH_SCORE, round(THRESHOLD + 0.02, 2))
WARMUP_SCORES = (RECOVERY_SCORE, RECOVERY_SCORE)


def _with_warmup(
    source_group: str,
    *rows: dict[str, object],
    start_second: int = 0,
) -> list[dict[str, object]]:
    """Prepend quiet warm-up slices so entry tests exercise steady-state rule history."""
    warmup_rows = [
        blur_row(
            timestamp_utc=f"2026-03-31 10:00:{index:02d}",
            source_group=source_group,
            source_name=f"warmup_{index:03d}.ts",
            blur_detected=False,
            blur_score=score,
            threshold_used=THRESHOLD,
        )
        for index, score in enumerate(WARMUP_SCORES, start=start_second)
    ]
    return [*warmup_rows, *rows]


def test_video_blur_rule_raises_alert_for_normalized_blur_score() -> None:
    """Two-above-one-below window should enter after warm-up and full history."""
    reset_session_rule_state("session-blur")
    warmup_a, warmup_b, first, second, third = evaluate_detector_rows(
        session_id="session-blur",
        detector_id="video_blur",
        rows=_with_warmup(
            "playlist-a",
            blur_row(
                timestamp_utc="2026-03-31 10:00:02",
                source_group="playlist-a",
                source_name="segment_001.ts",
                blur_score=HIGH_SCORE,
                threshold_used=THRESHOLD,
            ),
            blur_row(
                timestamp_utc="2026-03-31 10:00:03",
                source_group="playlist-a",
                source_name="segment_002.ts",
                blur_score=MID_HIGH_SCORE,
                threshold_used=THRESHOLD,
            ),
            blur_row(
                timestamp_utc="2026-03-31 10:00:04",
                source_group="playlist-a",
                source_name="segment_003.ts",
                blur_score=LOW_ENTRY_SCORE,
                threshold_used=THRESHOLD,
            ),
        ),
    )

    assert_no_alerts(warmup_a, warmup_b, first, second)
    assert len(third) == 1
    assert "entered a blurry state" in third[0].message
    assert f"2 of 3 slices above the threshold {THRESHOLD}" in third[0].message


def test_video_blur_rule_does_not_alert_before_rolling_window_is_full() -> None:
    """Blur entry should stay quiet until the rolling window is fully populated."""
    reset_session_rule_state("session-blur-short")

    first, second = evaluate_detector_rows(
        session_id="session-blur-short",
        detector_id="video_blur",
        rows=_with_warmup(
            "playlist-short",
            blur_row(
                timestamp_utc="2026-03-31 10:00:02",
                source_group="playlist-short",
                source_name="segment_001.ts",
                blur_score=VERY_HIGH_SCORE,
                threshold_used=THRESHOLD,
            ),
            blur_row(
                timestamp_utc="2026-03-31 10:00:03",
                source_group="playlist-short",
                source_name="segment_002.ts",
                blur_score=VERY_HIGH_SCORE,
                threshold_used=THRESHOLD,
            ),
        )[2:],
    )

    assert_no_alerts(first, second)


def test_video_blur_rule_requires_total_sample_warmup_before_entry() -> None:
    """A full rolling window alone should not alert before total-sample warm-up completes."""
    reset_session_rule_state("session-blur-warmup")

    first, second, third, fourth = evaluate_detector_rows(
        session_id="session-blur-warmup",
        detector_id="video_blur",
        rows=[
            blur_row(
                timestamp_utc="2026-03-31 10:00:00",
                source_group="playlist-warmup",
                source_name="segment_001.ts",
                blur_score=VERY_HIGH_SCORE,
                threshold_used=THRESHOLD,
            ),
            blur_row(
                timestamp_utc="2026-03-31 10:00:01",
                source_group="playlist-warmup",
                source_name="segment_002.ts",
                blur_score=VERY_HIGH_SCORE,
                threshold_used=THRESHOLD,
            ),
            blur_row(
                timestamp_utc="2026-03-31 10:00:02",
                source_group="playlist-warmup",
                source_name="segment_003.ts",
                blur_score=VERY_HIGH_SCORE,
                threshold_used=THRESHOLD,
            ),
            blur_row(
                timestamp_utc="2026-03-31 10:00:03",
                source_group="playlist-warmup",
                source_name="segment_004.ts",
                blur_score=VERY_HIGH_SCORE,
                threshold_used=THRESHOLD,
            ),
        ],
    )

    assert_no_alerts(first, second, third, fourth)


def test_video_blur_rule_suppresses_entry_when_recent_motion_is_high() -> None:
    """High recent motion should suppress blur entry even for a strong blur window."""
    reset_session_rule_state("session-blur-motion-high")

    warmup_a, warmup_b, first, second, third = evaluate_detector_rows(
        session_id="session-blur-motion-high",
        detector_id="video_blur",
        rows=_with_warmup(
            "playlist-motion-high",
            blur_row(
                timestamp_utc="2026-03-31 10:00:02",
                source_group="playlist-motion-high",
                source_name="segment_001.ts",
                blur_score=VERY_HIGH_SCORE,
                motion_mean=round(HIGH_MOTION_THRESHOLD + 0.03, 2),
                motion_p90=round(HIGH_MOTION_PEAK_THRESHOLD + 0.03, 2),
                threshold_used=THRESHOLD,
            ),
            blur_row(
                timestamp_utc="2026-03-31 10:00:03",
                source_group="playlist-motion-high",
                source_name="segment_002.ts",
                blur_score=VERY_HIGH_SCORE,
                motion_mean=round(HIGH_MOTION_THRESHOLD + 0.02, 2),
                motion_p90=round(HIGH_MOTION_PEAK_THRESHOLD + 0.02, 2),
                threshold_used=THRESHOLD,
            ),
            blur_row(
                timestamp_utc="2026-03-31 10:00:04",
                source_group="playlist-motion-high",
                source_name="segment_003.ts",
                blur_score=VERY_HIGH_SCORE,
                motion_mean=round(HIGH_MOTION_THRESHOLD + 0.01, 2),
                motion_p90=round(HIGH_MOTION_PEAK_THRESHOLD + 0.01, 2),
                threshold_used=THRESHOLD,
            ),
        ),
    )

    assert_no_alerts(warmup_a, warmup_b, first, second, third)


@pytest.mark.parametrize(
    ("session_id", "source_group", "motion_mean", "motion_p90"),
    [
        (
            "session-blur-motion-median-boundary",
            "playlist-motion-median-boundary",
            HIGH_MOTION_THRESHOLD,
            round(HIGH_MOTION_PEAK_THRESHOLD - 0.01, 2),
        ),
        (
            "session-blur-motion-peak-boundary",
            "playlist-motion-peak-boundary",
            round(HIGH_MOTION_THRESHOLD - 0.01, 2),
            HIGH_MOTION_PEAK_THRESHOLD,
        ),
    ],
)
def test_video_blur_rule_suppresses_entry_at_exact_high_motion_boundaries(
    session_id: str,
    source_group: str,
    motion_mean: float,
    motion_p90: float,
) -> None:
    """The high-motion guard should apply at both exact median and peak boundaries."""
    reset_session_rule_state(session_id)

    warmup_a, warmup_b, first, second, third = evaluate_detector_rows(
        session_id=session_id,
        detector_id="video_blur",
        rows=_with_warmup(
            source_group,
            blur_row(
                timestamp_utc="2026-03-31 10:00:02",
                source_group=source_group,
                source_name="segment_001.ts",
                blur_score=VERY_HIGH_SCORE,
                motion_mean=motion_mean,
                motion_p90=motion_p90,
                threshold_used=THRESHOLD,
            ),
            blur_row(
                timestamp_utc="2026-03-31 10:00:03",
                source_group=source_group,
                source_name="segment_002.ts",
                blur_score=VERY_HIGH_SCORE,
                motion_mean=motion_mean,
                motion_p90=motion_p90,
                threshold_used=THRESHOLD,
            ),
            blur_row(
                timestamp_utc="2026-03-31 10:00:04",
                source_group=source_group,
                source_name="segment_003.ts",
                blur_score=VERY_HIGH_SCORE,
                motion_mean=motion_mean,
                motion_p90=motion_p90,
                threshold_used=THRESHOLD,
            ),
        ),
    )

    assert_no_alerts(warmup_a, warmup_b, first, second, third)


def test_video_blur_rule_requires_stronger_blur_when_motion_is_ambiguous() -> None:
    """Moderate motion should only allow entry for a fully strong blur window."""
    reset_session_rule_state("session-blur-motion-ambiguous")

    warmup_a, warmup_b, first, second, third = evaluate_detector_rows(
        session_id="session-blur-motion-ambiguous",
        detector_id="video_blur",
        rows=_with_warmup(
            "playlist-motion-ambiguous",
            blur_row(
                timestamp_utc="2026-03-31 10:00:02",
                source_group="playlist-motion-ambiguous",
                source_name="segment_001.ts",
                blur_score=HIGH_SCORE,
                motion_mean=round(AMBIGUOUS_MOTION_THRESHOLD + 0.03, 2),
                threshold_used=THRESHOLD,
            ),
            blur_row(
                timestamp_utc="2026-03-31 10:00:03",
                source_group="playlist-motion-ambiguous",
                source_name="segment_002.ts",
                blur_score=MID_HIGH_SCORE,
                motion_mean=round(AMBIGUOUS_MOTION_THRESHOLD + 0.02, 2),
                threshold_used=THRESHOLD,
            ),
            blur_row(
                timestamp_utc="2026-03-31 10:00:04",
                source_group="playlist-motion-ambiguous",
                source_name="segment_003.ts",
                blur_score=LOW_ENTRY_SCORE,
                motion_mean=round(AMBIGUOUS_MOTION_THRESHOLD + 0.01, 2),
                threshold_used=THRESHOLD,
            ),
        ),
    )

    assert_no_alerts(warmup_a, warmup_b, first, second, third)

    reset_session_rule_state("session-blur-motion-ambiguous-strong")
    warmup_c, warmup_d, fourth, fifth, sixth = evaluate_detector_rows(
        session_id="session-blur-motion-ambiguous-strong",
        detector_id="video_blur",
        rows=_with_warmup(
            "playlist-motion-ambiguous-strong",
            blur_row(
                timestamp_utc="2026-03-31 10:01:02",
                source_group="playlist-motion-ambiguous-strong",
                source_name="segment_101.ts",
                blur_score=round(STRICT_MOTION_BLUR_THRESHOLD + 0.02, 2),
                motion_mean=round(AMBIGUOUS_MOTION_THRESHOLD + 0.03, 2),
                threshold_used=THRESHOLD,
            ),
            blur_row(
                timestamp_utc="2026-03-31 10:01:03",
                source_group="playlist-motion-ambiguous-strong",
                source_name="segment_102.ts",
                blur_score=round(STRICT_MOTION_BLUR_THRESHOLD + 0.01, 2),
                motion_mean=round(AMBIGUOUS_MOTION_THRESHOLD + 0.02, 2),
                threshold_used=THRESHOLD,
            ),
            blur_row(
                timestamp_utc="2026-03-31 10:01:04",
                source_group="playlist-motion-ambiguous-strong",
                source_name="segment_103.ts",
                blur_score=STRICT_MOTION_BLUR_THRESHOLD,
                motion_mean=round(AMBIGUOUS_MOTION_THRESHOLD + 0.01, 2),
                threshold_used=THRESHOLD,
            ),
        ),
    )

    assert_no_alerts(warmup_c, warmup_d, fourth, fifth)
    assert len(sixth) == 1


@pytest.mark.parametrize(
    ("session_id", "source_group", "blur_score", "expected_final_alert_count"),
    [
        (
            "session-blur-motion-ambiguous-boundary",
            "playlist-motion-ambiguous-boundary",
            STRICT_MOTION_BLUR_THRESHOLD,
            1,
        ),
        (
            "session-blur-motion-ambiguous-boundary-no-entry",
            "playlist-motion-ambiguous-boundary-no-entry",
            round(STRICT_MOTION_BLUR_THRESHOLD - 0.01, 2),
            0,
        ),
    ],
)
def test_video_blur_rule_ambiguous_motion_boundary_behavior(
    session_id: str,
    source_group: str,
    blur_score: float,
    expected_final_alert_count: int,
) -> None:
    """At the ambiguous-motion boundary, only the stricter blur threshold should enter."""
    reset_session_rule_state(session_id)

    warmup_a, warmup_b, first, second, third = evaluate_detector_rows(
        session_id=session_id,
        detector_id="video_blur",
        rows=_with_warmup(
            source_group,
            blur_row(
                timestamp_utc="2026-03-31 10:00:02",
                source_group=source_group,
                source_name="segment_001.ts",
                blur_score=blur_score,
                motion_mean=AMBIGUOUS_MOTION_THRESHOLD,
                threshold_used=THRESHOLD,
            ),
            blur_row(
                timestamp_utc="2026-03-31 10:00:03",
                source_group=source_group,
                source_name="segment_002.ts",
                blur_score=blur_score,
                motion_mean=AMBIGUOUS_MOTION_THRESHOLD,
                threshold_used=THRESHOLD,
            ),
            blur_row(
                timestamp_utc="2026-03-31 10:00:04",
                source_group=source_group,
                source_name="segment_003.ts",
                blur_score=blur_score,
                motion_mean=AMBIGUOUS_MOTION_THRESHOLD,
                threshold_used=THRESHOLD,
            ),
        ),
    )

    assert_no_alerts(warmup_a, warmup_b, first, second)
    assert len(third) == expected_final_alert_count


@pytest.mark.parametrize(
    ("session_id", "source_group", "entry_scores", "expected_final_alert_count"),
    [
        (
            "session-blur-boundary",
            "playlist-boundary",
            (BOUNDARY_SCORE, BOUNDARY_SCORE, LOW_ENTRY_SCORE),
            1,
        ),
        (
            "session-blur-below-boundary",
            "playlist-below-boundary",
            (
                round(THRESHOLD - 0.001, 3),
                round(THRESHOLD - 0.001, 3),
                round(THRESHOLD - 0.001, 3),
            ),
            0,
        ),
    ],
)
def test_video_blur_rule_standard_threshold_boundary_behavior(
    session_id: str,
    source_group: str,
    entry_scores: tuple[float, float, float],
    expected_final_alert_count: int,
) -> None:
    """Standard blur entry should stay inclusive at the threshold and fail closed below it."""
    reset_session_rule_state(session_id)

    warmup_a, warmup_b, first, second, third = evaluate_detector_rows(
        session_id=session_id,
        detector_id="video_blur",
        rows=_with_warmup(
            source_group,
            blur_row(
                timestamp_utc="2026-03-31 10:00:02",
                source_group=source_group,
                source_name="segment_001.ts",
                blur_score=entry_scores[0],
                motion_mean=0.0,
                motion_p90=0.0,
                threshold_used=THRESHOLD,
            ),
            blur_row(
                timestamp_utc="2026-03-31 10:00:03",
                source_group=source_group,
                source_name="segment_002.ts",
                blur_score=entry_scores[1],
                motion_mean=0.0,
                motion_p90=0.0,
                threshold_used=THRESHOLD,
            ),
            blur_row(
                timestamp_utc="2026-03-31 10:00:04",
                source_group=source_group,
                source_name="segment_003.ts",
                blur_score=entry_scores[2],
                motion_mean=0.0,
                motion_p90=0.0,
                threshold_used=THRESHOLD,
            ),
        ),
    )

    assert_no_alerts(warmup_a, warmup_b, first, second)
    assert len(third) == expected_final_alert_count


def test_video_blur_rule_does_not_repeat_until_recovery_then_alerts_again() -> None:
    """An active blur episode should suppress duplicates until the window fully recovers."""
    reset_session_rule_state("session-blur-repeat")

    entering_scores = [*WARMUP_SCORES, HIGH_SCORE, MID_HIGH_SCORE, LOW_ENTRY_SCORE]
    entering_alerts = evaluate_detector_rows(
        session_id="session-blur-repeat",
        detector_id="video_blur",
        rows=[
            blur_row(
                timestamp_utc=f"2026-03-31 10:00:{index:02d}",
                source_group="playlist-b",
                source_name=f"segment_00{index + 1}.ts",
                blur_score=score,
                blur_detected=score >= THRESHOLD,
                threshold_used=THRESHOLD,
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
            blur_score=VERY_HIGH_SCORE,
            threshold_used=THRESHOLD,
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
                threshold_used=THRESHOLD,
            )
            for index, score in enumerate((RECOVERY_SCORE, RECOVERY_SCORE, RECOVERY_SCORE), start=5)
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
                threshold_used=THRESHOLD,
            )
            for index, score in enumerate(REENTRY_SCORES, start=8)
        ],
    )
    reenter_alert_counts = [len(alerts) for alerts in reenter_alert_batches]

    assert reenter_alert_counts == [0, 1, 0]


def test_video_blur_rule_recovers_at_exact_recovery_threshold() -> None:
    """A blur episode should recover when the rolling median lands exactly on the recovery threshold."""
    reset_session_rule_state("session-blur-recovery-boundary")

    entered_batches = evaluate_detector_rows(
        session_id="session-blur-recovery-boundary",
        detector_id="video_blur",
        rows=_with_warmup(
            "playlist-recovery-boundary",
            blur_row(
                timestamp_utc="2026-03-31 10:00:02",
                source_group="playlist-recovery-boundary",
                source_name="segment_001.ts",
                blur_score=HIGH_SCORE,
                threshold_used=THRESHOLD,
            ),
            blur_row(
                timestamp_utc="2026-03-31 10:00:03",
                source_group="playlist-recovery-boundary",
                source_name="segment_002.ts",
                blur_score=MID_HIGH_SCORE,
                threshold_used=THRESHOLD,
            ),
            blur_row(
                timestamp_utc="2026-03-31 10:00:04",
                source_group="playlist-recovery-boundary",
                source_name="segment_003.ts",
                blur_score=LOW_ENTRY_SCORE,
                threshold_used=THRESHOLD,
            ),
        ),
    )
    assert len(entered_batches[-1]) == 1

    recovered_batches = evaluate_detector_rows(
        session_id="session-blur-recovery-boundary",
        detector_id="video_blur",
        rows=[
            blur_row(
                timestamp_utc="2026-03-31 10:00:05",
                source_group="playlist-recovery-boundary",
                source_name="segment_004.ts",
                blur_detected=False,
                blur_score=RECOVERY_THRESHOLD,
                threshold_used=THRESHOLD,
            ),
            blur_row(
                timestamp_utc="2026-03-31 10:00:06",
                source_group="playlist-recovery-boundary",
                source_name="segment_005.ts",
                blur_detected=False,
                blur_score=RECOVERY_THRESHOLD,
                threshold_used=THRESHOLD,
            ),
            blur_row(
                timestamp_utc="2026-03-31 10:00:07",
                source_group="playlist-recovery-boundary",
                source_name="segment_006.ts",
                blur_detected=False,
                blur_score=RECOVERY_THRESHOLD,
                threshold_used=THRESHOLD,
            ),
        ],
    )

    assert_no_alerts(*recovered_batches)

    reenter_batches = evaluate_detector_rows(
        session_id="session-blur-recovery-boundary",
        detector_id="video_blur",
        rows=[
            blur_row(
                timestamp_utc="2026-03-31 10:00:08",
                source_group="playlist-recovery-boundary",
                source_name="segment_007.ts",
                blur_score=REENTRY_SCORES[0],
                threshold_used=THRESHOLD,
            ),
            blur_row(
                timestamp_utc="2026-03-31 10:00:09",
                source_group="playlist-recovery-boundary",
                source_name="segment_008.ts",
                blur_score=REENTRY_SCORES[1],
                threshold_used=THRESHOLD,
            ),
            blur_row(
                timestamp_utc="2026-03-31 10:00:10",
                source_group="playlist-recovery-boundary",
                source_name="segment_009.ts",
                blur_score=REENTRY_SCORES[2],
                threshold_used=THRESHOLD,
            ),
        ],
    )

    assert [len(alerts) for alerts in reenter_batches] == [0, 1, 0]


def test_video_blur_rule_does_not_recover_just_above_recovery_threshold() -> None:
    """A blur episode should stay active when the rolling median remains just above recovery."""
    reset_session_rule_state("session-blur-recovery-above")

    entered_batches = evaluate_detector_rows(
        session_id="session-blur-recovery-above",
        detector_id="video_blur",
        rows=_with_warmup(
            "playlist-recovery-above",
            blur_row(
                timestamp_utc="2026-03-31 10:00:02",
                source_group="playlist-recovery-above",
                source_name="segment_001.ts",
                blur_score=HIGH_SCORE,
                threshold_used=THRESHOLD,
            ),
            blur_row(
                timestamp_utc="2026-03-31 10:00:03",
                source_group="playlist-recovery-above",
                source_name="segment_002.ts",
                blur_score=MID_HIGH_SCORE,
                threshold_used=THRESHOLD,
            ),
            blur_row(
                timestamp_utc="2026-03-31 10:00:04",
                source_group="playlist-recovery-above",
                source_name="segment_003.ts",
                blur_score=LOW_ENTRY_SCORE,
                threshold_used=THRESHOLD,
            ),
        ),
    )
    assert len(entered_batches[-1]) == 1

    almost_recovered = evaluate_detector_rows(
        session_id="session-blur-recovery-above",
        detector_id="video_blur",
        rows=[
            blur_row(
                timestamp_utc="2026-03-31 10:00:05",
                source_group="playlist-recovery-above",
                source_name="segment_004.ts",
                blur_detected=False,
                blur_score=round(RECOVERY_THRESHOLD + 0.01, 2),
                threshold_used=THRESHOLD,
            ),
            blur_row(
                timestamp_utc="2026-03-31 10:00:06",
                source_group="playlist-recovery-above",
                source_name="segment_005.ts",
                blur_detected=False,
                blur_score=round(RECOVERY_THRESHOLD + 0.01, 2),
                threshold_used=THRESHOLD,
            ),
            blur_row(
                timestamp_utc="2026-03-31 10:00:07",
                source_group="playlist-recovery-above",
                source_name="segment_006.ts",
                blur_detected=False,
                blur_score=round(RECOVERY_THRESHOLD + 0.01, 2),
                threshold_used=THRESHOLD,
            ),
        ],
    )

    assert_no_alerts(*almost_recovered)

    still_active = evaluate_alerts(
        session_id="session-blur-recovery-above",
        detector_id="video_blur",
        row=blur_row(
            timestamp_utc="2026-03-31 10:00:08",
            source_group="playlist-recovery-above",
            source_name="segment_007.ts",
            blur_score=VERY_HIGH_SCORE,
            threshold_used=THRESHOLD,
        ),
    )

    assert_no_alerts(still_active)


def test_video_blur_rule_emits_separate_alerts_before_and_after_recovery() -> None:
    """A blur episode should ring once, recover, and ring again later in the timeline."""
    reset_session_rule_state("session-blur-separated-alerts")

    first_episode = evaluate_detector_rows(
        session_id="session-blur-separated-alerts",
        detector_id="video_blur",
        rows=_with_warmup(
            "playlist-separated",
            blur_row(
                timestamp_utc="2026-03-31 10:00:02",
                source_group="playlist-separated",
                source_name="segment_001.ts",
                blur_score=HIGH_SCORE,
                threshold_used=THRESHOLD,
            ),
            blur_row(
                timestamp_utc="2026-03-31 10:00:03",
                source_group="playlist-separated",
                source_name="segment_002.ts",
                blur_score=MID_HIGH_SCORE,
                threshold_used=THRESHOLD,
            ),
            blur_row(
                timestamp_utc="2026-03-31 10:00:04",
                source_group="playlist-separated",
                source_name="segment_003.ts",
                blur_score=LOW_ENTRY_SCORE,
                threshold_used=THRESHOLD,
            ),
        ),
    )
    assert_no_alerts(*first_episode[:4])
    assert len(first_episode[4]) == 1
    assert first_episode[4][0].timestamp_utc == "2026-03-31 10:00:04"

    recovery_batches = evaluate_detector_rows(
        session_id="session-blur-separated-alerts",
        detector_id="video_blur",
        rows=[
            blur_row(
                timestamp_utc="2026-03-31 10:00:03",
                source_group="playlist-separated",
                source_name="segment_004.ts",
                blur_detected=False,
                blur_score=RECOVERY_SCORE,
                threshold_used=THRESHOLD,
            ),
            blur_row(
                timestamp_utc="2026-03-31 10:00:04",
                source_group="playlist-separated",
                source_name="segment_005.ts",
                blur_detected=False,
                blur_score=RECOVERY_SCORE,
                threshold_used=THRESHOLD,
            ),
            blur_row(
                timestamp_utc="2026-03-31 10:00:05",
                source_group="playlist-separated",
                source_name="segment_006.ts",
                blur_detected=False,
                blur_score=RECOVERY_SCORE,
                threshold_used=THRESHOLD,
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
                blur_score=HIGH_SCORE,
                threshold_used=THRESHOLD,
            ),
            blur_row(
                timestamp_utc="2026-03-31 10:00:09",
                source_group="playlist-separated",
                source_name="segment_009.ts",
                blur_score=MID_HIGH_SCORE,
                threshold_used=THRESHOLD,
            ),
            blur_row(
                timestamp_utc="2026-03-31 10:00:10",
                source_group="playlist-separated",
                source_name="segment_010.ts",
                blur_score=REENTRY_SCORES[2],
                threshold_used=THRESHOLD,
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
            blur_score=VERY_HIGH_SCORE,
            threshold_used=THRESHOLD,
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
            blur_score=VERY_HIGH_SCORE,
            threshold_used=THRESHOLD,
        ),
    )
    assert_no_alerts(second_session)


def test_video_blur_rule_keeps_rolling_state_isolated_per_source_group() -> None:
    """Interleaved source groups should not contribute to another group's blur window."""
    reset_session_rule_state("session-blur-groups")

    batches = evaluate_detector_rows(
        session_id="session-blur-groups",
        detector_id="video_blur",
        rows=[
            blur_row(
                timestamp_utc="2026-03-31 10:00:00",
                source_group="playlist-a",
                source_name="a-warmup-001.ts",
                blur_detected=False,
                blur_score=RECOVERY_SCORE,
                threshold_used=THRESHOLD,
            ),
            blur_row(
                timestamp_utc="2026-03-31 10:00:01",
                source_group="playlist-a",
                source_name="a-warmup-002.ts",
                blur_detected=False,
                blur_score=RECOVERY_SCORE,
                threshold_used=THRESHOLD,
            ),
            blur_row(
                timestamp_utc="2026-03-31 10:00:02",
                source_group="playlist-b",
                source_name="b-segment-001.ts",
                blur_score=VERY_HIGH_SCORE,
                threshold_used=THRESHOLD,
            ),
            blur_row(
                timestamp_utc="2026-03-31 10:00:03",
                source_group="playlist-a",
                source_name="a-segment-001.ts",
                blur_score=HIGH_SCORE,
                threshold_used=THRESHOLD,
            ),
            blur_row(
                timestamp_utc="2026-03-31 10:00:04",
                source_group="playlist-a",
                source_name="a-segment-002.ts",
                blur_score=MID_HIGH_SCORE,
                threshold_used=THRESHOLD,
            ),
            blur_row(
                timestamp_utc="2026-03-31 10:00:05",
                source_group="playlist-a",
                source_name="a-segment-003.ts",
                blur_score=LOW_ENTRY_SCORE,
                threshold_used=THRESHOLD,
            ),
        ],
    )

    assert_no_alerts(*batches[:5])
    assert len(batches[5]) == 1


def test_video_blur_rule_does_not_recover_from_other_source_groups() -> None:
    """Recovery on one source group should not clear an active blur state on another."""
    reset_session_rule_state("session-blur-cross-recovery")

    entered_batches = evaluate_detector_rows(
        session_id="session-blur-cross-recovery",
        detector_id="video_blur",
        rows=_with_warmup(
            "playlist-a",
            *[
                blur_row(
                    timestamp_utc=f"2026-03-31 10:00:0{index}",
                    source_group="playlist-a",
                    source_name=f"a-segment-00{index + 1}.ts",
                    blur_score=score,
                    threshold_used=THRESHOLD,
                )
                for index, score in enumerate((HIGH_SCORE, MID_HIGH_SCORE, LOW_ENTRY_SCORE), start=2)
            ],
        ),
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
                threshold_used=THRESHOLD,
            )
            for index, score in enumerate((RECOVERY_SCORE, RECOVERY_SCORE, RECOVERY_SCORE), start=3)
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
            blur_score=VERY_HIGH_SCORE,
            threshold_used=THRESHOLD,
        ),
    )

    assert_no_alerts(still_active_on_a)


def test_video_blur_rule_suppresses_entry_when_only_motion_median_crosses_guard() -> None:
    """High motion median alone should suppress blur entry even when motion peak stays lower."""
    reset_session_rule_state("session-blur-motion-median-only")

    warmup_a, warmup_b, first, second, third = evaluate_detector_rows(
        session_id="session-blur-motion-median-only",
        detector_id="video_blur",
        rows=_with_warmup(
            "playlist-motion-median-only",
            blur_row(
                timestamp_utc="2026-03-31 10:00:02",
                source_group="playlist-motion-median-only",
                source_name="segment_001.ts",
                blur_score=VERY_HIGH_SCORE,
                motion_mean=HIGH_MOTION_THRESHOLD,
                motion_p90=round(HIGH_MOTION_PEAK_THRESHOLD - 0.02, 2),
                threshold_used=THRESHOLD,
            ),
            blur_row(
                timestamp_utc="2026-03-31 10:00:03",
                source_group="playlist-motion-median-only",
                source_name="segment_002.ts",
                blur_score=VERY_HIGH_SCORE,
                motion_mean=HIGH_MOTION_THRESHOLD,
                motion_p90=round(HIGH_MOTION_PEAK_THRESHOLD - 0.02, 2),
                threshold_used=THRESHOLD,
            ),
            blur_row(
                timestamp_utc="2026-03-31 10:00:04",
                source_group="playlist-motion-median-only",
                source_name="segment_003.ts",
                blur_score=VERY_HIGH_SCORE,
                motion_mean=HIGH_MOTION_THRESHOLD,
                motion_p90=round(HIGH_MOTION_PEAK_THRESHOLD - 0.02, 2),
                threshold_used=THRESHOLD,
            ),
        ),
    )

    assert_no_alerts(warmup_a, warmup_b, first, second, third)


def test_video_blur_rule_suppresses_entry_when_only_motion_peak_crosses_guard() -> None:
    """High motion peak alone should suppress blur entry even when motion median stays lower."""
    reset_session_rule_state("session-blur-motion-peak-only")

    warmup_a, warmup_b, first, second, third = evaluate_detector_rows(
        session_id="session-blur-motion-peak-only",
        detector_id="video_blur",
        rows=_with_warmup(
            "playlist-motion-peak-only",
            blur_row(
                timestamp_utc="2026-03-31 10:00:02",
                source_group="playlist-motion-peak-only",
                source_name="segment_001.ts",
                blur_score=VERY_HIGH_SCORE,
                motion_mean=round(HIGH_MOTION_THRESHOLD - 0.02, 2),
                motion_p90=HIGH_MOTION_PEAK_THRESHOLD,
                threshold_used=THRESHOLD,
            ),
            blur_row(
                timestamp_utc="2026-03-31 10:00:03",
                source_group="playlist-motion-peak-only",
                source_name="segment_002.ts",
                blur_score=VERY_HIGH_SCORE,
                motion_mean=round(HIGH_MOTION_THRESHOLD - 0.02, 2),
                motion_p90=HIGH_MOTION_PEAK_THRESHOLD,
                threshold_used=THRESHOLD,
            ),
            blur_row(
                timestamp_utc="2026-03-31 10:00:04",
                source_group="playlist-motion-peak-only",
                source_name="segment_003.ts",
                blur_score=VERY_HIGH_SCORE,
                motion_mean=round(HIGH_MOTION_THRESHOLD - 0.02, 2),
                motion_p90=HIGH_MOTION_PEAK_THRESHOLD,
                threshold_used=THRESHOLD,
            ),
        ),
    )

    assert_no_alerts(warmup_a, warmup_b, first, second, third)
