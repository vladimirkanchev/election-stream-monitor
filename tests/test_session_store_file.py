"""Behavior tests for the file-backed `SessionStore` adapter.

These tests use the store API first, with a few parity checks against
`session_io` to prove the adapter preserves current behavior.
"""

from dataclasses import replace
from pathlib import Path

import config
import pytest
from session_io import (
    append_result,
    read_session_result_events,
    read_session_snapshot,
    session_exists,
    write_session_metadata,
    write_session_progress,
)
from session_models import ResultEvent, SessionMetadata, SessionProgress, SessionStatus
from session_store_file import FileSessionStore

MISSING_SESSION_ID = "session-missing"


def _metadata(session_id: str, *, status: SessionStatus = "running") -> SessionMetadata:
    """Build compact session metadata."""
    return SessionMetadata(
        session_id=session_id,
        mode="video_files",
        input_path="/tmp/clip.mp4",
        selected_detectors=["video_metrics"],
        status=status,
    )


def _result(session_id: str, detector_id: str, window_index: int) -> ResultEvent:
    """Build one ordered detector result."""
    return ResultEvent(
        session_id=session_id,
        detector_id=detector_id,
        payload={"source_name": f"clip.mp4 @ 00:0{window_index}", "window_index": window_index},
    )


def _running_progress(session_id: str, *, processed_count: int) -> SessionProgress:
    """Build latest progress without storage assumptions."""
    return SessionProgress(
        session_id=session_id,
        status="running",
        processed_count=processed_count,
        total_count=3,
        current_item=f"segment_{processed_count:04d}.ts",
        latest_result_detector="video_metrics",
        alert_count=0,
        last_updated_utc=f"2026-06-29 10:00:0{processed_count}",
        latest_result_detectors=["video_metrics"],
        status_reason="running",
        status_detail=None,
    )


@pytest.fixture
def file_store(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> FileSessionStore:
    """Return a file store isolated from real session output."""
    monkeypatch.setattr(config, "SESSION_OUTPUT_FOLDER", tmp_path)
    return FileSessionStore()


def test_file_session_store_preserves_missing_session_contract(
    file_store: FileSessionStore,
) -> None:
    """Missing sessions should read as the empty snapshot shape."""
    snapshot = file_store.read_snapshot(MISSING_SESSION_ID)

    assert file_store.session_exists(MISSING_SESSION_ID) is False
    assert snapshot == {
        "session": None,
        "progress": None,
        "alerts": [],
        "results": [],
        "latest_result": None,
    }


def test_file_session_store_round_trips_contract_payloads(
    file_store: FileSessionStore,
) -> None:
    """Store writes should rebuild the public snapshot read model."""
    metadata = _metadata("session-contract-round-trip", status="running")
    progress = _running_progress(metadata.session_id, processed_count=1)
    result = _result(metadata.session_id, "video_metrics", 1)

    file_store.write_metadata(metadata)
    file_store.write_progress(progress)
    file_store.append_result(result)

    snapshot = file_store.read_snapshot(metadata.session_id)
    assert file_store.session_exists(metadata.session_id) is True
    assert snapshot["session"] == metadata.to_dict()
    assert snapshot["progress"] == progress.to_dict()
    assert snapshot["results"] == [result.to_dict()]
    assert snapshot["latest_result"] == result.to_dict()


def test_file_session_store_preserves_result_order_and_latest_result(
    file_store: FileSessionStore,
) -> None:
    """Ordered appends should drive both result reads and `latest_result`."""
    metadata = _metadata("session-contract-results")
    first = _result(metadata.session_id, "video_metrics", 0)
    second = _result(metadata.session_id, "video_blur", 1)

    file_store.write_metadata(metadata)
    file_store.append_result(first)
    file_store.append_result(second)

    assert file_store.read_results(metadata.session_id) == [first.to_dict(), second.to_dict()]
    snapshot = file_store.read_snapshot(metadata.session_id)
    assert snapshot["results"] == [first.to_dict(), second.to_dict()]
    assert snapshot["latest_result"] == second.to_dict()


def test_file_session_store_keeps_progress_latest_only(
    file_store: FileSessionStore,
) -> None:
    """Progress writes should replace the latest read model, not append history."""
    metadata = _metadata("session-contract-progress")
    first = _running_progress(metadata.session_id, processed_count=1)
    second = _running_progress(metadata.session_id, processed_count=2)

    file_store.write_metadata(metadata)
    file_store.write_progress(first)
    file_store.write_progress(second)

    snapshot = file_store.read_snapshot(metadata.session_id)
    assert snapshot["progress"] == second.to_dict()
    assert "progress_history" not in snapshot


def test_file_session_store_preserves_terminal_progress_contract(
    file_store: FileSessionStore,
) -> None:
    """Terminal progress should remain readable as the latest snapshot."""
    metadata = _metadata("session-contract-terminal", status="completed")
    completed = replace(
        SessionProgress.initial(session_id=metadata.session_id, total_count=2),
        status="completed",
        processed_count=2,
        current_item="clip.mp4",
        status_reason="completed",
        status_detail="session completed",
    )

    file_store.write_metadata(metadata)
    file_store.write_progress(completed)

    snapshot = file_store.read_snapshot(metadata.session_id)
    assert snapshot["session"] == metadata.to_dict()
    assert snapshot["progress"] == completed.to_dict()


def test_file_session_store_matches_existing_snapshot_behavior(
    file_store: FileSessionStore,
) -> None:
    """The adapter should expose the same snapshot as `session_io`."""
    metadata = _metadata("session-file-store")
    result = _result(metadata.session_id, "video_metrics", 0)

    write_session_metadata(metadata)
    write_session_progress(SessionProgress.initial(session_id=metadata.session_id, total_count=2))
    append_result(result)

    assert file_store.read_snapshot(metadata.session_id) == read_session_snapshot(metadata.session_id)


def test_file_session_store_matches_existing_result_order_behavior(
    file_store: FileSessionStore,
) -> None:
    """The adapter should preserve existing result append order."""
    metadata = _metadata("session-file-results")
    write_session_metadata(metadata)

    first = _result(metadata.session_id, "video_metrics", 0)
    second = _result(metadata.session_id, "video_blur", 1)
    append_result(first)
    append_result(second)

    assert file_store.read_results(metadata.session_id) == read_session_result_events(
        metadata.session_id
    )


def test_file_session_store_write_methods_delegate_to_existing_helpers(
    file_store: FileSessionStore,
) -> None:
    """Adapter writes should create the same durable session state."""
    metadata = _metadata("session-file-writes", status="pending")
    progress = SessionProgress.initial(session_id=metadata.session_id, total_count=1)
    result = _result(metadata.session_id, "video_metrics", 0)

    file_store.write_metadata(metadata)
    file_store.write_progress(progress)
    file_store.append_result(result)

    assert session_exists(metadata.session_id) is True
    snapshot = read_session_snapshot(metadata.session_id)
    assert snapshot["session"] == metadata.to_dict()
    assert snapshot["progress"] == progress.to_dict()
    assert snapshot["latest_result"] == result.to_dict()
