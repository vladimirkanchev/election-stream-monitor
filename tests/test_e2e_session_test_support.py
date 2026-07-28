"""Contracts for bounded ground-truth variance and sanitized failure diagnostics."""

import json

import pytest

from tests.e2e_session_test_support import (
    assert_detector_truth_counts,
    assert_snapshot_matches_ground_truth,
    ground_truth_diagnostic_context,
)


def _expected_snapshot() -> dict[str, object]:
    return {
        "session_status": "completed",
        "progress_status": "completed",
        "processed_count": 1,
        "result_count": 2,
        "alert_count": 1,
        "current_item": "clip.mp4 @ 00:00",
        "latest_result_detectors": ["video_metrics", "video_blur"],
        "detector_true_counts": {"video_metrics": 1, "video_blur": 0},
        "alerts": [
            {
                "detector_id": "video_metrics",
                "source_name": "clip.mp4",
                "window_index": 0,
                "window_start_sec": 0.0,
            }
        ],
    }


def _snapshot(alerts: list[dict[str, object]]) -> dict[str, object]:
    return {
        "session": {"status": "completed"},
        "progress": {
            "status": "completed",
            "processed_count": 1,
            "current_item": "clip.mp4 @ 00:00",
            "latest_result_detectors": ["video_metrics", "video_blur"],
        },
        "results": [
            {
                "detector_id": "video_metrics",
                "payload": {"black_detected": True, "source_name": "clip.mp4"},
            },
            {
                "detector_id": "video_blur",
                "payload": {"blur_detected": False, "source_name": "clip.mp4"},
            },
        ],
        "alerts": alerts,
    }


def test_snapshot_truth_allows_one_additional_video_metrics_alert() -> None:
    """The decoder-variance path permits only one additional black-detector alert."""
    expected = _expected_snapshot()
    expected_alert = expected["alerts"][0]
    extra_alert = {**expected_alert, "window_index": 1, "window_start_sec": 1.0}

    assert_snapshot_matches_ground_truth(
        _snapshot([expected_alert, extra_alert]),
        expected,
        allow_video_metrics_variance=True,
    )


def test_snapshot_truth_rejects_extra_alert_from_another_detector() -> None:
    """The decoder-variance path must not hide a blur-alert regression."""
    expected = _expected_snapshot()
    expected_alert = expected["alerts"][0]
    extra_alert = {**expected_alert, "detector_id": "video_blur"}

    with pytest.raises(AssertionError, match="Unexpected alert variance"):
        assert_snapshot_matches_ground_truth(
            _snapshot([expected_alert, extra_alert]),
            expected,
            allow_video_metrics_variance=True,
        )


def test_snapshot_truth_rejects_more_than_one_extra_black_alert() -> None:
    """The decoder-variance path must not become an unbounded alert allowance."""
    expected = _expected_snapshot()
    expected_alert = expected["alerts"][0]
    first_extra = {**expected_alert, "window_index": 1, "window_start_sec": 1.0}
    second_extra = {**expected_alert, "window_index": 2, "window_start_sec": 2.0}

    with pytest.raises(AssertionError, match=r"alert count in \[1, 2\]"):
        assert_snapshot_matches_ground_truth(
            _snapshot([expected_alert, first_extra, second_extra]),
            expected,
            allow_video_metrics_variance=True,
        )


def test_snapshot_truth_keeps_expected_alert_order_under_variance() -> None:
    """The decoder allowance must not reorder reviewed expected alerts."""
    expected = _expected_snapshot()
    first_alert = expected["alerts"][0]
    second_alert = {**first_alert, "window_index": 2, "window_start_sec": 2.0}
    expected["alerts"] = [first_alert, second_alert]
    expected["alert_count"] = 2

    with pytest.raises(AssertionError, match="Missing expected alert sequence"):
        assert_snapshot_matches_ground_truth(
            _snapshot([second_alert, first_alert]),
            expected,
            allow_video_metrics_variance=True,
        )


def test_truth_count_variance_does_not_allow_missing_black_detection() -> None:
    """The decoder-variance path permits one extra black result, not fewer."""
    with pytest.raises(AssertionError, match=r"truth count in \[2, 3\]"):
        assert_detector_truth_counts(
            _snapshot([]),
            {"video_metrics": 2},
            allow_video_metrics_count_variance=True,
        )


def test_ground_truth_failure_writes_compact_sanitized_artifact(
    monkeypatch,
    tmp_path,
) -> None:
    """A failing case should record stable facts without full source details."""
    monkeypatch.setenv("ESM_GROUND_TRUTH_ARTIFACT_DIR", str(tmp_path))
    expected = _expected_snapshot()
    expected["processed_count"] = 2
    context = ground_truth_diagnostic_context(
        {
            "id": "checked in case",
            "mode": "video_files",
            "fixture": {"kind": "checked_in", "path": "private/path/clip.mp4"},
            "selected_detectors": ["video_metrics", "video_blur"],
        }
    )

    with pytest.raises(AssertionError):
        assert_snapshot_matches_ground_truth(
            _snapshot(expected["alerts"]),
            expected,
            diagnostic_context=context,
        )

    artifact = json.loads((tmp_path / "checked-in-case.json").read_text(encoding="utf-8"))
    assert artifact["case"] == {
        "case_id": "checked in case",
        "fixture_id": "clip.mp4",
        "fixture_kind": "checked_in",
        "mode": "video_files",
        "selected_detectors": ["video_metrics", "video_blur"],
        "subset_indices": [],
        "subset_name": "full_fixture",
    }
    assert artifact["actual"]["alerts"] == [
        {"detector_id": "video_metrics", "window_index": 0, "window_start_sec": 0.0}
    ]
    assert artifact["actual"]["results"][0] == {
        "black_detected": True,
        "detector_id": "video_metrics",
    }
    assert "private/path" not in json.dumps(artifact)


def test_ground_truth_failure_artifact_bounds_projected_result_rows(
    monkeypatch,
    tmp_path,
) -> None:
    """Failure diagnostics should cap rows and omit source data from each projection."""
    monkeypatch.setenv("ESM_GROUND_TRUTH_ARTIFACT_DIR", str(tmp_path))
    expected = _expected_snapshot()
    snapshot = _snapshot(expected["alerts"])
    snapshot["results"] = [
        {
            "detector_id": "video_metrics",
            "payload": {
                "black_detected": True,
                "source_name": "private/path/clip.mp4",
                "window_index": index,
            },
        }
        for index in range(25)
    ]

    with pytest.raises(AssertionError):
        assert_snapshot_matches_ground_truth(
            snapshot,
            expected,
            diagnostic_context=ground_truth_diagnostic_context(
                {"id": "bounded diagnostic", "fixture": {"kind": "checked_in"}}
            ),
        )

    artifact = json.loads((tmp_path / "bounded-diagnostic.json").read_text(encoding="utf-8"))
    assert artifact["actual"]["results_truncated"] is True
    assert len(artifact["actual"]["results"]) == 24
    assert all("source_name" not in row for row in artifact["actual"]["results"])
