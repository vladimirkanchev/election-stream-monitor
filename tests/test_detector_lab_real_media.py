"""Slow real-media confidence checks for detector-lab blur and motion behavior.

These tests intentionally run on checked-in media fixtures. They are valuable
for confidence and calibration, but they are not part of the fast inner-loop
detector/rule feedback lane.
"""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from detector_lab.runner import DetectorLabConfig, run_detector_lab


pytestmark = pytest.mark.slow


def _fixture_media_path(relative_path: str) -> Path:
    """Resolve one checked-in detector-lab media fixture by relative path."""
    return Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "media" / relative_path


def test_real_fixture_practical_motion_blur_detects_labeled_core_windows(tmp_path: Path) -> None:
    """The practical motion-blur lane should fire on the labeled motion-blur core of the short trigger fixture."""
    fixture_path = _fixture_media_path("video_files/blur_trigger.mp4")

    rows = run_detector_lab(
        DetectorLabConfig(
            input_path=fixture_path,
            mode="video_files",
            output_csv=tmp_path / "blur_trigger_motion.csv",
            algorithm_ids=("practical.motion_blur_alert_v1",),
            max_windows=5,
        )
    )
    rows_by_window = {int(row["window_index"]): row for row in rows}

    assert rows_by_window[2]["practical_detected"] is True
    assert rows_by_window[2]["guardrail_reason"] == ""
    assert rows_by_window[3]["practical_detected"] is True
    assert rows_by_window[3]["guardrail_reason"] == ""
    assert rows_by_window[4]["practical_detected"] is False
    assert rows_by_window[4]["guardrail_reason"] == "softness_too_low"


def test_real_fixture_motion_blur_stays_suppressed_during_black_transition_windows(
    tmp_path: Path,
) -> None:
    """The practical motion-blur lane should stay suppressed through the black-transition-heavy part of the recovery fixture."""
    fixture_path = _fixture_media_path("video_files/black_recovery_realert_long.mp4")

    rows = run_detector_lab(
        DetectorLabConfig(
            input_path=fixture_path,
            mode="video_files",
            output_csv=tmp_path / "black_recovery_motion.csv",
            algorithm_ids=("practical.motion_blur_alert_v1",),
            max_windows=8,
        )
    )
    rows_by_window = {int(row["window_index"]): row for row in rows}

    for window_index in (0, 3, 4, 7):
        assert rows_by_window[window_index]["practical_detected"] is False
        assert rows_by_window[window_index]["guardrail_reason"] == "black_transition_motion"

    for window_index in (1, 2, 5, 6):
        assert rows_by_window[window_index]["practical_detected"] is False
        assert rows_by_window[window_index]["guardrail_reason"] == "black_dominant"


def test_real_fixture_practical_lane_precedence_matches_current_guardrails(
    tmp_path: Path,
) -> None:
    """Real fixtures should show black owning black windows and motion blur owning the clearest motion-preferred blur window."""
    black_fixture = _fixture_media_path("video_files/black_recovery_realert_long.mp4")
    blur_fixture = _fixture_media_path("video_files/blur_trigger.mp4")

    black_rows = run_detector_lab(
        DetectorLabConfig(
            input_path=black_fixture,
            mode="video_files",
            output_csv=tmp_path / "black_precedence.csv",
            algorithm_ids=(
                "practical.black_frame_alert_v1",
                "practical.blur_alert_v3",
                "practical.motion_blur_alert_v1",
            ),
            max_windows=3,
        )
    )
    black_by_key = {
        (row["algorithm_id"], int(row["window_index"])): row for row in black_rows
    }

    assert black_by_key[("practical.black_frame_alert_v1", 1)]["practical_detected"] is True
    assert black_by_key[("practical.blur_alert_v3", 1)]["practical_detected"] is False
    assert black_by_key[("practical.blur_alert_v3", 1)]["guardrail_reason"] == "black_dominant"
    assert black_by_key[("practical.motion_blur_alert_v1", 1)]["practical_detected"] is False
    assert (
        black_by_key[("practical.motion_blur_alert_v1", 1)]["guardrail_reason"]
        == "black_dominant"
    )

    blur_rows = run_detector_lab(
        DetectorLabConfig(
            input_path=blur_fixture,
            mode="video_files",
            output_csv=tmp_path / "blur_precedence.csv",
            algorithm_ids=(
                "practical.blur_alert_v3",
                "practical.motion_blur_alert_v1",
            ),
            max_windows=3,
        )
    )
    blur_by_key = {
        (row["algorithm_id"], int(row["window_index"])): row for row in blur_rows
    }

    assert blur_by_key[("practical.motion_blur_alert_v1", 2)]["practical_detected"] is True
    assert blur_by_key[("practical.blur_alert_v3", 2)]["practical_detected"] is False
    assert blur_by_key[("practical.blur_alert_v3", 2)]["guardrail_reason"] == "prefer_motion_blur"


def test_real_fixture_practical_motion_blur_sequence_transitions_from_suppressed_to_detected(
    tmp_path: Path,
) -> None:
    """A black-transition-heavy real fixture should move from suppressed motion-blur windows into later positive windows."""
    fixture_path = _fixture_media_path("video_files/black_recovery_realert_long.mp4")

    rows = run_detector_lab(
        DetectorLabConfig(
            input_path=fixture_path,
            mode="video_files",
            output_csv=tmp_path / "black_recovery_motion_sequence.csv",
            algorithm_ids=("practical.motion_blur_alert_v1",),
            max_windows=10,
        )
    )
    rows_by_window = {int(row["window_index"]): row for row in rows}

    for window_index in range(0, 8):
        assert rows_by_window[window_index]["practical_detected"] is False
    assert rows_by_window[8]["practical_detected"] is True
    assert rows_by_window[9]["practical_detected"] is True


def test_real_fixture_flow_backed_algorithms_export_distinct_motion_signals(
    tmp_path: Path,
) -> None:
    """Flow-backed algorithms should both emit motion fields on the same labeled slice while remaining distinguishable."""
    pytest.importorskip("cv2")
    fixture_path = _fixture_media_path("video_files/blur_trigger.mp4")

    rows = run_detector_lab(
        DetectorLabConfig(
            input_path=fixture_path,
            mode="video_files",
            output_csv=tmp_path / "blur_trigger_flow.csv",
            algorithm_ids=(
                "experimental.video_blur.motion_coherent_v1",
                "experimental.video_blur.sparse_lk_motion_v1",
                "experimental.video_blur.dense_farneback_motion_v1",
            ),
            max_windows=4,
        )
    )
    by_algorithm_window = {
        (row["algorithm_id"], int(row["window_index"])): row for row in rows
    }

    sparse_window = by_algorithm_window[("experimental.video_blur.sparse_lk_motion_v1", 2)]
    dense_window = by_algorithm_window[("experimental.video_blur.dense_farneback_motion_v1", 2)]
    coherent_window = by_algorithm_window[("experimental.video_blur.motion_coherent_v1", 2)]

    assert sparse_window["motion_blur_method"] == "sparse_lk"
    assert dense_window["motion_blur_method"] == "dense_farneback"
    assert sparse_window["optical_flow_mean"] > 0.0
    assert dense_window["optical_flow_mean"] > 0.0
    assert sparse_window["optical_flow_mean"] != dense_window["optical_flow_mean"]
    assert coherent_window["blur_score"] > 0.0


def test_real_fixture_motion_blur_fields_flow_through_full_csv_export(tmp_path: Path) -> None:
    """Motion-blur detector rows should arrive in the full CSV export with their practical fields intact."""
    fixture_path = _fixture_media_path("video_files/blur_trigger.mp4")
    output_csv = tmp_path / "blur_trigger_motion_export.csv"

    run_detector_lab(
        DetectorLabConfig(
            input_path=fixture_path,
            mode="video_files",
            output_csv=output_csv,
            algorithm_ids=("practical.motion_blur_alert_v1",),
            max_windows=3,
            output_profile="full",
        )
    )

    with output_csv.open(encoding="utf-8", newline="") as file_handle:
        csv_rows = list(csv.DictReader(file_handle))

    motion_row = next(
        row
        for row in csv_rows
        if row["algorithm_id"] == "practical.motion_blur_alert_v1"
        and row["window_index"] == "2"
    )

    assert motion_row["detector_id"] == "practical_motion_blur_alert"
    assert motion_row["ground_truth_summary"] != ""
    assert motion_row["practical_score"] != ""
    assert motion_row["practical_threshold"] == "0.68"
    assert motion_row["guardrail_reason"] == ""
    assert motion_row["alert_count"] == "1"
    assert motion_row["alert_titles"] == "Practical motion blur alert"
