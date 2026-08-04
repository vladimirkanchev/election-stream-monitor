"""Transport-oriented checks for reviewed representative HLS subsets.

These tests serve reviewed HLS subsets over local HTTP so the real
`api_stream` seam can be exercised without a public stream. Local media and
the local HTTP server keep this as an explicit slow confidence lane.
"""

from pathlib import Path
from typing import Any

import pytest

from tests.e2e_session_test_support import (
    assert_completed_session,
)
from tests.representative_hls_test_support import (
    assert_api_stream_temp_dir_cleaned,
    detector_alerts,
    detector_payloads,
    range_indices,
    representative_expected_case,
    representative_hls_ground_truth_cases,
    representative_hls_subset,
    representative_hls_subset_from_ground_truth_fixture,
    require_representative_local_hls,
    run_api_stream_subset_session,
    run_video_segments_subset_session,
)

pytestmark = [pytest.mark.e2e, pytest.mark.slow]


PROMOTED_REPRESENTATIVE_HLS_CASES = representative_hls_ground_truth_cases()


def _payload_truths(
    snapshot: dict[str, object],
    detector_id: str,
    field_name: str,
) -> list[bool]:
    """Project one boolean detector field from a session snapshot."""
    return [
        bool(payload[field_name])
        for payload in detector_payloads(snapshot, detector_id)
    ]


def _assert_subset_progress(
    snapshot: dict[str, Any],
    subset,
    *,
    selected_detectors: list[str],
) -> None:
    """Assert completion plus the expected reviewed-subset progress shape."""
    assert snapshot["progress"]["processed_count"] == subset.segment_count
    assert snapshot["progress"]["current_item"] == subset.expected_source_names[-1]
    assert snapshot["progress"]["latest_result_detectors"] == selected_detectors


def _assert_detector_source_order(
    snapshot: dict[str, Any],
    detector_id: str,
    subset,
) -> list[dict[str, Any]]:
    """Return detector payloads after checking persisted source ordering."""
    payloads = detector_payloads(snapshot, detector_id)
    assert [payload["source_name"] for payload in payloads] == subset.expected_source_names
    return payloads


def _assert_black_negative_metrics_snapshot(
    snapshot: dict[str, Any],
    subset,
) -> None:
    """Assert that `video_metrics` stayed black-negative across a reviewed subset."""
    metric_payloads = _assert_detector_source_order(snapshot, "video_metrics", subset)
    assert len(metric_payloads) == subset.segment_count
    assert detector_alerts(snapshot, "video_metrics") == []
    assert all(payload["black_detected"] is False for payload in metric_payloads)


@pytest.mark.parametrize(
    "case",
    PROMOTED_REPRESENTATIVE_HLS_CASES,
    ids=lambda case: case["id"],
)
def test_promoted_representative_hls_keeps_shared_api_stream_contract(
    case: dict[str, object],
    monkeypatch,
    tmp_path: Path,
    ffmpeg_available,
) -> None:
    """Promoted representative HLS subsets should keep a shared transport contract.

    This matrix intentionally stays below exact seam parity. It locks the
    stable overlap between the folder-backed and HTTP/HLS-backed paths:
    completion, chunk ordering, detector coverage, and the broad behavior
    implied by the representative expectation catalog.
    """
    _ = ffmpeg_available
    subset = representative_hls_subset_from_ground_truth_fixture(case["fixture"])
    expected_case = representative_expected_case(f"{subset.fixture_id}_hls")
    require_representative_local_hls(subset.fixture_id)

    video_metadata, video_snapshot = run_video_segments_subset_session(
        monkeypatch,
        tmp_path / "video",
        subset=subset,
        selected_detectors=case["selected_detectors"],
    )
    api_metadata, api_snapshot = run_api_stream_subset_session(
        monkeypatch,
        tmp_path / "api",
        subset=subset,
        selected_detectors=case["selected_detectors"],
    )

    assert_completed_session(video_metadata, video_snapshot)
    assert_completed_session(api_metadata, api_snapshot)
    _assert_subset_progress(
        video_snapshot,
        subset,
        selected_detectors=case["selected_detectors"],
    )
    _assert_subset_progress(
        api_snapshot,
        subset,
        selected_detectors=case["selected_detectors"],
    )

    for detector_id in case["selected_detectors"]:
        _assert_detector_source_order(video_snapshot, detector_id, subset)
        _assert_detector_source_order(api_snapshot, detector_id, subset)

    if expected_case["expected"]["black_screen_alert"] == "expected":
        assert any(_payload_truths(video_snapshot, "video_metrics", "black_detected"))
    elif "video_metrics" in case["selected_detectors"]:
        _assert_black_negative_metrics_snapshot(video_snapshot, subset)
        _assert_black_negative_metrics_snapshot(api_snapshot, subset)

    if expected_case["expected"]["blur_alert"] == "expected":
        assert any(_payload_truths(video_snapshot, "video_blur", "blur_detected"))
        assert any(_payload_truths(api_snapshot, "video_blur", "blur_detected"))

    assert_api_stream_temp_dir_cleaned(api_metadata.session_id)


def test_representative_api_stream_clean_baseline_completes_and_cleans_temp_files(
    monkeypatch,
    tmp_path: Path,
    ffmpeg_available,
) -> None:
    """A clean baseline subset should complete through `api_stream` cleanly."""
    _ = ffmpeg_available
    subset = representative_hls_subset(
        fixture_id="stable_docs__source_baseline",
        subset_name="stable_docs_api_baseline_subset",
        segment_indices=range_indices(0, 11),
    )
    require_representative_local_hls(subset.fixture_id)
    metadata, snapshot = run_api_stream_subset_session(
        monkeypatch,
        tmp_path,
        subset=subset,
        selected_detectors=["video_metrics"],
    )

    assert_completed_session(metadata, snapshot)
    _assert_subset_progress(snapshot, subset, selected_detectors=["video_metrics"])
    _assert_black_negative_metrics_snapshot(snapshot, subset)
    assert_api_stream_temp_dir_cleaned(metadata.session_id)


def test_representative_api_stream_black_case_preserves_completion_and_chunk_order(
    monkeypatch,
    tmp_path: Path,
    ffmpeg_available,
) -> None:
    """A strong-black subset should stay transport-coherent in both stream modes.

    Current detector parity is not yet locked here. The transport-backed
    `api_stream` path should at least complete, process the same chunk count,
    and preserve the same segment ordering as the folder-based run.
    """
    _ = ffmpeg_available
    subset = representative_hls_subset(
        fixture_id="stable_docs__black_strong_mid_12s",
        subset_name="stable_docs_black_alignment_subset",
        segment_indices=range_indices(68, 83),
    )
    require_representative_local_hls(subset.fixture_id)

    video_metadata, video_snapshot = run_video_segments_subset_session(
        monkeypatch,
        tmp_path / "video",
        subset=subset,
        selected_detectors=["video_metrics"],
    )
    api_metadata, api_snapshot = run_api_stream_subset_session(
        monkeypatch,
        tmp_path / "api",
        subset=subset,
        selected_detectors=["video_metrics"],
    )

    assert_completed_session(video_metadata, video_snapshot)
    assert_completed_session(api_metadata, api_snapshot)
    _assert_subset_progress(video_snapshot, subset, selected_detectors=["video_metrics"])
    _assert_subset_progress(api_snapshot, subset, selected_detectors=["video_metrics"])
    _assert_detector_source_order(video_snapshot, "video_metrics", subset)
    _assert_detector_source_order(api_snapshot, "video_metrics", subset)
    assert detector_alerts(video_snapshot, "video_metrics")
    assert_api_stream_temp_dir_cleaned(api_metadata.session_id)


def test_representative_api_stream_wide_observer_startup_black_case_preserves_alert_anchor(
    monkeypatch,
    tmp_path: Path,
    ffmpeg_available,
) -> None:
    """A promoted startup-black subset should stay transport-coherent at alert level.

    The folder-backed and HTTP/HLS-backed seams currently do not agree on exact
    per-chunk black-positive counts for this startup case. This test locks the
    stable shared contract instead: completion, chunk ordering, and the same
    first alert anchor on the reviewed startup window.
    """
    _ = ffmpeg_available
    subset = representative_hls_subset(
        fixture_id="wide_observer__black_strong_start_12s",
        subset_name="wide_observer_black_start_api_subset",
        segment_indices=range_indices(0, 7),
    )
    require_representative_local_hls(subset.fixture_id)

    video_metadata, video_snapshot = run_video_segments_subset_session(
        monkeypatch,
        tmp_path / "video",
        subset=subset,
        selected_detectors=["video_metrics"],
    )
    api_metadata, api_snapshot = run_api_stream_subset_session(
        monkeypatch,
        tmp_path / "api",
        subset=subset,
        selected_detectors=["video_metrics"],
    )

    assert_completed_session(video_metadata, video_snapshot)
    assert_completed_session(api_metadata, api_snapshot)
    _assert_subset_progress(video_snapshot, subset, selected_detectors=["video_metrics"])
    _assert_subset_progress(api_snapshot, subset, selected_detectors=["video_metrics"])
    video_payloads = _assert_detector_source_order(video_snapshot, "video_metrics", subset)
    api_payloads = _assert_detector_source_order(api_snapshot, "video_metrics", subset)

    video_alerts = detector_alerts(video_snapshot, "video_metrics")
    api_alerts = detector_alerts(api_snapshot, "video_metrics")
    assert len(video_alerts) == 1
    assert len(api_alerts) == 1
    assert video_alerts[0]["source_name"] == "segment_0000.ts"
    assert api_alerts[0]["source_name"] == "segment_0000.ts"
    assert video_alerts[0]["window_index"] == 0
    assert api_alerts[0]["window_index"] == 0
    assert any(payload["black_detected"] is True for payload in video_payloads)
    assert any(payload["black_detected"] is True for payload in api_payloads)
    assert_api_stream_temp_dir_cleaned(api_metadata.session_id)


def test_representative_api_stream_blur_case_stays_aligned_with_video_segments(
    monkeypatch,
    tmp_path: Path,
    ffmpeg_available,
) -> None:
    """A strong-blur subset should stay directionally aligned in both stream modes."""
    _ = ffmpeg_available
    subset = representative_hls_subset(
        fixture_id="crowded_ballot__gblur_strong_mid_20s",
        subset_name="crowded_ballot_blur_alignment_subset",
        segment_indices=range_indices(66, 83),
    )
    require_representative_local_hls(subset.fixture_id)

    video_metadata, video_snapshot = run_video_segments_subset_session(
        monkeypatch,
        tmp_path / "video",
        subset=subset,
        selected_detectors=["video_blur"],
    )
    api_metadata, api_snapshot = run_api_stream_subset_session(
        monkeypatch,
        tmp_path / "api",
        subset=subset,
        selected_detectors=["video_blur"],
    )

    assert_completed_session(video_metadata, video_snapshot)
    assert_completed_session(api_metadata, api_snapshot)
    _assert_subset_progress(video_snapshot, subset, selected_detectors=["video_blur"])
    _assert_subset_progress(api_snapshot, subset, selected_detectors=["video_blur"])
    assert detector_alerts(video_snapshot, "video_blur")
    assert any(
        payload["blur_detected"] is True
        for payload in detector_payloads(video_snapshot, "video_blur")
    )
    api_payloads = _assert_detector_source_order(api_snapshot, "video_blur", subset)
    assert sum(1 for payload in api_payloads if payload["blur_detected"] is True) >= 1
    assert_api_stream_temp_dir_cleaned(api_metadata.session_id)

@pytest.mark.parametrize(
    ("fixture_id", "subset_name", "segment_indices"),
    [
        (
            "crowded_ballot__compression_strong_repeated_3x20s",
            "crowded_ballot_compression_api_subset",
            range_indices(68, 83),
        ),
        (
            "messy_activity__compression_strong_mid_45s",
            "messy_activity_compression_api_subset",
            range_indices(53, 75),
        ),
    ],
    ids=["crowded_ballot_repeated_compression", "messy_activity_mid_compression"],
)
def test_representative_api_stream_compression_cases_stay_black_negative_and_aligned(
    fixture_id: str,
    subset_name: str,
    segment_indices: tuple[int, ...],
    monkeypatch,
    tmp_path: Path,
    ffmpeg_available,
) -> None:
    """Compression-heavy reviewed subsets should stay transport-coherent and black-negative.

    This keeps the same reviewed subset aligned across the folder-backed and
    HTTP/HLS-backed seams without forcing exact metric parity beyond the
    behavior we already trust for this case.
    """
    _ = ffmpeg_available
    subset = representative_hls_subset(
        fixture_id=fixture_id,
        subset_name=subset_name,
        segment_indices=segment_indices,
    )
    require_representative_local_hls(subset.fixture_id)

    video_metadata, video_snapshot = run_video_segments_subset_session(
        monkeypatch,
        tmp_path / "video",
        subset=subset,
        selected_detectors=["video_metrics"],
    )
    api_metadata, api_snapshot = run_api_stream_subset_session(
        monkeypatch,
        tmp_path / "api",
        subset=subset,
        selected_detectors=["video_metrics"],
    )

    assert_completed_session(video_metadata, video_snapshot)
    assert_completed_session(api_metadata, api_snapshot)
    _assert_subset_progress(video_snapshot, subset, selected_detectors=["video_metrics"])
    _assert_subset_progress(api_snapshot, subset, selected_detectors=["video_metrics"])
    _assert_black_negative_metrics_snapshot(video_snapshot, subset)
    _assert_black_negative_metrics_snapshot(api_snapshot, subset)
    assert_api_stream_temp_dir_cleaned(api_metadata.session_id)


def test_representative_api_stream_lowres_case_keeps_snapshot_shape_and_black_negative(
    monkeypatch,
    tmp_path: Path,
    ffmpeg_available,
) -> None:
    """A low-resolution subset should complete with coherent multi-detector progress."""
    _ = ffmpeg_available
    subset = representative_hls_subset(
        fixture_id="stable_docs__lowres_moderate_start_30s",
        subset_name="stable_docs_lowres_api_subset",
        segment_indices=range_indices(0, 17),
    )
    require_representative_local_hls(subset.fixture_id)

    metadata, snapshot = run_api_stream_subset_session(
        monkeypatch,
        tmp_path,
        subset=subset,
        selected_detectors=["video_metrics", "video_blur"],
    )

    assert_completed_session(metadata, snapshot)
    _assert_subset_progress(snapshot, subset, selected_detectors=[
        "video_metrics",
        "video_blur",
    ])
    _assert_black_negative_metrics_snapshot(snapshot, subset)
    blur_payloads = _assert_detector_source_order(snapshot, "video_blur", subset)
    assert len(blur_payloads) == subset.segment_count
    assert_api_stream_temp_dir_cleaned(metadata.session_id)
