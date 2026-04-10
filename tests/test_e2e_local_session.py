"""End-to-end local session test for the session file contract."""

from pathlib import Path

import config
from session_io import read_session_snapshot
from session_runner import run_local_session


def test_e2e_local_session_produces_frontend_readable_snapshot(
    monkeypatch, tmp_path: Path
) -> None:
    """A local run should produce session files readable by the frontend layer."""
    monkeypatch.setattr(config, "SESSION_OUTPUT_FOLDER", tmp_path / "sessions")

    input_dir = tmp_path / "segments"
    input_dir.mkdir()
    (input_dir / "segment_0001.ts").write_bytes(b"aa")
    (input_dir / "segment_0002.ts").write_bytes(b"bb")

    def fake_run_enabled_analyzers_bundle(
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

    monkeypatch.setattr(
        "session_runner.run_enabled_analyzers_bundle",
        fake_run_enabled_analyzers_bundle,
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
