"""Focused FastAPI adapter tests for session start/read/cancel routes.

These cases keep the HTTP boundary explicit:

- request/response mapping
- structured API error behavior
- wiring into the shared `session_service` seam
- the current rule that worker diagnostics stay backend-owned unless a later
  milestone adds a public diagnostics surface
"""

import pytest

from api.routers.sessions import (
    SessionServiceCancelFailedError,
    SessionServiceNotFoundError,
    SessionServiceStartFailedError,
)
from session_models import SessionMetadata
from tests.api_boundary_test_support import request


def _session_not_found_payload(session_id: str) -> dict[str, str]:
    return {
        "detail": "Session not found",
        "error_code": "session_not_found",
        "status_reason": "session_not_found",
        "status_detail": f"No persisted session snapshot found for session_id={session_id}",
    }


def _validation_error_payload(detail: str) -> dict[str, str]:
    return {
        "detail": detail,
        "error_code": "validation_failed",
        "status_reason": "validation_failed",
        "status_detail": detail,
    }


def _pending_metadata(
    session_id: str,
    mode: str,
    input_path: str,
    selected_detectors: list[str],
) -> SessionMetadata:
    return SessionMetadata(
        session_id=session_id,
        mode=mode,
        input_path=input_path,
        selected_detectors=selected_detectors,
        status="pending",
    )


def test_sessions_missing_id() -> None:
    response = request("GET", "/sessions/missing-session-id")
    assert response.status_code == 404
    assert response.json() == _session_not_found_payload("missing-session-id")


def test_get_session_returns_fully_populated_snapshot(monkeypatch) -> None:
    def fake_read_session_snapshot_or_none(session_id: str) -> dict[str, object]:
        return {
            "session": {
                "session_id": session_id,
                "mode": "api_stream",
                "input_path": "https://example.com/live/index.m3u8",
                "selected_detectors": ["video_metrics", "video_blur"],
                "status": "running",
            },
            "progress": {
                "session_id": session_id,
                "status": "running",
                "processed_count": 3,
                "total_count": 8,
                "current_item": "live-window-003.ts",
                "latest_result_detector": "video_metrics",
                "latest_result_detectors": ["video_metrics", "video_blur"],
                "alert_count": 1,
                "last_updated_utc": "2026-04-18 10:00:00",
                "status_reason": "running",
                "status_detail": None,
            },
            "alerts": [
                {
                    "session_id": session_id,
                    "timestamp_utc": "2026-04-18 10:00:00",
                    "detector_id": "video_metrics",
                    "title": "Black screen detected",
                    "message": "Long black segment exceeded threshold.",
                    "severity": "warning",
                    "source_name": "live-window-003.ts",
                    "window_index": 3,
                    "window_start_sec": 6.0,
                },
            ],
            "results": [
                {
                    "session_id": session_id,
                    "detector_id": "video_metrics",
                    "payload": {
                        "black_ratio": 0.8,
                        "longest_black_sec": 2.4,
                    },
                },
            ],
            "latest_result": {
                "session_id": session_id,
                "detector_id": "video_metrics",
                "payload": {
                    "black_ratio": 0.8,
                    "longest_black_sec": 2.4,
                },
            },
        }

    monkeypatch.setattr(
        "api.routers.sessions.read_session_snapshot_or_none",
        fake_read_session_snapshot_or_none,
    )

    response = request("GET", "/sessions/test-session-123")

    assert response.status_code == 200
    assert response.json() == {
        "session": {
            "session_id": "test-session-123",
            "mode": "api_stream",
            "input_path": "https://example.com/live/index.m3u8",
            "selected_detectors": ["video_metrics", "video_blur"],
            "status": "running",
        },
        "progress": {
            "session_id": "test-session-123",
            "status": "running",
            "processed_count": 3,
            "total_count": 8,
            "current_item": "live-window-003.ts",
            "latest_result_detector": "video_metrics",
            "latest_result_detectors": ["video_metrics", "video_blur"],
            "alert_count": 1,
            "last_updated_utc": "2026-04-18 10:00:00",
            "status_reason": "running",
            "status_detail": None,
        },
        "alerts": [
            {
                "session_id": "test-session-123",
                "timestamp_utc": "2026-04-18 10:00:00",
                "detector_id": "video_metrics",
                "title": "Black screen detected",
                "message": "Long black segment exceeded threshold.",
                "severity": "warning",
                "source_name": "live-window-003.ts",
                "window_index": 3,
                "window_start_sec": 6.0,
            },
        ],
        "results": [
            {
                "session_id": "test-session-123",
                "detector_id": "video_metrics",
                "payload": {
                    "black_ratio": 0.8,
                    "longest_black_sec": 2.4,
                },
            },
        ],
        "latest_result": {
            "session_id": "test-session-123",
            "detector_id": "video_metrics",
            "payload": {
                "black_ratio": 0.8,
                "longest_black_sec": 2.4,
            },
        },
    }


def test_get_session_returns_terminal_completed_snapshot(monkeypatch) -> None:
    def fake_read_session_snapshot_or_none(session_id: str) -> dict[str, object]:
        return {
            "session": {
                "session_id": session_id,
                "mode": "video_files",
                "input_path": "/tmp/input.mp4",
                "selected_detectors": ["video_metrics"],
                "status": "completed",
            },
            "progress": {
                "session_id": session_id,
                "status": "completed",
                "processed_count": 4,
                "total_count": 4,
                "current_item": None,
                "latest_result_detector": "video_metrics",
                "latest_result_detectors": ["video_metrics"],
                "alert_count": 0,
                "last_updated_utc": "2026-04-21 10:00:00",
                "status_reason": "completed",
                "status_detail": None,
            },
            "alerts": [],
            "results": [],
            "latest_result": None,
        }

    monkeypatch.setattr(
        "api.routers.sessions.read_session_snapshot_or_none",
        fake_read_session_snapshot_or_none,
    )

    response = request("GET", "/sessions/session-completed")

    assert response.status_code == 200
    assert response.json() == {
        "session": {
            "session_id": "session-completed",
            "mode": "video_files",
            "input_path": "/tmp/input.mp4",
            "selected_detectors": ["video_metrics"],
            "status": "completed",
        },
        "progress": {
            "session_id": "session-completed",
            "status": "completed",
            "processed_count": 4,
            "total_count": 4,
            "current_item": None,
            "latest_result_detector": "video_metrics",
            "latest_result_detectors": ["video_metrics"],
            "alert_count": 0,
            "last_updated_utc": "2026-04-21 10:00:00",
            "status_reason": "completed",
            "status_detail": None,
        },
        "alerts": [],
        "results": [],
        "latest_result": None,
    }


def test_get_session_returns_terminal_failed_snapshot(monkeypatch) -> None:
    def fake_read_session_snapshot_or_none(session_id: str) -> dict[str, object]:
        return {
            "session": {
                "session_id": session_id,
                "mode": "api_stream",
                "input_path": "https://example.com/live/index.m3u8",
                "selected_detectors": ["video_metrics"],
                "status": "failed",
            },
            "progress": {
                "session_id": session_id,
                "status": "failed",
                "processed_count": 2,
                "total_count": 0,
                "current_item": "segment_001.ts",
                "latest_result_detector": "video_metrics",
                "latest_result_detectors": ["video_metrics"],
                "alert_count": 0,
                "last_updated_utc": "2026-04-21 11:00:00",
                "status_reason": "source_unreachable",
                "status_detail": "reconnect budget exhausted",
            },
            "alerts": [],
            "results": [],
            "latest_result": None,
        }

    monkeypatch.setattr(
        "api.routers.sessions.read_session_snapshot_or_none",
        fake_read_session_snapshot_or_none,
    )

    response = request("GET", "/sessions/session-failed")

    assert response.status_code == 200
    assert response.json() == {
        "session": {
            "session_id": "session-failed",
            "mode": "api_stream",
            "input_path": "https://example.com/live/index.m3u8",
            "selected_detectors": ["video_metrics"],
            "status": "failed",
        },
        "progress": {
            "session_id": "session-failed",
            "status": "failed",
            "processed_count": 2,
            "total_count": 0,
            "current_item": "segment_001.ts",
            "latest_result_detector": "video_metrics",
            "latest_result_detectors": ["video_metrics"],
            "alert_count": 0,
            "last_updated_utc": "2026-04-21 11:00:00",
            "status_reason": "source_unreachable",
            "status_detail": "reconnect budget exhausted",
        },
        "alerts": [],
        "results": [],
        "latest_result": None,
    }


def test_get_session_validation_failure_returns_structured_error(monkeypatch) -> None:
    detail = "session directory requires a single safe path component"
    monkeypatch.setattr(
        "api.routers.sessions.read_session_snapshot_or_none",
        lambda session_id: (_ for _ in ()).throw(ValueError(detail)),
    )

    response = request("GET", "/sessions/bad-session-id")

    assert response.status_code == 400
    assert response.json() == _validation_error_payload(detail)


@pytest.mark.parametrize(
    ("request_body", "expected_call", "expected_payload"),
    [
        (
            {
                "mode": "video_files",
                "input_path": "tests/fixtures/media/video_files/black_trigger.mp4",
                "selected_detectors": ["video_metrics"],
            },
            (
                "video_files",
                "tests/fixtures/media/video_files/black_trigger.mp4",
                ["video_metrics"],
            ),
            {
                "session_id": "test-session-123",
                "mode": "video_files",
                "input_path": "tests/fixtures/media/video_files/black_trigger.mp4",
                "selected_detectors": ["video_metrics"],
                "status": "pending",
            },
        ),
        (
            {
                "mode": "api_stream",
                "input_path": "https://example.com/live/index.m3u8",
                "selected_detectors": ["video_metrics", "video_blur"],
            },
            (
                "api_stream",
                "https://example.com/live/index.m3u8",
                ["video_metrics", "video_blur"],
            ),
            {
                "session_id": "api-stream-session-123",
                "mode": "api_stream",
                "input_path": "https://example.com/live/index.m3u8",
                "selected_detectors": ["video_metrics", "video_blur"],
                "status": "pending",
            },
        ),
    ],
)
def test_sessions_start_happy_path(
    monkeypatch,
    request_body: dict[str, object],
    expected_call: tuple[str, str, list[str]],
    expected_payload: dict[str, object],
) -> None:
    calls: list[tuple[str, str, list[str]]] = []

    def fake_start_session_service(
        *,
        mode: str,
        input_path: str,
        selected_detectors: list[str],
    ) -> SessionMetadata:
        calls.append((mode, input_path, selected_detectors))
        return _pending_metadata(
            session_id=str(expected_payload["session_id"]),
            mode=mode,
            input_path=input_path,
            selected_detectors=selected_detectors,
        )

    monkeypatch.setattr(
        "api.routers.sessions.start_session_service",
        fake_start_session_service,
    )

    response = request("POST", "/sessions", json=request_body)

    assert response.status_code == 200
    assert calls == [expected_call]
    assert response.json() == expected_payload


@pytest.mark.parametrize(
    ("path", "service_attr", "error_factory", "expected_status", "expected_payload"),
    [
        (
            "/sessions",
            "start_session_service",
            lambda: OSError("Input path does not exist: missing.mp4"),
            400,
            _validation_error_payload("Input path does not exist: missing.mp4"),
        ),
        (
            "/sessions/test-session-123/cancel",
            "cancel_session_service",
            lambda: ValueError("session directory requires a single safe path component"),
            400,
            _validation_error_payload("session directory requires a single safe path component"),
        ),
        (
            "/sessions/test-session-123/cancel",
            "cancel_session_service",
            lambda: SessionServiceCancelFailedError("test-session-123", "completed"),
            409,
            {
                "detail": "Session cannot be cancelled from its current state",
                "error_code": "cancel_failed",
                "status_reason": "cancel_failed",
                "status_detail": "Session test-session-123 is already completed.",
            },
        ),
        (
            "/sessions/missing-session-id/cancel",
            "cancel_session_service",
            lambda: SessionServiceNotFoundError("missing-session-id"),
            404,
            _session_not_found_payload("missing-session-id"),
        ),
    ],
)
def test_session_adapter_error_mapping(
    monkeypatch,
    path: str,
    service_attr: str,
    error_factory,
    expected_status: int,
    expected_payload: dict[str, object],
) -> None:
    request_json = (
        {
            "mode": "video_files",
            "input_path": "tests/fixtures/media/video_files/black_trigger.mp4",
            "selected_detectors": ["video_metrics"],
        }
        if path == "/sessions"
        else None
    )

    monkeypatch.setattr(
        f"api.routers.sessions.{service_attr}",
        lambda *args, **kwargs: (_ for _ in ()).throw(error_factory()),
    )

    response = request("POST", path, json=request_json)

    assert response.status_code == expected_status
    assert response.json() == expected_payload


def test_sessions_start_failure(monkeypatch) -> None:
    monkeypatch.setattr(
        "api.routers.sessions.start_session_service",
        lambda **kwargs: (_ for _ in ()).throw(SessionServiceStartFailedError("spawn failed")),
    )

    response = request(
        "POST",
        "/sessions",
        json={
            "mode": "video_files",
            "input_path": "tests/fixtures/media/video_files/black_trigger.mp4",
            "selected_detectors": ["video_metrics"],
        },
    )

    assert response.status_code == 500
    assert response.json() == {
        "detail": "Session could not be started",
        "error_code": "session_start_failed",
        "status_reason": "session_start_failed",
        "status_detail": "spawn failed",
    }


def test_start_session_does_not_surface_worker_log_metadata(monkeypatch) -> None:
    """Worker diagnostics should stay backend-owned until a later milestone exposes them."""
    monkeypatch.setattr(
        "api.routers.sessions.start_session_service",
        lambda **kwargs: _pending_metadata(
            session_id="session-no-log-path",
            mode="video_files",
            input_path="tests/fixtures/media/video_files/black_trigger.mp4",
            selected_detectors=["video_metrics"],
        ),
    )

    response = request(
        "POST",
        "/sessions",
        json={
            "mode": "video_files",
            "input_path": "tests/fixtures/media/video_files/black_trigger.mp4",
            "selected_detectors": ["video_metrics"],
        },
    )

    assert response.status_code == 200
    assert "worker_log_path" not in response.json()


def test_cancel_session_happy_path(monkeypatch) -> None:
    calls: list[str] = []

    monkeypatch.setattr(
        "api.routers.sessions.cancel_session_service",
        lambda session_id: calls.append(session_id) or {
            "session_id": session_id,
            "mode": "video_files",
            "input_path": "tests/fixtures/media/video_files/black_trigger.mp4",
            "selected_detectors": ["video_metrics"],
            "status": "cancelling",
        },
    )

    response = request("POST", "/sessions/test-session-123/cancel")

    assert response.status_code == 200
    assert calls == ["test-session-123"]
    assert response.json() == {
        "session_id": "test-session-123",
        "mode": "video_files",
        "input_path": "tests/fixtures/media/video_files/black_trigger.mp4",
        "selected_detectors": ["video_metrics"],
        "status": "cancelling",
    }

def test_cancel_session_allows_already_cancelling_state(monkeypatch) -> None:
    calls: list[str] = []

    monkeypatch.setattr(
        "api.routers.sessions.cancel_session_service",
        lambda session_id: calls.append(session_id) or {
            "session_id": session_id,
            "mode": "api_stream",
            "input_path": "https://example.com/live/index.m3u8",
            "selected_detectors": ["video_metrics"],
            "status": "cancelling",
        },
    )

    response = request("POST", "/sessions/session-cancelling/cancel")

    assert response.status_code == 200
    assert calls == ["session-cancelling"]
    assert response.json() == {
        "session_id": "session-cancelling",
        "mode": "api_stream",
        "input_path": "https://example.com/live/index.m3u8",
        "selected_detectors": ["video_metrics"],
        "status": "cancelling",
    }
