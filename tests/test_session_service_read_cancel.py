"""Focused tests for session-service reads, cancel behavior, and snapshot shape.

This file covers the shared service contract used by the API, CLI, and desktop
polling paths, with extra attention on store-backed progress reads, ordered
results, and derived `latest_result`.
"""

from collections.abc import Iterator
from threading import Event, Thread
from typing import cast

import pytest

import session_service
from analyzer_contract import InputMode
from session_alert_store import clear_default_session_alert_store_cache
from session_models import SessionProgress, SessionStatus
from session_store import SessionSnapshotPayload
from tests.session_alert_test_support import (
    build_normalized_alert,
    install_runtime_postgres_session_alerts,
)


@pytest.fixture(autouse=True)
def _clear_default_alert_store_cache() -> Iterator[None]:
    """Keep runtime-selected default-store caching isolated across service tests."""
    clear_default_session_alert_store_cache()
    yield
    clear_default_session_alert_store_cache()


def _session(
    *,
    session_id: str,
    mode: InputMode,
    input_path: str,
    status: SessionStatus,
    selected_detectors: list[str] | None = None,
) -> dict[str, object]:
    """Build the session section used by service read and cancel tests."""
    session_data: dict[str, object] = {
        "session_id": session_id,
        "mode": mode,
        "input_path": input_path,
        "status": status,
    }
    if selected_detectors is not None:
        session_data["selected_detectors"] = selected_detectors
    return session_data


def _snapshot(
    session: dict[str, object] | None,
    *,
    progress: dict[str, object] | None = None,
) -> dict[str, object]:
    """Build the minimal snapshot shape expected by the shared service helpers."""
    return {
        "session": session,
        "progress": progress,
        "alerts": [],
        "results": [],
        "latest_result": None,
    }


def _progress(
    *,
    session_id: str,
    processed_count: int,
    total_count: int = 5,
    current_item: str | None = None,
    alert_count: int | None = None,
    last_updated_utc: str | None = None,
    status: SessionStatus = "running",
) -> dict[str, object]:
    """Build one stable progress payload for shared service read-path tests."""
    return SessionProgress(
        session_id=session_id,
        status=status,
        processed_count=processed_count,
        total_count=total_count,
        current_item=current_item or f"segment_{processed_count:04d}.ts",
        latest_result_detector="video_metrics",
        alert_count=processed_count if alert_count is None else alert_count,
        last_updated_utc=last_updated_utc or f"2026-06-30 10:00:0{processed_count}",
        latest_result_detectors=["video_metrics"],
        status_reason=status,
        status_detail=None,
    ).to_dict()


def _cancel_summary(
    *,
    session_id: str,
    mode: str,
    input_path: str,
    selected_detectors: list[str] | None,
) -> dict[str, object]:
    """Build the cancel summary returned by the service after a valid request."""
    return {
        "session_id": session_id,
        "mode": mode,
        "input_path": input_path,
        "selected_detectors": selected_detectors or [],
        "status": "cancelling",
    }


def test_read_session_returns_existing_snapshot(monkeypatch) -> None:
    """Read should return the full snapshot when a session exists."""
    monkeypatch.setattr(
        session_service,
        "read_session_snapshot",
        lambda session_id: _snapshot(
            {
                "session_id": session_id,
                "mode": "video_files",
                "input_path": "/tmp/input.mp4",
                "selected_detectors": ["video_metrics"],
                "status": "running",
            }
        ),
    )

    snapshot = session_service.read_session_snapshot_or_none("session-123")

    assert snapshot is not None
    session_data = cast(dict[str, object], snapshot["session"])
    assert session_data["session_id"] == "session-123"


def test_read_session_snapshot_uses_default_session_store(monkeypatch) -> None:
    """Service reads should resolve through the default session-store boundary."""

    class FakeStore:
        def read_snapshot(self, session_id: str) -> SessionSnapshotPayload:
            return cast(
                SessionSnapshotPayload,
                _snapshot(
                    _session(
                        session_id=session_id,
                        mode="video_files",
                        input_path="/tmp/store-backed.mp4",
                        selected_detectors=["video_metrics"],
                        status="running",
                    )
                ),
            )

    monkeypatch.setattr(
        session_service,
        "get_default_session_store",
        lambda: FakeStore(),
    )

    snapshot = session_service.read_session_snapshot("session-store-read")

    session_data = cast(dict[str, object], snapshot["session"])
    assert session_data["session_id"] == "session-store-read"


def test_read_session_snapshot_keeps_store_backed_progress_shape(monkeypatch) -> None:
    """Service reads should return progress exactly as exposed by the active store."""
    expected_progress = _progress(
        session_id="session-store-progress",
        processed_count=3,
        total_count=5,
        current_item="live-window-003.ts",
        alert_count=1,
        last_updated_utc="2026-06-30 09:00:00",
    )

    class FakeStore:
        def read_snapshot(self, session_id: str) -> SessionSnapshotPayload:
            return cast(
                SessionSnapshotPayload,
                _snapshot(
                    _session(
                        session_id=session_id,
                        mode="api_stream",
                        input_path="https://example.com/live/index.m3u8",
                        selected_detectors=["video_metrics"],
                        status="running",
                    ),
                    progress=expected_progress,
                ),
            )

    monkeypatch.setattr(
        session_service,
        "get_default_session_store",
        lambda: FakeStore(),
    )

    snapshot = session_service.read_session_snapshot("session-store-progress")

    assert snapshot["progress"] == expected_progress


def test_read_session_snapshot_keeps_store_backed_ordered_results_shape(monkeypatch) -> None:
    """Service reads should preserve ordered result history and derived latest result."""
    session_id = "session-store-results"
    expected_results = [
        {
            "session_id": session_id,
            "detector_id": "video_metrics",
            "payload": {
                "timestamp_utc": "2026-07-01 10:00:00",
                "source_name": "segment_0000.ts",
                "window_index": 0,
            },
        },
        {
            "session_id": session_id,
            "detector_id": "video_blur",
            "payload": {
                "timestamp_utc": "2026-07-01 10:00:00",
                "source_name": "segment_0001.ts",
                "window_index": 1,
            },
        },
    ]

    class FakeStore:
        def read_snapshot(self, read_session_id: str) -> SessionSnapshotPayload:
            return cast(
                SessionSnapshotPayload,
                {
                    "session": _session(
                        session_id=read_session_id,
                        mode="video_segments",
                        input_path="/tmp/segments",
                        selected_detectors=["video_metrics", "video_blur"],
                        status="running",
                    ),
                    "progress": None,
                    "alerts": [],
                    "results": expected_results,
                    "latest_result": expected_results[-1],
                },
            )

    monkeypatch.setattr(
        session_service,
        "get_default_session_store",
        lambda: FakeStore(),
    )

    snapshot = session_service.read_session_snapshot(session_id)

    assert snapshot["results"] == expected_results
    assert snapshot["latest_result"] == expected_results[-1]


def test_read_session_snapshot_returns_last_committed_progress_during_interleaved_write(
    monkeypatch,
) -> None:
    """Service reads should stay on the last committed progress during an in-flight update."""
    session_id = "session-store-progress-race"
    session_payload = _session(
        session_id=session_id,
        mode="video_segments",
        input_path="/tmp/segments",
        selected_detectors=["video_metrics"],
        status="running",
    )
    first_progress = _progress(session_id=session_id, processed_count=1)
    second_progress = _progress(session_id=session_id, processed_count=2)
    write_errors: list[BaseException] = []

    class CoordinatedStore:
        def __init__(self) -> None:
            self._committed_progress = first_progress
            self.write_started = Event()
            self.allow_commit = Event()

        def read_snapshot(self, read_session_id: str) -> SessionSnapshotPayload:
            return cast(
                SessionSnapshotPayload,
                _snapshot(
                    session_payload if read_session_id == session_id else None,
                    progress=self._committed_progress if read_session_id == session_id else None,
                ),
            )

        def write_progress(self, progress: SessionProgress) -> None:
            self.write_started.set()
            assert self.allow_commit.wait(timeout=1.0)
            self._committed_progress = progress.to_dict()

    store = CoordinatedStore()

    monkeypatch.setattr(
        session_service,
        "get_default_session_store",
        lambda: store,
    )

    def write_second_progress() -> None:
        try:
            store.write_progress(
                SessionProgress(
                    session_id=session_id,
                    status="running",
                    processed_count=2,
                    total_count=5,
                    current_item="segment_0002.ts",
                    latest_result_detector="video_metrics",
                    alert_count=2,
                    last_updated_utc="2026-06-30 10:00:02",
                    latest_result_detectors=["video_metrics"],
                    status_reason="running",
                    status_detail=None,
                )
            )
        except BaseException as error:
            write_errors.append(error)

    writer = Thread(target=write_second_progress)
    writer.start()
    assert store.write_started.wait(timeout=1.0)

    snapshot_during_write = session_service.read_session_snapshot(session_id)
    assert snapshot_during_write["progress"] == first_progress

    store.allow_commit.set()
    writer.join(timeout=1.0)
    assert not writer.is_alive()
    assert write_errors == []

    snapshot_after_write = session_service.read_session_snapshot(session_id)
    assert snapshot_after_write["progress"] == second_progress


def test_read_session_returns_none_when_missing(monkeypatch) -> None:
    """Read should centralize the missing-session check."""
    monkeypatch.setattr(
        session_service,
        "read_session_snapshot",
        lambda session_id: _snapshot(None),
    )

    snapshot = session_service.read_session_snapshot_or_none("missing-session")

    assert snapshot is None


def test_read_session_returns_seam_backed_alerts_in_runtime_postgres_mode(
    monkeypatch,
    tmp_path,
) -> None:
    """The shared session service should expose seam-backed alerts in Postgres mode."""
    session_id = "session-service-runtime-postgres"
    alerts = [
        build_normalized_alert(
            session_id,
            timestamp_utc="2026-05-19 23:10:00",
            detector_id="video_metrics",
            title="Service snapshot alert",
            message="Read through the shared snapshot service seam.",
            severity="warning",
            source_name="segment_0001.ts",
        )
    ]
    install_runtime_postgres_session_alerts(
        monkeypatch,
        tmp_path,
        session_id=session_id,
        alerts=alerts,
    )
    snapshot = session_service.read_session_snapshot_or_none(session_id)

    assert snapshot is not None
    assert snapshot["alerts"] == alerts


def test_cancel_failed_error_exposes_current_status() -> None:
    """The service cancel error should keep the parsed status for adapters."""
    error = session_service.SessionServiceCancelFailedError(
        "session-terminal",
        "completed",
    )

    assert error.session_id == "session-terminal"
    assert error.current_status == "completed"
    assert str(error) == "Session session-terminal is already completed."


def test_build_empty_session_snapshot_returns_fresh_lists() -> None:
    """Each empty snapshot call should get its own mutable event lists."""
    first = session_service.build_empty_session_snapshot()
    second = session_service.build_empty_session_snapshot()
    first_alerts = cast(list[dict[str, object]], first["alerts"])
    first_results = cast(list[dict[str, object]], first["results"])

    first_alerts.append({"title": "example"})
    first_results.append({"detector_id": "video_metrics"})

    assert second == {
        "session": None,
        "progress": None,
        "alerts": [],
        "results": [],
        "latest_result": None,
    }


def test_cancel_session_running_happy_path(monkeypatch) -> None:
    """Cancel should allow active sessions and return the cancelling summary."""
    cancelled: list[str] = []

    monkeypatch.setattr(
        session_service,
        "read_session_snapshot",
        lambda session_id: _snapshot(
            _session(
                session_id=session_id,
                mode="video_files",
                input_path="tests/fixtures/media/video_files/black_trigger.mp4",
                selected_detectors=["video_metrics"],
                status="running",
            )
        ),
    )
    monkeypatch.setattr(
        session_service,
        "request_session_cancel",
        lambda session_id: cancelled.append(session_id),
    )

    summary = session_service.cancel_session("session-running")

    assert cancelled == ["session-running"]
    assert summary == _cancel_summary(
        session_id="session-running",
        mode="video_files",
        input_path="tests/fixtures/media/video_files/black_trigger.mp4",
        selected_detectors=["video_metrics"],
    )


def test_cancel_session_allows_already_cancelling(monkeypatch) -> None:
    """Cancel should preserve the existing behavior for already-cancelling runs."""
    cancelled: list[str] = []

    monkeypatch.setattr(
        session_service,
        "read_session_snapshot",
        lambda session_id: _snapshot(
            _session(
                session_id=session_id,
                mode="api_stream",
                input_path="https://example.com/live/index.m3u8",
                selected_detectors=["video_metrics"],
                status="cancelling",
            )
        ),
    )
    monkeypatch.setattr(
        session_service,
        "request_session_cancel",
        lambda session_id: cancelled.append(session_id),
    )

    summary = session_service.cancel_session("session-cancelling")

    assert cancelled == ["session-cancelling"]
    assert summary == _cancel_summary(
        session_id="session-cancelling",
        mode="api_stream",
        input_path="https://example.com/live/index.m3u8",
        selected_detectors=["video_metrics"],
    )


def test_cancel_session_rejects_terminal_status(monkeypatch) -> None:
    """Cancel should reject terminal sessions through the service error."""
    monkeypatch.setattr(
        session_service,
        "read_session_snapshot",
        lambda session_id: _snapshot(
            _session(
                session_id=session_id,
                mode="video_files",
                input_path="/tmp/input.mp4",
                selected_detectors=["video_metrics"],
                status="completed",
            )
        ),
    )

    with pytest.raises(
        session_service.SessionServiceCancelFailedError,
        match="Session session-terminal is already completed.",
    ):
        session_service.cancel_session("session-terminal")


def test_cancel_session_missing_id_raises_not_found(monkeypatch) -> None:
    """Cancel should use the service-level not-found error for missing sessions."""
    monkeypatch.setattr(
        session_service,
        "read_session_snapshot",
        lambda session_id: _snapshot(None),
    )

    with pytest.raises(session_service.SessionServiceNotFoundError, match="missing-session"):
        session_service.cancel_session("missing-session")


def test_cancel_session_defaults_missing_selected_detectors_to_empty_list(
    monkeypatch,
) -> None:
    """Cancel summaries should stay stable even when older snapshots miss the field."""
    monkeypatch.setattr(
        session_service,
        "read_session_snapshot",
        lambda session_id: _snapshot(
            _session(
                session_id=session_id,
                mode="video_files",
                input_path="/tmp/input.mp4",
                selected_detectors=None,
                status="running",
            )
        ),
    )
    monkeypatch.setattr(
        session_service,
        "request_session_cancel",
        lambda session_id: None,
    )

    summary = session_service.cancel_session("session-missing-detectors")

    assert summary == _cancel_summary(
        session_id="session-missing-detectors",
        mode="video_files",
        input_path="/tmp/input.mp4",
        selected_detectors=None,
    )
