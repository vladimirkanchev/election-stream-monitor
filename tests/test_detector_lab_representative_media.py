"""Detector-lab checks for reviewed representative MP4 windows.

These tests keep a small, human-reviewed set of representative MP4 windows
visible in calibration mode. They protect broad detector behavior, catalog
boundaries, and promotion rules without pretending that every quality issue
already has exact ground truth.
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
LOWRES_HLS_FIXTURE_ID = "stable_docs__lowres_moderate_start_30s_hls"
LOWRES_HLS_SOURCE_MP4_PATH = (
    "local_files/low_resolution/stable_docs__lowres_moderate_start_30s.mp4"
)
LOWRES_STRONG_END_FIXTURE_ID = "stable_docs__lowres_strong_end_30s"
LOWRES_STRONG_END_START_WINDOW = 270
LOWRES_SCORE_SHIFT_FIXTURE_ID = "wide_observer__lowres_strong_mid_45s"
LOWRES_SCORE_SHIFT_LEAD_IN_START_WINDOW = 119
LOWRES_SCORE_SHIFT_CORE_START_WINDOW = 127
LOWRES_SCORE_SHIFT_RECOVERY_START_WINDOW = 180
LOWRES_SCORE_SHIFT_WINDOW_COUNT = 8
MIN_LOWRES_LEAD_IN_TO_CORE_SCORE_DELTA = 0.12
MIN_LOWRES_RECOVERY_TO_CORE_SCORE_DELTA = 0.15
LOWRES_BLACK_NEGATIVE_WINDOW_COUNT = 8
LOWRES_PROMOTED_MP4_EXACT_CASE_ID = (
    "representative_mp4_stable_docs_lowres_blur_video_blur"
)
LOWRES_HLS_BLACK_GUARD_EXACT_CASE_ID = (
    "representative_hls_stable_docs_lowres_black_guard_video_metrics"
)
LOWRES_SOURCE_FAMILY_MATRIX = (
    pytest.param("stable_docs__lowres_strong_end_30s", 270, id="stable-docs-strong-end"),
    pytest.param("close_review__lowres_strong_end_30s", 270, id="close-review-strong-end"),
    pytest.param("wide_observer__lowres_strong_mid_45s", 127, id="wide-observer-strong-mid"),
)
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
    """Run detector-lab for one reviewed MP4 slice and group results by algorithm."""
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
    """Return representative-catalog metadata for one local MP4 fixture."""
    return representative_expected_case(fixture_id)


def _repeated_compression_case() -> dict[str, object]:
    """Return catalog metadata for the repeated-compression calibration fixture."""
    return _case(REPEATED_COMPRESSION_FIXTURE_ID)


def _repeated_compression_rows(
    *,
    start_window: int,
    max_windows: int,
    tmp_path: Path,
    algorithm_ids: tuple[str, ...],
) -> dict[str, list[dict[str, object]]]:
    """Run detector-lab for one reviewed slice of the repeated-compression fixture."""
    return _rows_by_algorithm(
        fixture_id=REPEATED_COMPRESSION_FIXTURE_ID,
        start_window=start_window,
        max_windows=max_windows,
        tmp_path=tmp_path,
        algorithm_ids=algorithm_ids,
    )


def _practical_scores(rows: list[dict[str, object]]) -> list[float]:
    """Return practical scores as floats for one detector result set."""
    assert rows
    return [float(row["practical_score"]) for row in rows]


def _assert_black_negative_calibration_window(
    rows: dict[str, list[dict[str, object]]],
    *,
    min_blur_score: float,
    min_motion_score: float,
) -> None:
    """Assert a reviewed slice stays black-negative while quality signals stay visible."""
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
    """Assert a reviewed slice never looks like a black-frame outage."""
    black_rows = rows[BLACK_FRAME_ALERT]

    assert black_rows
    assert all(row["practical_detected"] is False for row in black_rows)
    assert all(float(row["black_ratio"]) == 0.0 for row in black_rows)


def _assert_blur_scores_stay_calibration_only(
    rows: dict[str, list[dict[str, object]]],
    *,
    min_score_movement: float,
) -> None:
    """Assert blur scores move enough to remain useful as calibration evidence."""
    blur_rows = rows[BLUR_ALERT]
    scores = _practical_scores(blur_rows)

    assert blur_rows
    assert all(row["practical_detected"] is False for row in blur_rows)
    assert max(scores) - min(scores) >= min_score_movement


def _blur_score_profile(rows: dict[str, list[dict[str, object]]]) -> dict[str, float]:
    """Summarize blur-score shape for repeated-burst comparison."""
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
    """Assert repeated compression bursts keep a similar broad blur-score shape."""
    mean_scores = [profile["mean"] for profile in profiles]
    score_ranges = [profile["range"] for profile in profiles]

    assert max(mean_scores) - min(mean_scores) <= MAX_REPEATED_COMPRESSION_MEAN_DELTA
    assert max(score_ranges) - min(score_ranges) <= MAX_REPEATED_COMPRESSION_RANGE_DELTA


def _mean_practical_score(rows: list[dict[str, object]]) -> float:
    """Return the mean detector score for one contiguous reviewed slice."""
    return fmean(_practical_scores(rows))


def _assert_repeated_compression_stays_review_only(case: dict[str, object]) -> None:
    """Assert repeated compression stays review-only and is not promoted to exact truth."""
    assert case["artifact_type"] == "compression_noise"
    _assert_review_only_quality_degradation_case(case)


def _assert_review_only_quality_degradation_case(case: dict[str, object]) -> None:
    """Assert metadata stays calibration-oriented instead of claiming exact runtime truth."""
    assert case["assertion_tier"] == "future_quality_degradation"
    assert case["expected"]["black_screen_alert"] == "not_expected"
    assert case["expected"]["blur_alert"] == "borderline_or_metric_only"
    assert case["expected"]["quality_degradation"] == "expected"
    assert "exact_ground_truth_case_id" not in case


def _assert_lowres_stays_calibration_only(case: dict[str, object]) -> None:
    """Assert a low-resolution case stays review-only until explicit promotion."""
    assert case["artifact_type"] == "low_resolution"
    _assert_review_only_quality_degradation_case(case)


def _assert_lowres_promoted_mp4_truth(case: dict[str, object]) -> None:
    """Assert the reviewed MP4 low-res positive case is promoted explicitly."""
    assert case["artifact_type"] == "low_resolution"
    assert case["assertion_tier"] == "current_positive_blur"
    assert case["expected"]["black_screen_alert"] == "not_expected"
    assert case["expected"]["blur_alert"] == "expected"
    assert case["expected"]["quality_degradation"] == "expected"
    assert case["exact_ground_truth_case_id"] == LOWRES_PROMOTED_MP4_EXACT_CASE_ID


def _assert_lowres_review_only_hls_black_guard(case: dict[str, object]) -> None:
    """Assert low-res HLS metadata keeps blur review-only while preserving black truth."""
    assert case["assertion_tier"] == "future_quality_degradation"
    assert case["source_mp4_path"] == LOWRES_HLS_SOURCE_MP4_PATH
    assert case["expected"]["black_screen_alert"] == "not_expected"
    assert case["expected"]["blur_alert"] == "borderline_or_metric_only"
    assert case["expected"]["quality_degradation"] == "expected"
    assert case["exact_ground_truth_case_id"] == LOWRES_HLS_BLACK_GUARD_EXACT_CASE_ID


def _assert_black_negative_expected(case: dict[str, object]) -> None:
    """Assert the catalog expects no black-screen alert for the reviewed slice."""
    assert case["expected"]["black_screen_alert"] == "not_expected"


def _lowres_black_negative_rows(
    *,
    fixture_id: str,
    start_window: int,
    tmp_path: Path,
) -> dict[str, list[dict[str, object]]]:
    """Run only the black-frame detector over one reviewed low-resolution slice."""
    return _rows_by_algorithm(
        fixture_id=fixture_id,
        start_window=start_window,
        max_windows=LOWRES_BLACK_NEGATIVE_WINDOW_COUNT,
        tmp_path=tmp_path,
        algorithm_ids=(BLACK_FRAME_ALERT,),
    )


def test_representative_compression_windows_show_quality_motion_without_black(
    tmp_path: Path,
) -> None:
    """Compression slices should stay black-negative while quality degradation stays visible."""
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


def test_representative_lowres_moderate_start_stays_black_negative(
    tmp_path: Path,
) -> None:
    """Low-res startup should stay outside black-screen alert territory."""
    case = _case(LOWRES_FIXTURE_ID)
    rows = _lowres_black_negative_rows(
        fixture_id=LOWRES_FIXTURE_ID,
        start_window=0,
        tmp_path=tmp_path,
    )

    _assert_black_negative_expected(case)
    _assert_black_frame_algorithm_stays_negative(rows)


def test_representative_lowres_strong_end_stays_black_negative(
    tmp_path: Path,
) -> None:
    """Severe low-res collapse should stay outside black-screen alert territory."""
    case = _case(LOWRES_STRONG_END_FIXTURE_ID)
    rows = _lowres_black_negative_rows(
        fixture_id=LOWRES_STRONG_END_FIXTURE_ID,
        start_window=LOWRES_STRONG_END_START_WINDOW,
        tmp_path=tmp_path,
    )

    _assert_black_negative_expected(case)
    _assert_black_frame_algorithm_stays_negative(rows)


def test_representative_lowres_blur_boundary_remains_calibration_only() -> None:
    """Strong low-resolution cases should stay outside exact blur truth until reviewed."""
    _assert_lowres_stays_calibration_only(_case(LOWRES_STRONG_END_FIXTURE_ID))


def test_representative_lowres_metadata_does_not_silently_promote_exact_truth() -> None:
    """Low-res exact truth should stay explicit and review-backed in metadata."""
    promoted_mp4_case = _case(LOWRES_FIXTURE_ID)
    review_only_mp4_case = _case(LOWRES_STRONG_END_FIXTURE_ID)
    review_only_hls_case = _case(LOWRES_HLS_FIXTURE_ID)

    _assert_lowres_promoted_mp4_truth(promoted_mp4_case)
    _assert_lowres_stays_calibration_only(review_only_mp4_case)
    _assert_lowres_review_only_hls_black_guard(review_only_hls_case)


@pytest.mark.parametrize(
    ("fixture_id", "start_window"),
    LOWRES_SOURCE_FAMILY_MATRIX,
)
def test_representative_lowres_source_family_matrix_stays_black_negative(
    fixture_id: str,
    start_window: int,
    tmp_path: Path,
) -> None:
    """Low-res black-negative behavior should hold across source families."""
    case = _case(fixture_id)
    rows = _lowres_black_negative_rows(
        fixture_id=fixture_id,
        start_window=start_window,
        tmp_path=tmp_path,
    )

    assert case["artifact_type"] == "low_resolution"
    _assert_black_negative_expected(case)
    assert case["expected"]["quality_degradation"] == "expected"
    _assert_black_frame_algorithm_stays_negative(rows)


def test_representative_lowres_lead_in_vs_core_score_shift(
    tmp_path: Path,
) -> None:
    """Low-res slices should shift detector scores relative to normal lead-in and recovery."""
    case = _case(LOWRES_SCORE_SHIFT_FIXTURE_ID)
    lead_in_rows = _rows_by_algorithm(
        fixture_id=LOWRES_SCORE_SHIFT_FIXTURE_ID,
        start_window=LOWRES_SCORE_SHIFT_LEAD_IN_START_WINDOW,
        max_windows=LOWRES_SCORE_SHIFT_WINDOW_COUNT,
        tmp_path=tmp_path,
        algorithm_ids=(MOTION_BLUR_ALERT,),
    )[MOTION_BLUR_ALERT]
    core_rows = _rows_by_algorithm(
        fixture_id=LOWRES_SCORE_SHIFT_FIXTURE_ID,
        start_window=LOWRES_SCORE_SHIFT_CORE_START_WINDOW,
        max_windows=LOWRES_SCORE_SHIFT_WINDOW_COUNT,
        tmp_path=tmp_path,
        algorithm_ids=(MOTION_BLUR_ALERT,),
    )[MOTION_BLUR_ALERT]
    recovery_rows = _rows_by_algorithm(
        fixture_id=LOWRES_SCORE_SHIFT_FIXTURE_ID,
        start_window=LOWRES_SCORE_SHIFT_RECOVERY_START_WINDOW,
        max_windows=LOWRES_SCORE_SHIFT_WINDOW_COUNT,
        tmp_path=tmp_path,
        algorithm_ids=(MOTION_BLUR_ALERT,),
    )[MOTION_BLUR_ALERT]

    _assert_lowres_stays_calibration_only(case)
    assert (
        _mean_practical_score(lead_in_rows) - _mean_practical_score(core_rows)
        >= MIN_LOWRES_LEAD_IN_TO_CORE_SCORE_DELTA
    )
    assert (
        _mean_practical_score(recovery_rows) - _mean_practical_score(core_rows)
        >= MIN_LOWRES_RECOVERY_TO_CORE_SCORE_DELTA
    )


def test_representative_lowres_windows_stay_black_negative_but_score_as_motion_heavy(
    tmp_path: Path,
) -> None:
    """Low-res startup slices should stay black-negative while quality scores rise."""
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
