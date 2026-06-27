"""Calibration-oriented checks for reviewed representative MP4 windows.

These tests keep detector score shape visible on a few reviewed windows before
threshold policy changes.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from detector_lab.runner import DetectorLabConfig, run_detector_lab
from tests.representative_hls_test_support import (
    representative_expected_case,
    representative_local_file_path,
    require_representative_local_files,
)


pytestmark = pytest.mark.slow


def _rows_by_algorithm(
    *,
    fixture_id: str,
    start_window: int,
    max_windows: int,
    tmp_path: Path,
) -> dict[str, list[dict[str, object]]]:
    """Run detector-lab on one reviewed MP4 window range and group rows."""
    require_representative_local_files(fixture_id)
    fixture_path = representative_local_file_path(fixture_id)
    rows = run_detector_lab(
        DetectorLabConfig(
            input_path=fixture_path,
            mode="video_files",
            output_csv=tmp_path / f"{fixture_id}.csv",
            algorithm_ids=(
                "practical.black_frame_alert_v1",
                "practical.blur_alert_v3",
                "practical.motion_blur_alert_v1",
            ),
            start_window=start_window,
            max_windows=max_windows,
        )
    )

    grouped: dict[str, list[dict[str, object]]] = {}
    for row in rows:
        grouped.setdefault(row["algorithm_id"], []).append(row)
    return grouped


def _assert_black_negative_calibration_window(
    rows: dict[str, list[dict[str, object]]],
    *,
    min_blur_score: float,
    min_motion_score: float,
) -> None:
    """Assert a reviewed calibration window stays black-negative but quality-heavy."""
    black_rows = rows["practical.black_frame_alert_v1"]
    blur_rows = rows["practical.blur_alert_v3"]
    motion_rows = rows["practical.motion_blur_alert_v1"]

    assert all(row["practical_detected"] is False for row in black_rows)
    assert all(float(row["black_ratio"]) == 0.0 for row in black_rows)
    assert all(row["practical_detected"] is False for row in blur_rows)
    assert min(float(row["practical_score"]) for row in blur_rows) >= min_blur_score
    assert all(row["practical_detected"] is True for row in motion_rows)
    assert min(float(row["practical_score"]) for row in motion_rows) >= min_motion_score


def test_representative_compression_windows_show_quality_motion_without_black(
    tmp_path: Path,
) -> None:
    """Compression review windows should stay black-negative while motion scores stay high."""
    rows = _rows_by_algorithm(
        fixture_id="messy_activity__compression_strong_mid_45s",
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
    """Compression-heavy MP4 fixtures should not be promoted into exact blur truth."""
    case = representative_expected_case("messy_activity__compression_strong_mid_45s")

    assert case["expected"]["blur_alert"] == "borderline_or_metric_only"
    assert "exact_ground_truth_case_id" not in case


def test_representative_lowres_windows_stay_black_negative_but_score_as_motion_heavy(
    tmp_path: Path,
) -> None:
    """Low-resolution startup windows should stay black-negative while scores remain elevated."""
    rows = _rows_by_algorithm(
        fixture_id="stable_docs__lowres_moderate_start_30s",
        start_window=0,
        max_windows=8,
        tmp_path=tmp_path,
    )
    _assert_black_negative_calibration_window(
        rows,
        min_blur_score=0.91,
        min_motion_score=0.72,
    )
