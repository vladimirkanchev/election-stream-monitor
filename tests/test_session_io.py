"""Tests for session file helpers."""

import json
from pathlib import Path

import config
from session_io import (
    append_alert,
    append_result,
    initialize_session,
    is_session_cancel_requested,
    read_session_snapshot,
    request_session_cancel,
    update_session_status,
    write_session_progress,
)
from session_models import (
    AlertEvent,
    InvalidSessionProgressError,
    InvalidSessionTransitionError,
    ResultEvent,
    SessionMetadata,
    SessionProgress,
)


def test_session_io_writes_and_reads_snapshot(monkeypatch, tmp_path: Path) -> None:
    """Session helpers should persist metadata, progress, alerts, and results."""
    monkeypatch.setattr(config, "SESSION_OUTPUT_FOLDER", tmp_path)

    metadata = SessionMetadata(
        session_id="session-123",
        mode="video_segments",
        input_path="/tmp/input",
        selected_detectors=["video_metrics"],
        status="pending",
    )
    initialize_session(metadata)
    write_session_progress(SessionProgress.initial(session_id="session-123", total_count=3))
    append_result(
        ResultEvent(
            session_id="session-123",
            detector_id="video_metrics",
            payload={"source_name": "segment_0001.ts"},
        )
    )
    append_alert(
        AlertEvent(
            session_id="session-123",
            timestamp_utc="2026-03-30 12:00:00",
            detector_id="video_metrics",
            title="Black screen detected",
            message="Black content detected.",
            severity="warning",
            source_name="segment_0001.ts",
        )
    )

    snapshot = read_session_snapshot("session-123")

    assert snapshot["session"]["session_id"] == "session-123"
    assert snapshot["progress"]["total_count"] == 3
    assert snapshot["alerts"][0]["title"] == "Black screen detected"
    assert snapshot["latest_result"]["payload"]["source_name"] == "segment_0001.ts"


def test_session_io_records_cancel_request(monkeypatch, tmp_path: Path) -> None:
    """Cancel requests should be persisted in the session directory."""
    monkeypatch.setattr(config, "SESSION_OUTPUT_FOLDER", tmp_path)

    request_session_cancel("session-456")

    assert is_session_cancel_requested("session-456") is True


def test_session_snapshot_tolerates_invalid_json_file(
    monkeypatch, tmp_path: Path
) -> None:
    """Snapshot reads should not crash if one JSON file is temporarily unreadable."""
    monkeypatch.setattr(config, "SESSION_OUTPUT_FOLDER", tmp_path)

    session_dir = tmp_path / "session-789"
    session_dir.mkdir(parents=True)
    (session_dir / "session.json").write_text(
        json.dumps(
            {
                "session_id": "session-789",
                "mode": "video_segments",
                "input_path": "/tmp/input",
                "selected_detectors": [],
                "status": "running",
            }
        ),
        encoding="utf-8",
    )
    (session_dir / "progress.json").write_text("", encoding="utf-8")

    snapshot = read_session_snapshot("session-789")

    assert snapshot["session"]["session_id"] == "session-789"
    assert snapshot["progress"] is None


def test_read_session_snapshot_returns_stable_empty_contract_for_missing_session(
    monkeypatch, tmp_path: Path
) -> None:
    """Snapshot reads should always expose the same top-level contract keys."""
    monkeypatch.setattr(config, "SESSION_OUTPUT_FOLDER", tmp_path)

    snapshot = read_session_snapshot("session-missing")

    assert snapshot == {
        "session": None,
        "progress": None,
        "alerts": [],
        "results": [],
        "latest_result": None,
    }


def test_session_snapshot_preserves_result_order_and_latest_result(
    monkeypatch, tmp_path: Path
) -> None:
    """Results should remain append-ordered and latest_result should mirror the last one."""
    monkeypatch.setattr(config, "SESSION_OUTPUT_FOLDER", tmp_path)

    metadata = SessionMetadata(
        session_id="session-order",
        mode="video_files",
        input_path="/tmp/clip.mp4",
        selected_detectors=["video_blur"],
        status="running",
    )
    initialize_session(metadata)
    write_session_progress(SessionProgress.initial(session_id="session-order", total_count=2))
    append_result(
        ResultEvent(
            session_id="session-order",
            detector_id="video_blur",
            payload={
                "source_name": "clip.mp4 @ 00:00",
                "window_index": 0,
                "window_start_sec": 0.0,
            },
        )
    )
    append_result(
        ResultEvent(
            session_id="session-order",
            detector_id="video_blur",
            payload={
                "source_name": "clip.mp4 @ 00:01",
                "window_index": 1,
                "window_start_sec": 1.0,
            },
        )
    )

    snapshot = read_session_snapshot("session-order")

    assert [result["payload"]["window_index"] for result in snapshot["results"]] == [0, 1]
    assert snapshot["latest_result"] == snapshot["results"][-1]
    assert snapshot["latest_result"]["payload"]["source_name"] == "clip.mp4 @ 00:01"


def test_session_snapshot_preserves_alert_fields_and_append_order(
    monkeypatch, tmp_path: Path
) -> None:
    """Alert events should keep their playback-alignment fields in append order."""
    monkeypatch.setattr(config, "SESSION_OUTPUT_FOLDER", tmp_path)

    metadata = SessionMetadata(
        session_id="session-alerts",
        mode="video_segments",
        input_path="/tmp/segments",
        selected_detectors=["video_metrics"],
        status="running",
    )
    initialize_session(metadata)
    write_session_progress(SessionProgress.initial(session_id="session-alerts", total_count=2))
    append_alert(
        AlertEvent(
            session_id="session-alerts",
            timestamp_utc="2026-03-30 12:00:00",
            detector_id="video_metrics",
            title="Black screen detected",
            message="First segment alert.",
            severity="warning",
            source_name="segment_0001.ts",
            window_index=0,
            window_start_sec=0.0,
        )
    )
    append_alert(
        AlertEvent(
            session_id="session-alerts",
            timestamp_utc="2026-03-30 12:00:01",
            detector_id="video_metrics",
            title="Black screen detected",
            message="Second segment alert.",
            severity="warning",
            source_name="segment_0002.ts",
            window_index=1,
            window_start_sec=1.0,
        )
    )

    snapshot = read_session_snapshot("session-alerts")

    assert [alert["source_name"] for alert in snapshot["alerts"]] == [
        "segment_0001.ts",
        "segment_0002.ts",
    ]
    assert [alert["window_index"] for alert in snapshot["alerts"]] == [0, 1]
    assert [alert["window_start_sec"] for alert in snapshot["alerts"]] == [0.0, 1.0]


def test_update_session_status_rejects_invalid_terminal_transition(
    monkeypatch, tmp_path: Path
) -> None:
    """Completed sessions should not be allowed to transition back to running."""
    monkeypatch.setattr(config, "SESSION_OUTPUT_FOLDER", tmp_path)

    metadata = SessionMetadata(
        session_id="session-transition",
        mode="video_segments",
        input_path="/tmp/input",
        selected_detectors=["video_metrics"],
        status="completed",
    )

    try:
        update_session_status(metadata, "running")
    except InvalidSessionTransitionError as error:
        assert "completed -> running" in str(error)
    else:
        raise AssertionError("Expected invalid session transitions to be rejected")


def test_write_session_progress_rejects_completed_progress_with_missing_work(
    monkeypatch, tmp_path: Path
) -> None:
    """Completed progress should not be persisted when not all work has been processed."""
    monkeypatch.setattr(config, "SESSION_OUTPUT_FOLDER", tmp_path)

    progress = SessionProgress(
        session_id="session-progress",
        status="completed",
        processed_count=1,
        total_count=2,
        current_item="segment_0001.ts",
        latest_result_detector="video_metrics",
        alert_count=0,
        last_updated_utc="2026-04-04 18:00:00",
        latest_result_detectors=["video_metrics"],
    )

    try:
        write_session_progress(progress)
    except InvalidSessionProgressError as error:
        assert "completed session progress must report all items as processed" in str(error)
    else:
        raise AssertionError("Expected invalid completed progress to be rejected")


def test_session_snapshot_skips_malformed_jsonl_lines_and_invalid_event_payloads(
    monkeypatch, tmp_path: Path
) -> None:
    """Corrupted or malformed JSONL events should be ignored while preserving order."""
    monkeypatch.setattr(config, "SESSION_OUTPUT_FOLDER", tmp_path)

    session_dir = tmp_path / "session-corrupt-jsonl"
    session_dir.mkdir(parents=True)
    (session_dir / "session.json").write_text(
        json.dumps(
            {
                "session_id": "session-corrupt-jsonl",
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
                "session_id": "session-corrupt-jsonl",
                "status": "running",
                "processed_count": 1,
                "total_count": 2,
                "current_item": "segment_0001.ts",
                "latest_result_detector": "video_metrics",
                "alert_count": 1,
                "last_updated_utc": "2026-04-04 18:00:00",
                "latest_result_detectors": ["video_metrics"],
            }
        ),
        encoding="utf-8",
    )
    (session_dir / "results.jsonl").write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "session_id": "session-corrupt-jsonl",
                        "detector_id": "video_metrics",
                        "payload": {"source_name": "segment_0001.ts"},
                    }
                ),
                "{bad json",
                json.dumps({"session_id": "session-corrupt-jsonl", "detector_id": ""}),
            ]
        ),
        encoding="utf-8",
    )
    (session_dir / "alerts.jsonl").write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "session_id": "session-corrupt-jsonl",
                        "timestamp_utc": "2026-04-04 18:00:00",
                        "detector_id": "video_metrics",
                        "title": "Black screen detected",
                        "message": "First alert.",
                        "severity": "warning",
                        "source_name": "segment_0001.ts",
                    }
                ),
                json.dumps({"session_id": "session-corrupt-jsonl", "severity": "warning"}),
            ]
        ),
        encoding="utf-8",
    )

    snapshot = read_session_snapshot("session-corrupt-jsonl")

    assert len(snapshot["results"]) == 1
    assert snapshot["latest_result"] == snapshot["results"][0]
    assert len(snapshot["alerts"]) == 1
    assert snapshot["alerts"][0]["source_name"] == "segment_0001.ts"


def test_session_snapshot_ignores_invalid_metadata_and_progress_payloads(
    monkeypatch, tmp_path: Path
) -> None:
    """Corrupted top-level session files should degrade to stable null fields."""
    monkeypatch.setattr(config, "SESSION_OUTPUT_FOLDER", tmp_path)

    session_dir = tmp_path / "session-invalid-top"
    session_dir.mkdir(parents=True)
    (session_dir / "session.json").write_text(
        json.dumps(
            {
                "session_id": "session-invalid-top",
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
                "session_id": "session-invalid-top",
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

    snapshot = read_session_snapshot("session-invalid-top")

    assert snapshot["session"] is not None
    assert snapshot["progress"] is None
