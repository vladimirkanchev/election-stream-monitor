"""Tests for session file helpers and the snapshot-facing alert seam.

This suite still owns the broader file-backed session contract while alert
persistence now flows through the shared store seam.
"""

import json
from collections.abc import Iterator
from pathlib import Path

import pytest

import config
import session_alert_store
from session_alert_incidents import build_session_timeline
from session_alert_store import clear_default_session_alert_store_cache
from session_alerts import read_session_alert_events, summarize_session_alert_events
from session_io import (
    append_alert,
    append_result,
    get_worker_log_path,
    initialize_session,
    is_session_cancel_requested,
    read_session_snapshot,
    request_session_cancel,
    update_session_status,
    write_session_progress,
)
from session_models import (
    AlertEvent,
    InvalidResultEventError,
    InvalidSessionProgressError,
    InvalidSessionTransitionError,
    ResultEvent,
    SessionMetadata,
    SessionProgress,
    SessionStatus,
)
from tests.session_alert_test_support import (
    StaticAlertStore,
    build_normalized_alert,
    install_runtime_postgres_session_alerts,
    select_runtime_postgres_store,
)


@pytest.fixture(autouse=True)
def _clear_default_alert_store_cache() -> Iterator[None]:
    """Keep runtime-selected default-store caching isolated in snapshot tests."""
    clear_default_session_alert_store_cache()
    yield
    clear_default_session_alert_store_cache()


def _session_metadata(
    session_id: str,
    *,
    mode: str = "video_segments",
    input_path: str = "/tmp/input",
    selected_detectors: list[str] | None = None,
    status: SessionStatus = "running",
) -> SessionMetadata:
    """Build one small metadata fixture for snapshot and lifecycle tests."""
    return SessionMetadata(
        session_id=session_id,
        mode=mode,
        input_path=input_path,
        selected_detectors=selected_detectors or ["video_metrics"],
        status=status,
    )


def _snapshot_alert(
    *,
    session_id: str,
    timestamp_utc: str,
    source_name: str,
    message: str,
    window_index: int | None = None,
    window_start_sec: float | None = None,
) -> AlertEvent:
    """Build one alert event using the stable snapshot defaults in this suite."""
    return AlertEvent(
        session_id=session_id,
        timestamp_utc=timestamp_utc,
        detector_id="video_metrics",
        title="Black screen detected",
        message=message,
        severity="warning",
        source_name=source_name,
        window_index=window_index,
        window_start_sec=window_start_sec,
    )


def _status_transition_metadata(current_status: SessionStatus, next_status: SessionStatus) -> SessionMetadata:
    """Build one metadata fixture for lifecycle-transition persistence checks."""
    return _session_metadata(
        f"session-{current_status}-to-{next_status}",
        status=current_status,
    )


def _empty_snapshot_contract() -> dict[str, object]:
    """Build the stable empty snapshot shape used across this suite."""
    return {
        "session": None,
        "progress": None,
        "alerts": [],
        "results": [],
        "latest_result": None,
    }


def test_session_io_writes_and_reads_snapshot(monkeypatch, tmp_path: Path) -> None:
    """Session helpers should persist metadata, progress, alerts, and results."""
    monkeypatch.setattr(config, "SESSION_OUTPUT_FOLDER", tmp_path)

    metadata = _session_metadata("session-123", status="pending")
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
        _snapshot_alert(
            session_id="session-123",
            timestamp_utc="2026-03-30 12:00:00",
            source_name="segment_0001.ts",
            message="Black content detected.",
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


def test_get_worker_log_path_is_session_scoped(monkeypatch, tmp_path: Path) -> None:
    """Worker logs should live beside other session artifacts in the session directory."""
    monkeypatch.setattr(config, "SESSION_OUTPUT_FOLDER", tmp_path)

    assert get_worker_log_path("session-456") == tmp_path / "session-456" / "worker.log"


def test_request_session_cancel_is_idempotent_for_repeated_requests(
    monkeypatch, tmp_path: Path
) -> None:
    """Repeated cancel requests should keep the same persisted intent."""
    monkeypatch.setattr(config, "SESSION_OUTPUT_FOLDER", tmp_path)

    first_path = request_session_cancel("session-repeat-cancel")
    second_path = request_session_cancel("session-repeat-cancel")

    assert first_path == second_path
    assert json.loads(first_path.read_text(encoding="utf-8")) == {
        "session_id": "session-repeat-cancel",
        "cancel_requested": True,
    }


def test_request_session_cancel_remains_file_oriented_and_tolerant(
    monkeypatch, tmp_path: Path
) -> None:
    """Cancel marker writes should stay independent of persisted session state."""
    monkeypatch.setattr(config, "SESSION_OUTPUT_FOLDER", tmp_path)

    request_path = request_session_cancel("session-missing-or-terminal")

    assert request_path.exists()
    assert json.loads(request_path.read_text(encoding="utf-8")) == {
        "session_id": "session-missing-or-terminal",
        "cancel_requested": True,
    }


def test_request_session_cancel_rejects_session_id_path_traversal(
    monkeypatch, tmp_path: Path
) -> None:
    """Session helpers should fail closed when a session id tries to escape the output root."""
    monkeypatch.setattr(config, "SESSION_OUTPUT_FOLDER", tmp_path)

    with pytest.raises(ValueError, match="single safe path component"):
        request_session_cancel("../escape")


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


def test_session_snapshot_tolerates_file_vanishing_after_the_exists_check(
    monkeypatch, tmp_path: Path
) -> None:
    """Snapshot reads should fail closed if a file disappears between existence and read."""
    monkeypatch.setattr(config, "SESSION_OUTPUT_FOLDER", tmp_path)

    session_dir = tmp_path / "session-race"
    session_dir.mkdir(parents=True)
    metadata_path = session_dir / "session.json"
    metadata_path.write_text(
        json.dumps(
            {
                "session_id": "session-race",
                "mode": "video_segments",
                "input_path": "/tmp/input",
                "selected_detectors": [],
                "status": "running",
            }
        ),
        encoding="utf-8",
    )

    original_read_text = Path.read_text

    def flaky_read_text(self: Path, *args, **kwargs):
        if self == metadata_path:
            raise OSError("file disappeared mid-read")
        return original_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", flaky_read_text)

    snapshot = read_session_snapshot("session-race")

    assert snapshot["session"] is None
    assert snapshot["progress"] is None


def test_read_session_snapshot_returns_stable_empty_contract_for_missing_session(
    monkeypatch, tmp_path: Path
) -> None:
    """Snapshot reads should always expose the same top-level contract keys."""
    monkeypatch.setattr(config, "SESSION_OUTPUT_FOLDER", tmp_path)

    snapshot = read_session_snapshot("session-missing")

    assert snapshot == _empty_snapshot_contract()


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


def test_append_result_rejects_invalid_shared_payload_hint_types(
    monkeypatch, tmp_path: Path
) -> None:
    """Result writes should fail closed when shared payload hints use the wrong types."""
    monkeypatch.setattr(config, "SESSION_OUTPUT_FOLDER", tmp_path)

    metadata = _session_metadata("session-invalid-result")
    initialize_session(metadata)

    with pytest.raises(
        InvalidResultEventError,
        match="window_index must be an int",
    ):
        append_result(
            ResultEvent(
                session_id="session-invalid-result",
                detector_id="video_metrics",
                payload={
                    "source_name": "segment_0001.ts",
                    "window_index": "0",
                },
            )
        )


def test_session_snapshot_preserves_alert_fields_and_append_order(
    monkeypatch, tmp_path: Path
) -> None:
    """Alert events should keep their playback-alignment fields in append order."""
    monkeypatch.setattr(config, "SESSION_OUTPUT_FOLDER", tmp_path)

    metadata = _session_metadata(
        "session-alerts",
        input_path="/tmp/segments",
    )
    initialize_session(metadata)
    write_session_progress(SessionProgress.initial(session_id="session-alerts", total_count=2))
    append_alert(
        _snapshot_alert(
            session_id="session-alerts",
            timestamp_utc="2026-03-30 12:00:00",
            message="First segment alert.",
            source_name="segment_0001.ts",
            window_index=0,
            window_start_sec=0.0,
        )
    )
    append_alert(
        _snapshot_alert(
            session_id="session-alerts",
            timestamp_utc="2026-03-30 12:00:01",
            message="Second segment alert.",
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


def test_session_snapshot_reads_alerts_through_the_default_alert_store_seam(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Snapshots should source alerts from the active alert store, not only JSONL."""
    monkeypatch.setattr(config, "SESSION_OUTPUT_FOLDER", tmp_path)

    metadata = _session_metadata(
        "session-snapshot-store-read",
        input_path="/tmp/segments",
    )
    initialize_session(metadata)
    write_session_progress(
        SessionProgress.initial(session_id="session-snapshot-store-read", total_count=1)
    )

    class FakeAlertStore:
        def append_alert(self, event: AlertEvent) -> None:  # pragma: no cover - defensive only
            raise AssertionError("snapshot test should not append alerts")

        def read_session_alert_events(self, session_id: str) -> list[dict[str, object]]:
            assert session_id == "session-snapshot-store-read"
            return [
                {
                    "session_id": session_id,
                    "timestamp_utc": "2026-05-19 10:00:00",
                    "detector_id": "video_metrics",
                    "title": "Black screen detected",
                    "message": "Returned by the active alert store seam.",
                    "severity": "warning",
                    "source_name": "segment_0001.ts",
                    "window_index": None,
                    "window_start_sec": None,
                }
            ]

    monkeypatch.setattr(session_alert_store, "DEFAULT_SESSION_ALERT_STORE", FakeAlertStore())

    snapshot = read_session_snapshot("session-snapshot-store-read")

    assert snapshot["alerts"] == [
        {
            "session_id": "session-snapshot-store-read",
            "timestamp_utc": "2026-05-19 10:00:00",
            "detector_id": "video_metrics",
            "title": "Black screen detected",
            "message": "Returned by the active alert store seam.",
            "severity": "warning",
            "source_name": "segment_0001.ts",
            "window_index": None,
            "window_start_sec": None,
        }
    ]


def test_session_snapshot_propagates_unexpected_runtime_alert_store_failures(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Unexpected alert-store failures should stay visible instead of being flattened."""
    monkeypatch.setattr(config, "SESSION_OUTPUT_FOLDER", tmp_path)

    metadata = _session_metadata("session-snapshot-store-failure")
    initialize_session(metadata)

    class FailingAlertStore:
        def append_alert(self, event: AlertEvent) -> None:  # pragma: no cover - defensive only
            raise AssertionError("snapshot failure test should not append alerts")

        def read_session_alert_events(self, session_id: str) -> list[dict[str, object]]:
            assert session_id == "session-snapshot-store-failure"
            raise RuntimeError("database read failed")

    monkeypatch.setattr(session_alert_store, "DEFAULT_SESSION_ALERT_STORE", FailingAlertStore())

    with pytest.raises(RuntimeError, match="database read failed"):
        read_session_snapshot("session-snapshot-store-failure")


def test_session_snapshot_keeps_known_session_empty_alerts_in_runtime_postgres_mode(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Known sessions without alerts should still expose ``alerts: []`` in Postgres mode."""
    session_id = "session-snapshot-runtime-postgres-empty"
    monkeypatch.setattr(config, "SESSION_OUTPUT_FOLDER", tmp_path)
    install_runtime_postgres_session_alerts(
        monkeypatch,
        tmp_path,
        session_id=session_id,
        alerts=[],
    )
    snapshot = read_session_snapshot(session_id)

    assert snapshot["session"] is not None
    assert snapshot["alerts"] == []


def test_session_snapshot_ignores_store_alerts_when_session_metadata_is_missing(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Snapshot reads should stay empty when session metadata is missing, even if the store has alerts."""
    session_id = "session-snapshot-missing-metadata-store-alerts"
    monkeypatch.setattr(config, "SESSION_OUTPUT_FOLDER", tmp_path)
    select_runtime_postgres_store(
        monkeypatch,
        StaticAlertStore(
            session_id,
            [
                build_normalized_alert(
                    session_id,
                    timestamp_utc="2026-05-19 23:30:00",
                    detector_id="video_metrics",
                    title="Should stay hidden",
                    message="Metadata still gates snapshot visibility.",
                    severity="warning",
                    source_name="segment_0001.ts",
                )
            ],
        ),
    )
    snapshot = read_session_snapshot(session_id)

    assert snapshot == _empty_snapshot_contract()


def test_session_snapshot_ignores_store_alerts_when_session_metadata_is_malformed(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Malformed session metadata should still gate snapshot alerts even when the active store is healthy."""
    session_id = "session-snapshot-malformed-metadata-store-alerts"
    monkeypatch.setattr(config, "SESSION_OUTPUT_FOLDER", tmp_path)
    session_dir = tmp_path / session_id
    session_dir.mkdir(parents=True)
    (session_dir / "session.json").write_text(
        json.dumps(
            {
                "session_id": session_id,
                "mode": "video_segments",
                "input_path": "/tmp/input",
                "selected_detectors": ["video_metrics"],
                "status": "not-a-real-status",
            }
        ),
        encoding="utf-8",
    )
    select_runtime_postgres_store(
        monkeypatch,
        StaticAlertStore(
            session_id,
            [
                build_normalized_alert(
                    session_id,
                    timestamp_utc="2026-05-19 23:35:00",
                    detector_id="video_metrics",
                    title="Should stay hidden",
                    message="Malformed metadata still wins for snapshot visibility.",
                    severity="warning",
                    source_name="segment_0001.ts",
                )
            ],
        ),
    )
    snapshot = read_session_snapshot(session_id)

    assert snapshot == _empty_snapshot_contract()


def test_session_snapshot_keeps_file_backed_results_and_seam_backed_alerts_together_in_postgres_mode(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Snapshot reads should preserve the intended hybrid contract in Postgres mode."""
    session_id = "session-snapshot-runtime-postgres-hybrid"
    monkeypatch.setattr(config, "SESSION_OUTPUT_FOLDER", tmp_path)
    metadata = _session_metadata(session_id)
    initialize_session(metadata)
    write_session_progress(SessionProgress.initial(session_id=session_id, total_count=1))
    append_result(
        ResultEvent(
            session_id=session_id,
            detector_id="video_metrics",
            payload={"source_name": "segment_0001.ts", "black_ratio": 0.8},
        )
    )
    alerts = [
        build_normalized_alert(
            session_id,
            timestamp_utc="2026-05-19 23:50:00",
            detector_id="video_metrics",
            title="Hybrid snapshot alert",
            message="Read through the runtime-selected Postgres seam.",
            severity="warning",
            source_name="segment_0001.ts",
        )
    ]
    select_runtime_postgres_store(
        monkeypatch,
        StaticAlertStore(session_id, alerts),
    )
    snapshot = read_session_snapshot(session_id)

    assert snapshot["session"] is not None
    assert snapshot["results"] == [
        {
            "session_id": session_id,
            "detector_id": "video_metrics",
            "payload": {"source_name": "segment_0001.ts", "black_ratio": 0.8},
        }
    ]
    assert snapshot["latest_result"] == snapshot["results"][-1]
    assert snapshot["alerts"] == alerts


def test_append_alert_uses_the_default_alert_store_seam(monkeypatch, tmp_path: Path) -> None:
    """The compatibility write helper should delegate directly to the default alert store."""
    monkeypatch.setattr(config, "SESSION_OUTPUT_FOLDER", tmp_path)
    observed: list[AlertEvent] = []

    class FakeAlertStore:
        def append_alert(self, event: AlertEvent) -> None:
            observed.append(event)

    monkeypatch.setattr(session_alert_store, "DEFAULT_SESSION_ALERT_STORE", FakeAlertStore())

    event = _snapshot_alert(
        session_id="session-store-write",
        timestamp_utc="2026-03-30 12:00:00",
        source_name="segment_0001.ts",
        message="Delegated through the store seam.",
    )

    append_alert(event)

    assert observed == [event]


def test_append_alert_round_trips_through_the_shared_alert_read_models(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """The compatibility write entrypoint should feed the same seam used by alert readers."""
    monkeypatch.setattr(config, "SESSION_OUTPUT_FOLDER", tmp_path)

    metadata = _session_metadata("session-alert-round-trip")
    initialize_session(metadata)

    append_alert(
        _snapshot_alert(
            session_id="session-alert-round-trip",
            timestamp_utc="2026-05-06 10:00:00",
            message="Round-trip through the compatibility write seam.",
            source_name="segment_0001.ts",
        )
    )

    assert read_session_alert_events("session-alert-round-trip") == [
        {
            "session_id": "session-alert-round-trip",
            "timestamp_utc": "2026-05-06 10:00:00",
            "detector_id": "video_metrics",
            "title": "Black screen detected",
            "message": "Round-trip through the compatibility write seam.",
            "severity": "warning",
            "source_name": "segment_0001.ts",
            "window_index": None,
            "window_start_sec": None,
        }
    ]
    assert summarize_session_alert_events("session-alert-round-trip") == {
        "session_id": "session-alert-round-trip",
        "total_alerts": 1,
        "counts_by_detector": {"video_metrics": 1},
        "counts_by_severity": {"warning": 1},
        "first_alert_timestamp_utc": "2026-05-06 10:00:00",
        "last_alert_timestamp_utc": "2026-05-06 10:00:00",
    }
    assert build_session_timeline("session-alert-round-trip") == {
        "session_id": "session-alert-round-trip",
        "entries": [
            {
                "start_time_utc": "2026-05-06 10:00:00",
                "end_time_utc": "2026-05-06 10:00:00",
                "detector_id": "video_metrics",
                "severity": "warning",
                "title": "Black screen detected",
                "alert_count": 1,
                "source_names": ["segment_0001.ts"],
                "sample_message": "Round-trip through the compatibility write seam.",
            }
        ],
    }


@pytest.mark.parametrize(
    ("current_status", "next_status"),
    [
        ("pending", "pending"),
        ("pending", "running"),
        ("pending", "cancelled"),
        ("pending", "failed"),
        ("running", "running"),
        ("running", "cancelled"),
        ("running", "completed"),
        ("running", "failed"),
        ("cancelling", "cancelling"),
        ("cancelling", "cancelled"),
        ("cancelling", "failed"),
    ],
)
def test_update_session_status_persists_valid_lifecycle_transitions(
    monkeypatch, tmp_path: Path, current_status: str, next_status: str
) -> None:
    """Valid backend lifecycle transitions should persist updated metadata."""
    monkeypatch.setattr(config, "SESSION_OUTPUT_FOLDER", tmp_path)

    metadata = _status_transition_metadata(current_status, next_status)
    initialize_session(metadata)

    updated = update_session_status(metadata, next_status)
    snapshot = read_session_snapshot(f"session-{current_status}-to-{next_status}")

    assert updated.status == next_status
    assert snapshot["session"]["status"] == next_status


@pytest.mark.parametrize(
    ("current_status", "next_status"),
    [
        ("completed", "running"),
        ("completed", "cancelled"),
        ("completed", "failed"),
        ("cancelled", "running"),
        ("cancelled", "completed"),
        ("cancelled", "failed"),
        ("failed", "running"),
        ("failed", "completed"),
        ("failed", "cancelled"),
    ],
)
def test_update_session_status_rejects_invalid_terminal_transitions(
    monkeypatch, tmp_path: Path, current_status: str, next_status: str
) -> None:
    """Terminal sessions should not transition back into other lifecycle states."""
    monkeypatch.setattr(config, "SESSION_OUTPUT_FOLDER", tmp_path)

    metadata = _status_transition_metadata(current_status, next_status)

    with pytest.raises(
        InvalidSessionTransitionError,
        match=f"{current_status} -> {next_status}",
    ):
        update_session_status(metadata, next_status)


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
