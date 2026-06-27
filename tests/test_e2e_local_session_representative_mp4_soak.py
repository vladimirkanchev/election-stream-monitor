"""Full-file soak smoke for selected representative MP4 runs.

This suite stays lighter than the reviewed-subset truth lanes. Its job is to
prove that a few longer representative MP4 files can run end to end through
the real `video_files` seam without hanging, crashing, or producing unreadable
persisted output.
"""

from pathlib import Path
from typing import Any

import pytest

from tests.e2e_session_test_support import (
    assert_completed_session,
    configure_session_output,
    install_isolated_csv_stores,
    run_and_read_local_session,
)
from tests.representative_hls_test_support import (
    representative_local_file_path,
    require_representative_local_files,
)


pytestmark = [pytest.mark.e2e, pytest.mark.slow]

SOAK_FIXTURE_IDS = (
    "wide_observer__black_strong_start_12s",
    "messy_activity__compression_strong_mid_45s",
    "stable_docs",
)


def _run_full_representative_mp4_session(
    monkeypatch,
    tmp_path: Path,
    *,
    fixture_id: str,
) -> tuple[Path, tuple[object, dict[str, Any]]]:
    """Run one full representative MP4 through the real `video_files` seam.

    The soak lane keeps detector scope intentionally small so the test proves
    long-run session stability without turning into a second exact-truth suite.
    """
    configure_session_output(monkeypatch, tmp_path)
    install_isolated_csv_stores(monkeypatch, tmp_path)
    require_representative_local_files(fixture_id)
    input_path = representative_local_file_path(fixture_id)
    return input_path, run_and_read_local_session(
        mode="video_files",
        input_path=input_path,
        selected_detectors=["video_metrics"],
        session_id=f"representative-mp4-soak-{fixture_id}",
    )


def _assert_readable_persisted_outputs(
    tmp_path: Path,
    *,
    fixture_path: Path,
    snapshot: dict[str, Any],
) -> None:
    """Assert that persisted session and detector outputs stay readable."""
    metrics_path = tmp_path / "metrics" / "video_metrics.csv"

    assert (tmp_path / "sessions").exists()
    assert metrics_path.exists()
    csv_lines = metrics_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(csv_lines) >= 2
    assert snapshot["progress"]["processed_count"] >= 1
    assert len(snapshot["results"]) == snapshot["progress"]["processed_count"]
    assert snapshot["latest_result"]["payload"]["source_group"] == fixture_path.name
    assert snapshot["progress"]["current_item"] == (
        snapshot["latest_result"]["payload"]["source_name"]
    )


@pytest.mark.parametrize(
    "fixture_id",
    SOAK_FIXTURE_IDS,
    ids=lambda fixture_id: fixture_id,
)
def test_representative_full_mp4_soak_smoke_completes_with_readable_outputs(
    fixture_id: str,
    monkeypatch,
    tmp_path: Path,
    ffmpeg_available,
) -> None:
    """Selected representative MP4s should complete and persist readable output."""
    _ = ffmpeg_available
    fixture_path, (metadata, snapshot) = _run_full_representative_mp4_session(
        monkeypatch,
        tmp_path,
        fixture_id=fixture_id,
    )

    assert_completed_session(metadata, snapshot)
    assert snapshot["progress"]["status"] == "completed"
    _assert_readable_persisted_outputs(
        tmp_path,
        fixture_path=fixture_path,
        snapshot=snapshot,
    )
