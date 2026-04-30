"""Ground-truth validation for real local-session media fixtures.

This file owns the slower real-media matrix. The synthetic `api_stream`
ground-truth cases live separately so developers can exercise contract-heavy
live-session behavior without paying for the full ffmpeg-backed fixture set.
"""
from pathlib import Path

import pytest

from tests.e2e_session_test_support import (
    assert_snapshot_matches_ground_truth,
    configure_session_output,
    install_isolated_csv_stores,
    load_ground_truth_cases,
    resolve_fixture_path,
    run_and_read_local_session,
)


pytestmark = [pytest.mark.e2e, pytest.mark.slow]

LOCAL_SESSION_CASES = load_ground_truth_cases("local_session_cases")


@pytest.mark.parametrize("case", LOCAL_SESSION_CASES, ids=lambda case: case["id"])
def test_local_session_ground_truth_with_real_fixtures(
    case: dict[str, object],
    monkeypatch,
    tmp_path: Path,
    media_factory,
    media_fixture_dir: Path,
) -> None:
    """Real checked-in and generated media fixtures should match stored session truth.

    The JSON fixture defines the matrix; this test keeps the assertion logic
    centralized so the scenario data stays easy to review.
    """
    configure_session_output(monkeypatch, tmp_path)
    install_isolated_csv_stores(monkeypatch, tmp_path)

    input_path = resolve_fixture_path(
        case,
        media_fixture_dir=media_fixture_dir,
        media_factory=media_factory,
    )
    metadata, snapshot = run_and_read_local_session(
        mode=case["mode"],
        input_path=input_path,
        selected_detectors=case["selected_detectors"],
        session_id=f"ground-truth-{case['id']}",
    )

    tolerate_checked_in_mp4_black_variance = (
        case["mode"] == "video_files"
        and case["fixture"]["kind"] == "checked_in"
    )

    assert metadata.status == case["ground_truth"]["session_status"]
    assert_snapshot_matches_ground_truth(
        snapshot,
        case["ground_truth"],
        tolerate_checked_in_mp4_black_variance=tolerate_checked_in_mp4_black_variance,
    )
