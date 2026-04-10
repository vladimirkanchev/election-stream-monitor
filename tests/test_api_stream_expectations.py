"""Checks for the local api_stream validation manifest."""

from __future__ import annotations

import json
from pathlib import Path


EXPECTATIONS_PATH = Path(__file__).parent / "fixtures" / "media" / "api_stream_expectations.json"
GROUND_TRUTH_PATH = Path(__file__).parent / "fixtures" / "media" / "ground_truth.json"
MEDIA_ROOT = Path(__file__).parent / "fixtures" / "media"


def test_api_stream_expectation_manifest_matches_current_validation_set() -> None:
    """The local api_stream validation manifest should stay aligned with checked-in fixtures."""
    expectations = json.loads(EXPECTATIONS_PATH.read_text(encoding="utf-8"))
    ground_truth = json.loads(GROUND_TRUTH_PATH.read_text(encoding="utf-8"))

    assert expectations["schema_version"] == "api_stream_expectations_v1"

    cases = expectations["cases"]
    case_ids = [case["id"] for case in cases]
    assert len(case_ids) == len(set(case_ids))

    ground_truth_cases = {
        (
            case["fixture"]["path"],
            tuple(case["selected_detectors"]),
        ): case["ground_truth"]
        for case in ground_truth["local_session_cases"]
        if case["mode"] == "video_segments" and case["fixture"]["kind"] == "checked_in"
    }

    for case in cases:
        fixture_dir = MEDIA_ROOT / case["fixture_path"]
        assert fixture_dir.exists()
        assert (fixture_dir / "index.m3u8").exists()
        assert case["selected_detectors"]
        assert case["expected_chunk_count"] >= 0
        assert case["expected_alert_count"] >= 0
        assert case["expected_final_status"] in {"completed", "failed", "cancelled"}
        assert case["expected_log_snippets"]
        assert all(isinstance(entry, str) and entry for entry in case["expected_log_snippets"])
        assert case["expected_cleanup_checks"]
        assert all(
            isinstance(entry, str) and entry for entry in case["expected_cleanup_checks"]
        )

        ground_truth_key = (case["fixture_path"], tuple(case["selected_detectors"]))
        if ground_truth_key in ground_truth_cases:
            expected = ground_truth_cases[ground_truth_key]
            assert case["expected_chunk_count"] == expected["processed_count"]
            assert case["expected_alert_count"] == expected["alert_count"]
            assert case["expected_final_status"] == expected["session_status"]


def test_api_stream_expectation_manifest_handles_clean_baseline_and_missing_segment_cases() -> None:
    """Non-ground-truth api_stream validation cases should still have explicit structural checks."""
    expectations = json.loads(EXPECTATIONS_PATH.read_text(encoding="utf-8"))
    cases = {case["id"]: case for case in expectations["cases"]}

    clean_case = cases["api_stream_clean_baseline_long_metrics_only"]
    clean_dir = MEDIA_ROOT / clean_case["fixture_path"]
    clean_segments = sorted(clean_dir.glob("segment_*.ts"))
    assert len(clean_segments) == clean_case["expected_chunk_count"]
    assert clean_case["expected_alert_count"] == 0
    assert clean_case["expected_final_status"] == "completed"

    missing_case = cases["api_stream_missing_segment_long_metrics"]
    missing_dir = MEDIA_ROOT / missing_case["fixture_path"]
    playlist_lines = (missing_dir / "index.m3u8").read_text(encoding="utf-8").splitlines()
    referenced_segments = [
        line.strip()
        for line in playlist_lines
        if line.strip().startswith("segment_")
    ]
    first_missing_index = next(
        index
        for index, segment_name in enumerate(referenced_segments)
        if not (missing_dir / segment_name).exists()
    )

    assert referenced_segments[first_missing_index] == "segment_0004.ts"
    assert missing_case["expected_chunk_count"] == first_missing_index
    assert missing_case["expected_alert_count"] == 0
    assert missing_case["expected_final_status"] == "failed"
    assert "api_stream upstream returned HTTP 404" in missing_case["expected_log_snippets"]
