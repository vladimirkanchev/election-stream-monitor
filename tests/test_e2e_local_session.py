"""Snapshot-contract smoke test for one completed local session.

This file intentionally stays small. The heavier local session lifecycle
coverage lives in `test_session_runner_local.py`.
"""

from pathlib import Path

import config
from session_io import read_session_snapshot
from session_runner import run_local_session


def _write_segment_inputs(input_dir: Path) -> None:
    input_dir.mkdir()
    (input_dir / "segment_0001.ts").write_bytes(b"aa")
    (input_dir / "segment_0002.ts").write_bytes(b"bb")


def _fake_bundle_for_snapshot_contract(
    file_path: Path,
    prefix: str,
    mode: str,
    session_id: str,
    selected_analyzers: set[str] | None = None,
    persist_to_store: bool = True,
) -> dict[str, list[dict[str, object]]]:
    _ = (prefix, mode, selected_analyzers, persist_to_store)
    return {
        "results": [
            {
                "session_id": session_id,
                "detector_id": "video_metrics",
                "payload": {
                    "source_name": file_path.name,
                    "timestamp_utc": "2026-03-30 12:00:00",
                    "processing_sec": 0.01,
                },
            }
        ],
        "alerts": [
            {
                "session_id": session_id,
                "timestamp_utc": "2026-03-30 12:00:00",
                "detector_id": "video_metrics",
                "title": "Low bitrate observed",
                "message": f"Nominal bitrate dropped for {file_path.name}.",
                "severity": "info",
                "source_name": file_path.name,
            }
        ]
        if file_path.name == "segment_0002.ts"
        else [],
    }


def test_e2e_local_session_snapshot_contract_smoke(monkeypatch, tmp_path: Path) -> None:
    """One completed local run should still produce the frontend-readable snapshot shape."""
    monkeypatch.setattr(config, "SESSION_OUTPUT_FOLDER", tmp_path / "sessions")
    input_dir = tmp_path / "segments"
    _write_segment_inputs(input_dir)

    monkeypatch.setattr(
        "session_runner.run_enabled_analyzers_bundle",
        _fake_bundle_for_snapshot_contract,
    )
    monkeypatch.setattr("session_runner.black_frame_store.flush", lambda: None)
    monkeypatch.setattr("session_runner.blur_metrics_store.flush", lambda: None)

    metadata = run_local_session(
        mode="video_segments",
        input_path=input_dir,
        selected_detectors=["video_metrics"],
    )

    snapshot = read_session_snapshot(metadata.session_id)

    assert metadata.status == "completed"
    assert snapshot["session"]["status"] == "completed"
    assert snapshot["progress"]["processed_count"] == 2
    assert snapshot["progress"]["total_count"] == 2
    assert len(snapshot["results"]) == 2
    assert len(snapshot["alerts"]) == 1
    assert snapshot["latest_result"]["payload"]["source_name"] == "segment_0002.ts"
