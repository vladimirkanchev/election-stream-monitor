"""Exact session truth for the small reviewed representative MP4 window subsets.

This optional local-media lane exercises the real `video_files` session seam
on reviewed one-second windows without replaying full source clips.
"""

from pathlib import Path

import pytest

from tests.e2e_session_test_support import (
    ground_truth_diagnostic_context,
    assert_snapshot_matches_ground_truth,
)
from tests.representative_hls_test_support import (
    representative_video_file_ground_truth_cases,
    representative_video_file_subset_from_ground_truth_fixture,
    require_representative_local_files,
    run_video_files_subset_session,
)


pytestmark = [pytest.mark.e2e, pytest.mark.slow]

REPRESENTATIVE_LOCAL_VIDEO_FILE_CASES = representative_video_file_ground_truth_cases()


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
    assert_snapshot_matches_ground_truth(
        snapshot,
        case["ground_truth"],
        diagnostic_context=ground_truth_diagnostic_context(
            case,
            fixture_id=subset.fixture_id,
            subset_name=subset.subset_name,
            subset_indices=subset.window_indices,
        ),
    )
