"""Behavior-oriented checks for reviewed representative HLS subsets.

This suite is intentionally broader than the exact-truth lane. It checks the
stable intent we want from reviewed subsets without forcing fake precision on
borderline cases.
"""

from pathlib import Path
from typing import Any

import pytest

from tests.e2e_session_test_support import (
    assert_completed_session,
)
from tests.representative_hls_test_support import (
    RepresentativeHlsSubset,
    detector_alerts,
    detector_payloads,
    merge_index_groups,
    range_indices,
    representative_hls_subset,
    representative_video_file_subset,
    require_representative_local_hls,
    require_representative_local_files,
    run_video_files_subset_session,
    run_video_segments_subset_session,
)


pytestmark = [pytest.mark.e2e, pytest.mark.slow]


def _run_hls_subset_session(
    monkeypatch,
    tmp_path: Path,
    *,
    fixture_id: str,
    subset_name: str,
    segment_indices: tuple[int, ...],
    selected_detectors: list[str],
) -> tuple[object, RepresentativeHlsSubset, dict[str, Any]]:
    """Run one reviewed HLS subset through the `video_segments` seam."""
    subset = representative_hls_subset(
        fixture_id=fixture_id,
        subset_name=subset_name,
        segment_indices=segment_indices,
    )
    require_representative_local_hls(subset.fixture_id)
    metadata, snapshot = run_video_segments_subset_session(
        monkeypatch,
        tmp_path,
        subset=subset,
        selected_detectors=selected_detectors,
    )
    return metadata, subset, snapshot


def _assert_subset_completed(
    metadata,
    snapshot: dict[str, Any],
    subset: RepresentativeHlsSubset,
) -> None:
    """Assert completion plus the reviewed subset's expected segment order."""
    assert_completed_session(metadata, snapshot)
    assert snapshot["progress"]["processed_count"] == subset.segment_count
    assert snapshot["progress"]["current_item"] == subset.expected_source_names[-1]


def _assert_detector_payload_source_order(
    snapshot: dict[str, Any],
    detector_id: str,
    expected_source_names: list[str],
) -> list[dict[str, Any]]:
    """Return detector payloads after checking persisted source ordering."""
    payloads = detector_payloads(snapshot, detector_id)
    assert [payload["source_name"] for payload in payloads] == expected_source_names
    return payloads


def _assert_black_negative_metrics_snapshot(
    snapshot: dict[str, Any],
    subset: RepresentativeHlsSubset,
) -> None:
    """Assert that `video_metrics` stayed black-negative across a reviewed subset."""
    metric_payloads = _assert_detector_payload_source_order(
        snapshot,
        "video_metrics",
        subset.expected_source_names,
    )
    assert len(metric_payloads) == subset.segment_count
    assert detector_alerts(snapshot, "video_metrics") == []
    assert all(payload["black_detected"] is False for payload in metric_payloads)


@pytest.mark.parametrize(
    ("fixture_id", "subset_name"),
    [
        ("stable_docs__source_baseline", "stable_docs_baseline_subset"),
        ("messy_activity__source_baseline", "messy_activity_baseline_subset"),
    ],
)
def test_representative_hls_clean_baselines_stay_black_negative(
    fixture_id: str,
    subset_name: str,
    monkeypatch,
    tmp_path: Path,
    ffmpeg_available,
) -> None:
    """Clean baseline HLS subsets should stay black-negative."""
    _ = ffmpeg_available
    metadata, subset, snapshot = _run_hls_subset_session(
        monkeypatch,
        tmp_path,
        fixture_id=fixture_id,
        subset_name=subset_name,
        segment_indices=range_indices(0, 11),
        selected_detectors=["video_metrics"],
    )

    _assert_subset_completed(metadata, snapshot, subset)
    _assert_black_negative_metrics_snapshot(snapshot, subset)


def test_representative_hls_strong_black_case_emits_black_alerts(
    monkeypatch,
    tmp_path: Path,
    ffmpeg_available,
) -> None:
    """A trusted strong-black HLS subset should produce black detections and alerts."""
    _ = ffmpeg_available
    metadata, subset, snapshot = _run_hls_subset_session(
        monkeypatch,
        tmp_path,
        fixture_id="stable_docs__black_strong_mid_12s",
        subset_name="stable_docs_black_strong_subset",
        segment_indices=range_indices(68, 83),
        selected_detectors=["video_metrics"],
    )

    _assert_subset_completed(metadata, snapshot, subset)
    metric_payloads = _assert_detector_payload_source_order(
        snapshot,
        "video_metrics",
        subset.expected_source_names,
    )
    assert len(metric_payloads) == subset.segment_count
    assert any(payload["black_detected"] is True for payload in metric_payloads)
    assert detector_alerts(snapshot, "video_metrics")


def test_representative_hls_strong_blur_case_emits_blur_alerts(
    monkeypatch,
    tmp_path: Path,
    ffmpeg_available,
) -> None:
    """A trusted strong-blur HLS subset should produce blur detections and alerts."""
    _ = ffmpeg_available
    metadata, subset, snapshot = _run_hls_subset_session(
        monkeypatch,
        tmp_path,
        fixture_id="crowded_ballot__gblur_strong_mid_20s",
        subset_name="crowded_ballot_blur_strong_subset",
        segment_indices=range_indices(66, 83),
        selected_detectors=["video_blur"],
    )

    _assert_subset_completed(metadata, snapshot, subset)
    blur_payloads = _assert_detector_payload_source_order(
        snapshot,
        "video_blur",
        subset.expected_source_names,
    )
    assert len(blur_payloads) == subset.segment_count
    assert any(payload["blur_detected"] is True for payload in blur_payloads)
    assert detector_alerts(snapshot, "video_blur")


def test_representative_hls_strong_blur_case_keeps_shared_mp4_core_contract(
    monkeypatch,
    tmp_path: Path,
    ffmpeg_available,
) -> None:
    """Promoted strong-blur MP4 and HLS subsets should agree on the reviewed positive core.

    The current promoted blur subset is only the trusted positive core window.
    We therefore lock the stable overlap we actually have today: both seams
    complete, both emit blur alerts, and both keep every reviewed slice
    blur-positive inside that shared core.
    """
    _ = ffmpeg_available
    hls_subset = representative_hls_subset(
        fixture_id="crowded_ballot__gblur_strong_mid_20s",
        subset_name="crowded_ballot_blur_strong_parity_hls_subset",
        segment_indices=range_indices(66, 83),
    )
    mp4_subset = representative_video_file_subset(
        fixture_id="crowded_ballot__gblur_strong_mid_20s",
        subset_name="crowded_ballot_blur_strong_parity_mp4_subset",
        window_indices=range_indices(132, 167),
    )
    require_representative_local_hls(hls_subset.fixture_id)
    require_representative_local_files(mp4_subset.fixture_id)

    hls_metadata, hls_snapshot = run_video_segments_subset_session(
        monkeypatch,
        tmp_path / "hls",
        subset=hls_subset,
        selected_detectors=["video_blur"],
    )
    mp4_metadata, mp4_snapshot = run_video_files_subset_session(
        monkeypatch,
        tmp_path / "mp4",
        subset=mp4_subset,
        selected_detectors=["video_blur"],
    )

    _assert_subset_completed(hls_metadata, hls_snapshot, hls_subset)
    assert_completed_session(mp4_metadata, mp4_snapshot)
    assert mp4_snapshot["progress"]["processed_count"] == mp4_subset.window_count
    assert mp4_snapshot["progress"]["current_item"] == mp4_subset.expected_source_names[-1]

    hls_payloads = _assert_detector_payload_source_order(
        hls_snapshot,
        "video_blur",
        hls_subset.expected_source_names,
    )
    mp4_payloads = detector_payloads(mp4_snapshot, "video_blur")
    assert len(hls_payloads) == hls_subset.segment_count
    assert len(mp4_payloads) == mp4_subset.window_count
    assert [payload["source_name"] for payload in mp4_payloads] == mp4_subset.expected_source_names
    assert detector_alerts(hls_snapshot, "video_blur")
    assert detector_alerts(mp4_snapshot, "video_blur")
    assert all(payload["blur_detected"] is True for payload in hls_payloads)
    assert all(payload["blur_detected"] is True for payload in mp4_payloads)


def test_representative_hls_repeated_compression_does_not_fake_black_alerts(
    monkeypatch,
    tmp_path: Path,
    ffmpeg_available,
) -> None:
    """Repeated heavy compression should not drift into fake black alerts."""
    _ = ffmpeg_available
    metadata, subset, snapshot = _run_hls_subset_session(
        monkeypatch,
        tmp_path,
        fixture_id="crowded_ballot__compression_strong_repeated_3x20s",
        subset_name="crowded_ballot_compression_mid_subset",
        segment_indices=range_indices(68, 83),
        selected_detectors=["video_metrics"],
    )

    _assert_subset_completed(metadata, snapshot, subset)
    _assert_black_negative_metrics_snapshot(snapshot, subset)


def test_representative_hls_low_resolution_case_stays_black_negative(
    monkeypatch,
    tmp_path: Path,
    ffmpeg_available,
) -> None:
    """The reviewed low-resolution HLS subset should stay black-negative.

    Blur stays intentionally broad here because this case is still more useful
    as a quality-degradation sample than as exact blur truth.
    """
    _ = ffmpeg_available
    metadata, subset, snapshot = _run_hls_subset_session(
        monkeypatch,
        tmp_path,
        fixture_id="stable_docs__lowres_moderate_start_30s",
        subset_name="stable_docs_lowres_start_subset",
        segment_indices=range_indices(0, 17),
        selected_detectors=["video_metrics", "video_blur"],
    )

    _assert_subset_completed(metadata, snapshot, subset)
    _assert_black_negative_metrics_snapshot(snapshot, subset)
    blur_payloads = _assert_detector_payload_source_order(
        snapshot,
        "video_blur",
        subset.expected_source_names,
    )
    assert len(blur_payloads) == subset.segment_count


def test_representative_hls_repeated_compression_bursts_keep_processing_consistent(
    monkeypatch,
    tmp_path: Path,
    ffmpeg_available,
) -> None:
    """A reviewed repeated-compression subset should preserve playlist order."""
    _ = ffmpeg_available
    subset = representative_hls_subset(
        fixture_id="crowded_ballot__compression_strong_repeated_3x20s",
        subset_name="crowded_ballot_compression_repeated_subset",
        segment_indices=merge_index_groups(
            range_indices(28, 41),
            range_indices(68, 81),
            range_indices(108, 121),
        ),
    )
    require_representative_local_hls(subset.fixture_id)

    metadata, snapshot = run_video_segments_subset_session(
        monkeypatch,
        tmp_path,
        subset=subset,
        selected_detectors=["video_metrics"],
    )

    _assert_subset_completed(metadata, snapshot, subset)
    _assert_black_negative_metrics_snapshot(snapshot, subset)
