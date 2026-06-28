"""Detector-lab checks for reviewed representative MP4 windows.

This module keeps a small set of representative windows visible in calibration
mode. The goal is to protect broad detector behavior and metadata boundaries
without promoting borderline media into fake exact truth.
"""

from __future__ import annotations

from pathlib import Path
from statistics import fmean

import pytest

from detector_lab.runner import DetectorLabConfig, run_detector_lab
from tests.representative_hls_test_support import (
    representative_expected_case,
    representative_local_file_path,
    require_representative_local_files,
)


pytestmark = pytest.mark.slow

BLACK_FRAME_ALERT = "practical.black_frame_alert_v1"
BLUR_ALERT = "practical.blur_alert_v3"
MOTION_BLUR_ALERT = "practical.motion_blur_alert_v1"
MESSY_ACTIVITY_COMPRESSION_FIXTURE_ID = "messy_activity__compression_strong_mid_45s"
REPEATED_COMPRESSION_FIXTURE_ID = "crowded_ballot__compression_strong_repeated_3x20s"
LOWRES_FIXTURE_ID = "stable_docs__lowres_moderate_start_30s"
CROWDED_BALLOT_REPEATED_COMPRESSION_BURSTS = (
    pytest.param(60, id="first-burst"),
    pytest.param(140, id="second-burst"),
    pytest.param(220, id="third-burst"),
)
REPEATED_COMPRESSION_PROFILE_START_WINDOWS = (52, 132, 212)
CROWDED_BALLOT_REPEATED_COMPRESSION_PROFILE_WINDOWS = (
    pytest.param(52, id="first-burst-profile"),
    pytest.param(132, id="second-burst-profile"),
    pytest.param(212, id="third-burst-profile"),
)
REPEATED_COMPRESSION_PROFILE_WINDOW_COUNT = 36
MAX_REPEATED_COMPRESSION_MEAN_DELTA = 0.02
MAX_REPEATED_COMPRESSION_RANGE_DELTA = 0.01
LEAD_IN_VS_COMPRESSION_CORE_START_WINDOW = 52
LEAD_IN_WINDOW_COUNT = 8
COMPRESSION_CORE_WINDOW_COUNT = 20
MIN_LEAD_IN_TO_CORE_MOTION_SCORE_DELTA = 0.15


def _rows_by_algorithm(
    *,
    fixture_id: str,
    start_window: int,
    max_windows: int,
    tmp_path: Path,
    algorithm_ids: tuple[str, ...] = (
        BLACK_FRAME_ALERT,
        BLUR_ALERT,
        MOTION_BLUR_ALERT,
    ),
) -> dict[str, list[dict[str, object]]]:
    """Run detector-lab for one reviewed MP4 range and group rows by algorithm."""
    require_representative_local_files(fixture_id)
    fixture_path = representative_local_file_path(fixture_id)
    rows = run_detector_lab(
        DetectorLabConfig(
            input_path=fixture_path,
            mode="video_files",
            output_csv=tmp_path / f"{fixture_id}.csv",
            algorithm_ids=algorithm_ids,
            start_window=start_window,
            max_windows=max_windows,
        )
    )

    grouped: dict[str, list[dict[str, object]]] = {}
    for row in rows:
        grouped.setdefault(row["algorithm_id"], []).append(row)
    return grouped


def _case(fixture_id: str) -> dict[str, object]:
    """Return catalog metadata for one representative local MP4 fixture."""
    return representative_expected_case(fixture_id)


def _repeated_compression_case() -> dict[str, object]:
    """Return catalog metadata for the repeated compression calibration fixture."""
    return _case(REPEATED_COMPRESSION_FIXTURE_ID)


def _repeated_compression_rows(
    *,
    start_window: int,
    max_windows: int,
    tmp_path: Path,
    algorithm_ids: tuple[str, ...],
) -> dict[str, list[dict[str, object]]]:
    """Run detector-lab for the repeated compression fixture over one window range."""
    return _rows_by_algorithm(
        fixture_id=REPEATED_COMPRESSION_FIXTURE_ID,
        start_window=start_window,
        max_windows=max_windows,
        tmp_path=tmp_path,
        algorithm_ids=algorithm_ids,
    )


def _practical_scores(rows: list[dict[str, object]]) -> list[float]:
    """Return detector scores as floats for one algorithm result set."""
    assert rows
    return [float(row["practical_score"]) for row in rows]


def _assert_black_negative_calibration_window(
    rows: dict[str, list[dict[str, object]]],
    *,
    min_blur_score: float,
    min_motion_score: float,
) -> None:
    """Assert a reviewed window stays black-negative while quality signals remain elevated."""
    black_rows = rows[BLACK_FRAME_ALERT]
    blur_rows = rows[BLUR_ALERT]
    motion_rows = rows[MOTION_BLUR_ALERT]

    assert all(row["practical_detected"] is False for row in black_rows)
    assert all(float(row["black_ratio"]) == 0.0 for row in black_rows)
    assert all(row["practical_detected"] is False for row in blur_rows)
    assert min(_practical_scores(blur_rows)) >= min_blur_score
    assert all(row["practical_detected"] is True for row in motion_rows)
    assert min(_practical_scores(motion_rows)) >= min_motion_score


def _assert_black_frame_algorithm_stays_negative(
    rows: dict[str, list[dict[str, object]]],
) -> None:
    """Assert the reviewed window never looks like a black-frame outage."""
    black_rows = rows[BLACK_FRAME_ALERT]

    assert black_rows
    assert all(row["practical_detected"] is False for row in black_rows)
    assert all(float(row["black_ratio"]) == 0.0 for row in black_rows)


def _assert_blur_scores_stay_calibration_only(
    rows: dict[str, list[dict[str, object]]],
    *,
    min_score_movement: float,
) -> None:
    """Assert blur scores move enough to stay useful for calibration only."""
    blur_rows = rows[BLUR_ALERT]
    scores = _practical_scores(blur_rows)

    assert blur_rows
    assert all(row["practical_detected"] is False for row in blur_rows)
    assert max(scores) - min(scores) >= min_score_movement


def _blur_score_profile(rows: dict[str, list[dict[str, object]]]) -> dict[str, float]:
    """Summarize blur score shape for repeated-burst comparison."""
    blur_rows = rows[BLUR_ALERT]
    scores = _practical_scores(blur_rows)

    assert blur_rows
    assert all(row["practical_detected"] is False for row in blur_rows)
    return {
        "mean": fmean(scores),
        "range": max(scores) - min(scores),
    }


def _assert_repeated_burst_profiles_are_similar(
    profiles: list[dict[str, float]],
) -> None:
    """Assert repeated compression bursts keep a similar broad blur-score profile."""
    mean_scores = [profile["mean"] for profile in profiles]
    score_ranges = [profile["range"] for profile in profiles]

    assert max(mean_scores) - min(mean_scores) <= MAX_REPEATED_COMPRESSION_MEAN_DELTA
    assert max(score_ranges) - min(score_ranges) <= MAX_REPEATED_COMPRESSION_RANGE_DELTA


def _mean_practical_score(rows: list[dict[str, object]]) -> float:
    """Return the mean detector score for one contiguous reviewed region."""
    return fmean(_practical_scores(rows))


def _assert_repeated_compression_stays_review_only(case: dict[str, object]) -> None:
    """Assert repeated compression stays review-only and is not promoted to exact truth."""
    assert case["artifact_type"] == "compression_noise"
    assert case["assertion_tier"] == "future_quality_degradation"
    assert case["expected"]["black_screen_alert"] == "not_expected"
    assert case["expected"]["blur_alert"] == "borderline_or_metric_only"
    assert case["expected"]["quality_degradation"] == "expected"
    assert "exact_ground_truth_case_id" not in case


def test_representative_compression_windows_show_quality_motion_without_black(
    tmp_path: Path,
) -> None:
    """Compression windows should stay black-negative while quality degradation stays visible."""
    rows = _rows_by_algorithm(
        fixture_id=MESSY_ACTIVITY_COMPRESSION_FIXTURE_ID,
        start_window=106,
        max_windows=8,
        tmp_path=tmp_path,
    )
    _assert_black_negative_calibration_window(
        rows,
        min_blur_score=0.91,
        min_motion_score=0.71,
    )


def test_representative_compression_mp4_stays_out_of_exact_blur_truth() -> None:
    """Compression-heavy MP4 fixtures should remain outside exact blur truth."""
    case = _case(MESSY_ACTIVITY_COMPRESSION_FIXTURE_ID)

    assert case["expected"]["blur_alert"] == "borderline_or_metric_only"
    assert "exact_ground_truth_case_id" not in case


@pytest.mark.parametrize("start_window", CROWDED_BALLOT_REPEATED_COMPRESSION_BURSTS)
def test_representative_repeated_compression_bursts_do_not_fake_black(
    start_window: int,
    tmp_path: Path,
) -> None:
    """Repeated compression bursts should remain black-negative in detector-lab."""
    case = _repeated_compression_case()
    rows = _repeated_compression_rows(
        start_window=start_window,
        max_windows=8,
        tmp_path=tmp_path,
        algorithm_ids=(BLACK_FRAME_ALERT,),
    )

    _assert_repeated_compression_stays_review_only(case)
    _assert_black_frame_algorithm_stays_negative(rows)


@pytest.mark.parametrize(
    "start_window",
    CROWDED_BALLOT_REPEATED_COMPRESSION_PROFILE_WINDOWS,
)
def test_representative_repeated_compression_blur_scores_remain_calibration_only(
    start_window: int,
    tmp_path: Path,
) -> None:
    """Compression blur scores should move without becoming exact blur truth."""
    case = _repeated_compression_case()
    rows = _repeated_compression_rows(
        start_window=start_window,
        max_windows=REPEATED_COMPRESSION_PROFILE_WINDOW_COUNT,
        tmp_path=tmp_path,
        algorithm_ids=(BLUR_ALERT,),
    )

    _assert_repeated_compression_stays_review_only(case)
    _assert_blur_scores_stay_calibration_only(rows, min_score_movement=0.01)


def test_representative_repeated_compression_bursts_keep_similar_blur_profiles(
    tmp_path: Path,
) -> None:
    """Repeated compression bursts should keep similar blur-score profiles."""
    case = _repeated_compression_case()
    profiles = [
        _blur_score_profile(
            _repeated_compression_rows(
                start_window=start_window,
                max_windows=REPEATED_COMPRESSION_PROFILE_WINDOW_COUNT,
                tmp_path=tmp_path,
                algorithm_ids=(BLUR_ALERT,),
            )
        )
        for start_window in REPEATED_COMPRESSION_PROFILE_START_WINDOWS
    ]

    _assert_repeated_compression_stays_review_only(case)
    _assert_repeated_burst_profiles_are_similar(profiles)


def test_representative_repeated_compression_alerts_stay_unpromoted_until_reviewed() -> None:
    """Compression metadata should stay review-only until a later promotion decision."""
    _assert_repeated_compression_stays_review_only(_repeated_compression_case())


def test_representative_compression_core_scores_differ_from_cleanish_lead_in(
    tmp_path: Path,
) -> None:
    """Lead-in and compression-core windows should remain score-distinguishable."""
    case = _repeated_compression_case()
    rows = _repeated_compression_rows(
        start_window=LEAD_IN_VS_COMPRESSION_CORE_START_WINDOW,
        max_windows=LEAD_IN_WINDOW_COUNT + COMPRESSION_CORE_WINDOW_COUNT,
        tmp_path=tmp_path,
        algorithm_ids=(MOTION_BLUR_ALERT,),
    )[MOTION_BLUR_ALERT]
    lead_in_rows = rows[:LEAD_IN_WINDOW_COUNT]
    compression_core_rows = rows[LEAD_IN_WINDOW_COUNT:]

    _assert_repeated_compression_stays_review_only(case)
    assert (
        _mean_practical_score(lead_in_rows)
        - _mean_practical_score(compression_core_rows)
        >= MIN_LEAD_IN_TO_CORE_MOTION_SCORE_DELTA
    )


def test_representative_lowres_windows_stay_black_negative_but_score_as_motion_heavy(
    tmp_path: Path,
) -> None:
    """Low-resolution startup windows should stay black-negative while quality scores rise."""
    rows = _rows_by_algorithm(
        fixture_id=LOWRES_FIXTURE_ID,
        start_window=0,
        max_windows=8,
        tmp_path=tmp_path,
    )
    _assert_black_negative_calibration_window(
        rows,
        min_blur_score=0.91,
        min_motion_score=0.72,
    )
