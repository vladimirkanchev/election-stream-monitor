"""Behavior tests for the file-backed `SessionStore` adapter.

These tests stay focused on observable file-backed behavior. They use the store
API first, then compare selected reads with `session_io` so the adapter keeps
current parity without coupling the suite to private helper internals.
"""

import json
from dataclasses import replace
from pathlib import Path

import pytest

import config
from session_io import (
    append_result,
    is_session_cancel_requested,
    read_session_result_events,
    read_session_snapshot,
    request_session_cancel,
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


def test_file_session_store_keeps_append_order_when_result_timestamps_match(
    file_store: FileSessionStore,
) -> None:
    """Matching payload timestamps should not change append-only result history."""
    metadata = _metadata("session-contract-results-same-timestamp")
    first = ResultEvent(
        session_id=metadata.session_id,
        detector_id="video_metrics",
        payload={
            "timestamp_utc": "2026-07-01 10:00:00",
            "source_name": "clip.mp4 @ 00:00",
            "window_index": 0,
        },
    )
    second = ResultEvent(
        session_id=metadata.session_id,
        detector_id="video_blur",
        payload={
            "timestamp_utc": "2026-07-01 10:00:00",
            "source_name": "clip.mp4 @ 00:01",
            "window_index": 1,
        },
    )

    file_store.write_metadata(metadata)
    file_store.append_result(first)
    file_store.append_result(second)

    snapshot = file_store.read_snapshot(metadata.session_id)
    assert [row["detector_id"] for row in snapshot["results"]] == [
        "video_metrics",
        "video_blur",
    ]
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


def test_file_session_store_matches_missing_session_behavior(
    file_store: FileSessionStore,
) -> None:
    """Missing sessions should match the stable file-backed empty contract."""
    assert file_store.session_exists(MISSING_SESSION_ID) == session_exists(MISSING_SESSION_ID)
    assert file_store.read_snapshot(MISSING_SESSION_ID) == read_session_snapshot(MISSING_SESSION_ID)
    assert file_store.read_results(MISSING_SESSION_ID) == read_session_result_events(MISSING_SESSION_ID)


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


def test_file_session_store_round_trips_cancel_intent(
    file_store: FileSessionStore,
) -> None:
    """The file store should expose the current cancel-request signal."""
    session_id = "session-file-cancel-round-trip"

    assert file_store.is_cancel_requested(session_id) is False

    file_store.request_cancel(session_id)

    assert file_store.is_cancel_requested(session_id) is True


def test_file_session_store_matches_existing_cancel_helper_behavior(
    file_store: FileSessionStore,
) -> None:
    """Cancel methods should stay aligned with the legacy file helpers."""
    session_id = "session-file-cancel-parity"

    request_session_cancel(session_id)

    assert file_store.is_cancel_requested(session_id) == is_session_cancel_requested(session_id)


def test_file_session_store_request_cancel_delegates_to_existing_helper(
    file_store: FileSessionStore,
) -> None:
    """Store cancel writes should create the same file-backed marker."""
    session_id = "session-file-cancel-write"

    file_store.request_cancel(session_id)

    assert is_session_cancel_requested(session_id) is True


def test_file_session_store_request_cancel_preserves_marker_file_shape(
    file_store: FileSessionStore,
) -> None:
    """Store cancel writes should preserve the legacy marker payload on disk."""
    session_id = "session-file-cancel-marker-shape"

    file_store.request_cancel(session_id)

    marker_path = config.SESSION_OUTPUT_FOLDER / session_id / "cancel_requested.json"
    assert marker_path.exists()
    assert json.loads(marker_path.read_text(encoding="utf-8")) == {
        "session_id": session_id,
        "cancel_requested": True,
    }


def test_file_session_store_matches_invalid_top_level_snapshot_tolerance(
    file_store: FileSessionStore,
) -> None:
    """Malformed metadata or progress should degrade exactly like `session_io`."""
    session_id = "session-file-invalid-top"
    session_dir = config.SESSION_OUTPUT_FOLDER / session_id
    session_dir.mkdir(parents=True)
    (session_dir / "session.json").write_text(
        json.dumps(
            {
                "session_id": session_id,
                "mode": "video_segments",
                "input_path": "/tmp/input",
                "selected_detectors": ["video_metrics"],
                "status": "completed",
            }
        ),
        encoding="utf-8",
    )
    (session_dir / "progress.json").write_text(
        json.dumps(
            {
                "session_id": session_id,
                "status": "completed",
                "processed_count": 1,
                "total_count": 2,
                "current_item": "segment_0001.ts",
                "latest_result_detector": "video_metrics",
                "alert_count": 0,
                "last_updated_utc": "2026-04-04 18:00:00",
                "latest_result_detectors": ["video_metrics"],
            }
        ),
        encoding="utf-8",
    )

    assert file_store.read_snapshot(session_id) == read_session_snapshot(session_id)


def test_file_session_store_matches_malformed_result_log_tolerance(
    file_store: FileSessionStore,
) -> None:
    """Malformed result rows should be skipped with the same read shape and order."""
    session_id = "session-file-corrupt-jsonl"
    session_dir = config.SESSION_OUTPUT_FOLDER / session_id
    session_dir.mkdir(parents=True)
    (session_dir / "session.json").write_text(
        json.dumps(
            {
                "session_id": session_id,
                "mode": "video_segments",
                "input_path": "/tmp/input",
                "selected_detectors": ["video_metrics"],
                "status": "running",
            }
        ),
        encoding="utf-8",
    )
    (session_dir / "progress.json").write_text(
        json.dumps(
            {
                "session_id": session_id,
                "status": "running",
                "processed_count": 1,
                "total_count": 2,
                "current_item": "segment_0001.ts",
                "latest_result_detector": "video_metrics",
                "alert_count": 0,
                "last_updated_utc": "2026-04-04 18:00:00",
                "latest_result_detectors": ["video_metrics"],
                "status_reason": "running",
                "status_detail": None,
            }
        ),
        encoding="utf-8",
    )
    (session_dir / "results.jsonl").write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "session_id": session_id,
                        "detector_id": "video_metrics",
                        "payload": {"source_name": "segment_0001.ts", "window_index": 0},
                    }
                ),
                "{bad json",
                json.dumps({"session_id": session_id, "detector_id": ""}),
            ]
        ),
        encoding="utf-8",
    )

    assert file_store.read_results(session_id) == read_session_result_events(session_id)
    assert file_store.read_snapshot(session_id) == read_session_snapshot(session_id)


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
