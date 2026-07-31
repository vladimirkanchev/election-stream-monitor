"""Regression coverage for bounded detector-lab real-media failure diagnostics."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.detector_lab_failure_diagnostics import (
    DetectorLabDiagnosticContext,
    MAX_DIAGNOSTIC_ROWS,
    build_failure_diagnostic,
    emit_failure_diagnostic_on_error,
    persist_csv_artifact,
)


def _context() -> DetectorLabDiagnosticContext:
    """Return a reviewed fixture context without local paths."""
    return DetectorLabDiagnosticContext(
        label="blur trigger",
        fixture_id="video_files/blur_trigger.mp4",
        algorithm_ids=("practical.motion_blur_alert_v1",),
        max_windows=3,
    )


def test_failure_diagnostic_projects_safe_rows_and_expected_actual_counts(monkeypatch) -> None:
    """Failure evidence should retain detector facts without source internals."""
    monkeypatch.setattr(
        "tests.detector_lab_failure_diagnostics._environment_versions",
        lambda: {"python": "3.12", "ffmpeg": "7", "ffprobe": "7", "opencv": "4"},
    )
    diagnostic = build_failure_diagnostic(
        _context(),
        [
            {
                "detector_id": "practical_motion_blur_alert",
                "algorithm_id": "practical.motion_blur_alert_v1",
                "window_index": 2,
                "practical_detected": True,
                "practical_score": 0.8,
                "source_name": "/private/path/clip.mp4",
                "raw_detector_payload": "secret",
            }
        ],
    )

    assert diagnostic["fixture"] == {
        "id": "video_files/blur_trigger.mp4",
        "label": "blur trigger",
    }
    assert diagnostic["expected"]["requested_row_count"] == 3
    assert diagnostic["actual"]["detector_row_counts"] == {
        "practical_motion_blur_alert": 1
    }
    assert diagnostic["actual"]["rows"] == [
        {
            "algorithm_id": "practical.motion_blur_alert_v1",
            "detector_id": "practical_motion_blur_alert",
            "window_index": 2,
            "practical_detected": True,
            "practical_score": 0.8,
        }
    ]
    serialized = json.dumps(diagnostic)
    assert "/private/path" not in serialized
    assert "secret" not in serialized


def test_failure_diagnostic_writes_an_artifact_only_after_an_error(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Successful assertions must not create an artifact, unlike failures."""
    monkeypatch.setenv("ESM_DETECTOR_LAB_ARTIFACT_DIR", str(tmp_path))
    monkeypatch.setattr(
        "tests.detector_lab_failure_diagnostics._environment_versions", lambda: {}
    )
    rows = [
        {"detector_id": "video_blur", "window_index": index, "source_name": "/private"}
        for index in range(MAX_DIAGNOSTIC_ROWS + 1)
    ]

    with emit_failure_diagnostic_on_error(_context(), rows):
        pass
    assert not list(tmp_path.iterdir())

    with pytest.raises(AssertionError):
        with emit_failure_diagnostic_on_error(_context(), rows):
            raise AssertionError("expected detector failure")

    artifact = json.loads((tmp_path / "blur-trigger.failure.json").read_text())
    assert artifact["actual"]["rows_truncated"] is True
    assert len(artifact["actual"]["rows"]) == MAX_DIAGNOSTIC_ROWS
    assert "/private" not in json.dumps(artifact)


def test_csv_artifact_copy_enforces_file_and_bundle_bounds(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Configured CSV evidence must stay within the published upload budget."""
    artifact_dir = tmp_path / "artifacts"
    output_csv = tmp_path / "result.csv"
    output_csv.write_bytes(b"rows")
    monkeypatch.setenv("ESM_DETECTOR_LAB_ARTIFACT_DIR", str(artifact_dir))

    assert persist_csv_artifact(output_csv) is True
    assert (artifact_dir / output_csv.name).read_bytes() == b"rows"

    monkeypatch.setattr(
        "tests.detector_lab_failure_diagnostics.MAX_CSV_BYTES",
        3,
    )
    assert persist_csv_artifact(output_csv) is False


def test_csv_artifact_copy_enforces_count_and_total_size_limits(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """The artifact directory must reject excess CSV count and aggregate size."""
    artifact_dir = tmp_path / "artifacts"
    artifact_dir.mkdir()
    (artifact_dir / "existing.csv").write_bytes(b"old")
    output_csv = tmp_path / "result.csv"
    output_csv.write_bytes(b"new")
    monkeypatch.setenv("ESM_DETECTOR_LAB_ARTIFACT_DIR", str(artifact_dir))

    monkeypatch.setattr(
        "tests.detector_lab_failure_diagnostics.MAX_CSV_FILES",
        1,
    )
    assert persist_csv_artifact(output_csv) is False

    monkeypatch.setattr(
        "tests.detector_lab_failure_diagnostics.MAX_CSV_FILES",
        12,
    )
    monkeypatch.setattr(
        "tests.detector_lab_failure_diagnostics.MAX_CSV_TOTAL_BYTES",
        5,
    )
    assert persist_csv_artifact(output_csv) is False
