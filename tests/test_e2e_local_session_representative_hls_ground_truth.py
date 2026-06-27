"""Exact session truth for the few representative HLS subsets that proved stable.

This file is intentionally narrow. Promote only reviewed clean baselines,
stable positives, and stable false-positive guards here.
"""

from pathlib import Path

import pytest

from tests.e2e_session_test_support import (
    assert_snapshot_matches_ground_truth,
    load_ground_truth_cases,
)
from tests.representative_hls_test_support import (
    require_representative_local_hls,
    representative_hls_subset_from_ground_truth_fixture,
    run_video_segments_subset_session,
)


pytestmark = [pytest.mark.e2e, pytest.mark.slow]

REPRESENTATIVE_LOCAL_HLS_CASES = load_ground_truth_cases("representative_local_hls_cases")


@pytest.mark.parametrize("case", REPRESENTATIVE_LOCAL_HLS_CASES, ids=lambda case: case["id"])
def test_representative_local_hls_ground_truth(
    case: dict[str, object],
    monkeypatch,
    tmp_path: Path,
    ffmpeg_available,
) -> None:
    """Trusted representative HLS subsets should match stored exact session truth."""
    _ = ffmpeg_available
    subset = representative_hls_subset_from_ground_truth_fixture(case["fixture"])
    require_representative_local_hls(subset.fixture_id)

    metadata, snapshot = run_video_segments_subset_session(
        monkeypatch,
        tmp_path,
        subset=subset,
        selected_detectors=case["selected_detectors"],
    )

    assert metadata.status == case["ground_truth"]["session_status"]
    assert_snapshot_matches_ground_truth(snapshot, case["ground_truth"])
