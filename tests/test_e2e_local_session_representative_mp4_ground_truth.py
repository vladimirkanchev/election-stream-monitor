"""Exact session truth for the small reviewed representative MP4 window subsets.

This lane stays intentionally narrow. It exercises the real `video_files`
session seam on reviewed one-second windows without replaying every full
representative source clip in CI-sized test runs.
"""

from pathlib import Path

import pytest

from tests.e2e_session_test_support import (
    assert_snapshot_matches_ground_truth,
    load_ground_truth_cases,
)
from tests.representative_hls_test_support import (
    representative_video_file_subset_from_ground_truth_fixture,
    require_representative_local_files,
    run_video_files_subset_session,
)


pytestmark = [pytest.mark.e2e, pytest.mark.slow]

REPRESENTATIVE_LOCAL_VIDEO_FILE_CASES = load_ground_truth_cases(
    "representative_local_video_file_cases"
)


@pytest.mark.parametrize(
    "case",
    REPRESENTATIVE_LOCAL_VIDEO_FILE_CASES,
    ids=lambda case: case["id"],
)
def test_representative_local_video_file_ground_truth(
    case: dict[str, object],
    monkeypatch,
    tmp_path: Path,
    ffmpeg_available,
) -> None:
    """Trusted representative MP4 window subsets should match stored session truth."""
    _ = ffmpeg_available
    subset = representative_video_file_subset_from_ground_truth_fixture(case["fixture"])
    require_representative_local_files(subset.fixture_id)

    metadata, snapshot = run_video_files_subset_session(
        monkeypatch,
        tmp_path,
        subset=subset,
        selected_detectors=case["selected_detectors"],
    )

    assert metadata.status == case["ground_truth"]["session_status"]
    assert_snapshot_matches_ground_truth(snapshot, case["ground_truth"])
