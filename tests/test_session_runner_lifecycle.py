"""Focused tests for pending/running lifecycle helpers.

These cases stay intentionally small. They check the helper-module contract
directly, while larger session lifecycle behavior lives in the black-box
runner suites.
"""

from pathlib import Path

import config
from session_io import initialize_session, read_session_snapshot, write_session_progress
from session_models import SessionMetadata, SessionProgress
import session_runner_lifecycle


def _configure_session_output(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(config, "SESSION_OUTPUT_FOLDER", tmp_path / "sessions")


def _persist_session_state(metadata: SessionMetadata, progress: SessionProgress) -> None:
    initialize_session(metadata)
    write_session_progress(progress)


def test_persist_pending_metadata_writes_pending_session_snapshot(
    monkeypatch, tmp_path: Path
) -> None:
    _configure_session_output(monkeypatch, tmp_path)

    metadata = session_runner_lifecycle.persist_pending_metadata(
        mode="video_segments",
        input_path=tmp_path / "segments",
        selected_detectors=["video_metrics"],
        session_id="session-lifecycle-persist-pending",
    )

    snapshot = read_session_snapshot(metadata.session_id)

    assert metadata.status == "pending"
    assert snapshot["session"]["status"] == "pending"
    assert snapshot["session"]["input_path"] == str(tmp_path / "segments")


def test_initialize_pending_session_persists_pending_metadata_and_progress(
    monkeypatch, tmp_path: Path
) -> None:
    _configure_session_output(monkeypatch, tmp_path)

    metadata, progress = session_runner_lifecycle.initialize_pending_session(
        mode="video_segments",
        input_path=tmp_path / "segments",
        selected_detectors=["video_metrics"],
        session_id="session-lifecycle-pending",
    )

    snapshot = read_session_snapshot("session-lifecycle-pending")

    assert metadata.status == "pending"
    assert metadata.input_path == str(tmp_path / "segments")
    assert progress.status == "pending"
    assert progress.total_count == 0
    assert snapshot["session"]["status"] == "pending"
    assert snapshot["progress"]["status"] == "pending"
    assert snapshot["progress"]["status_reason"] == "pending"


def test_start_running_session_uses_default_progress_builder_and_persists_running_state(
    monkeypatch, tmp_path: Path
) -> None:
    _configure_session_output(monkeypatch, tmp_path)

    metadata = SessionMetadata(
        session_id="session-lifecycle-running",
        mode="video_files",
        input_path="sample.mp4",
        selected_detectors=["video_metrics"],
        status="pending",
    )
    progress = SessionProgress.initial(session_id=metadata.session_id, total_count=0)
    _persist_session_state(metadata, progress)

    updated_metadata, updated_progress = session_runner_lifecycle.start_running_session(
        metadata,
        progress,
        total_count=3,
    )

    snapshot = read_session_snapshot(metadata.session_id)

    assert updated_metadata.status == "running"
    assert updated_progress.status == "running"
    assert updated_progress.total_count == 3
    assert updated_progress.processed_count == 0
    assert snapshot["session"]["status"] == "running"
    assert snapshot["progress"]["status"] == "running"
    assert snapshot["progress"]["total_count"] == 3
    assert snapshot["progress"]["status_reason"] == "running"
