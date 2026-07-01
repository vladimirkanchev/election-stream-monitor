"""Contract tests for durable session-store behavior.

These tests keep the PostgreSQL migration boundary small and storage-neutral.
"""

from typing import Protocol

from session_store import (
    RESULT_EVENT_PUBLIC_KEYS,
    RESULT_EVENT_SHARED_PAYLOAD_HINT_KEYS,
    SESSION_SNAPSHOT_KEYS,
    ResultEventPayload,
    SessionMetadataPayload,
    SessionProgressPayload,
    SessionStore,
    SessionStoreCancellationControl,
    SessionStoreReader,
    SessionStoreWriter,
    build_empty_session_snapshot_payload,
    build_latest_result_payload,
    build_session_snapshot_payload,
    is_missing_session_snapshot,
)

EXPECTED_READER_METHODS = {"session_exists", "read_snapshot", "read_results"}
EXPECTED_WRITER_METHODS = {"write_metadata", "write_progress", "append_result"}
EXPECTED_CANCELLATION_METHODS = {"request_cancel", "is_cancel_requested"}

NON_DURABLE_METHOD_NAMES = {
    "append_alert",
    "get_session_dir",
    "get_worker_log_path",
    "request_session_cancel",
    "append_seen_chunk_key",
    "read_seen_chunk_keys",
    "append_api_stream_seen_chunk_key",
    "read_api_stream_seen_chunk_keys",
}


def _protocol_methods(protocol: type[object]) -> set[str]:
    """Return public methods declared directly on a Protocol."""
    return {
        name
        for name, value in protocol.__dict__.items()
        if callable(value) and not name.startswith("_")
    }


def _metadata_payload(session_id: str) -> SessionMetadataPayload:
    """Build one valid metadata payload."""
    return {
        "session_id": session_id,
        "mode": "video_files",
        "input_path": "/tmp/clip.mp4",
        "selected_detectors": ["video_metrics"],
        "status": "running",
    }


def _result_payload(session_id: str, detector_id: str, window_index: int) -> ResultEventPayload:
    """Build one ordered detector-result payload."""
    return {
        "session_id": session_id,
        "detector_id": detector_id,
        "payload": {
            "timestamp_utc": "2026-07-01 10:00:00",
            "source_name": "segment_0001.ts",
            "window_index": window_index,
            "window_start_sec": float(window_index),
            "severity": "warning",
            "title": "Detector signal",
            "message": "Representative detector note",
        },
    }


def test_session_store_reader_keeps_minimal_read_model_contract() -> None:
    """Reader methods should not expose backend layout."""
    assert _protocol_methods(SessionStoreReader) == EXPECTED_READER_METHODS


def test_session_store_writer_keeps_minimal_lifecycle_write_contract() -> None:
    """Writer methods should not own runner lifecycle operations."""
    assert _protocol_methods(SessionStoreWriter) == EXPECTED_WRITER_METHODS


def test_session_store_cancellation_control_keeps_runtime_signal_minimal() -> None:
    """Cancel control should stay limited to one write and one boolean read."""
    assert _protocol_methods(SessionStoreCancellationControl) == EXPECTED_CANCELLATION_METHODS


def test_session_store_contract_excludes_unrelated_runtime_concerns() -> None:
    """Paths, replay keys, diagnostics, and alerts should stay outside the store."""
    method_names = _protocol_methods(SessionStoreReader) | _protocol_methods(SessionStoreWriter)

    assert method_names.isdisjoint(NON_DURABLE_METHOD_NAMES)


def test_session_store_combines_durable_reads_writes_and_cancel_signal() -> None:
    """The combined store should expose the narrow runtime cancel methods too."""
    assert SessionStore.__bases__ == (
        SessionStoreReader,
        SessionStoreWriter,
        SessionStoreCancellationControl,
        Protocol,
    )


def test_empty_session_snapshot_payload_preserves_missing_session_shape() -> None:
    """Missing sessions keep the stable empty snapshot shape."""
    snapshot = build_empty_session_snapshot_payload()

    assert tuple(snapshot.keys()) == SESSION_SNAPSHOT_KEYS
    assert is_missing_session_snapshot(snapshot)
    assert snapshot["session"] is None
    assert snapshot["progress"] is None
    assert snapshot["alerts"] == []
    assert snapshot["results"] == []
    assert snapshot["latest_result"] is None


def test_empty_session_snapshot_payload_returns_fresh_event_lists() -> None:
    """Empty snapshots should not share mutable alert/result lists."""
    first = build_empty_session_snapshot_payload()
    second = build_empty_session_snapshot_payload()

    first["alerts"].append({"title": "example"})
    first["results"].append(
        {
            "session_id": "session-1",
            "detector_id": "video_metrics",
            "payload": {"source_name": "clip.mp4"},
        }
    )

    assert second["alerts"] == []
    assert second["results"] == []


def test_missing_session_snapshot_is_based_on_session_payload_only() -> None:
    """A null session payload is the missing-session signal."""
    snapshot = build_empty_session_snapshot_payload()

    snapshot["session"] = _metadata_payload("session-known")

    assert not is_missing_session_snapshot(snapshot)


def test_session_snapshot_payload_derives_latest_result_from_append_order() -> None:
    """`latest_result` should come from the final ordered result row."""
    first = _result_payload("session-order", "video_metrics", 0)
    second = _result_payload("session-order", "video_blur", 1)

    snapshot = build_session_snapshot_payload(
        session=None,
        progress=None,
        alerts=[],
        results=[first, second],
    )

    assert snapshot["results"] == [first, second]
    assert snapshot["latest_result"] == second


def test_result_event_contract_stays_compact_while_allowing_shared_payload_hints() -> None:
    """The public result row stays small while shared nested hint keys remain available."""
    result = _result_payload("session-contract-result", "video_blur", 7)

    assert tuple(result.keys()) == RESULT_EVENT_PUBLIC_KEYS
    assert RESULT_EVENT_SHARED_PAYLOAD_HINT_KEYS == (
        "timestamp_utc",
        "detector_name",
        "source_name",
        "window_index",
        "window_start_sec",
        "title",
        "message",
        "severity",
    )
    assert result["payload"]["source_name"] == "segment_0001.ts"
    assert result["payload"]["window_index"] == 7


def test_latest_result_payload_uses_append_order_not_timestamp_preference() -> None:
    """The latest result should come from history order even when timestamps collide."""
    first = _result_payload("session-order", "video_metrics", 0)
    second = _result_payload("session-order", "video_blur", 1)
    first["payload"]["timestamp_utc"] = "2026-07-01 10:00:00"
    second["payload"]["timestamp_utc"] = "2026-07-01 10:00:00"

    assert build_latest_result_payload([first, second]) == second


def test_session_snapshot_payload_treats_progress_as_latest_only() -> None:
    """Progress should be latest-only, not appended history."""
    progress: SessionProgressPayload = {
        "session_id": "session-progress",
        "status": "running",
        "processed_count": 2,
        "total_count": 3,
        "current_item": "segment_0002.ts",
        "latest_result_detector": "video_metrics",
        "alert_count": 1,
        "last_updated_utc": "2026-06-29 10:00:00",
        "latest_result_detectors": ["video_metrics"],
        "status_reason": "running",
        "status_detail": None,
    }

    snapshot = build_session_snapshot_payload(
        session=None,
        progress=progress,
        alerts=[],
        results=[],
    )

    assert snapshot["progress"] == progress
    assert "progress_history" not in snapshot
