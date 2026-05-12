"""Focused FastAPI adapter tests for session start routes."""

import pytest

from api.routers.sessions import SessionServiceStartFailedError
from analyzer_contract import InputMode
from session_models import SessionMetadata
from tests.api_boundary_sessions_test_support import (
    DEFAULT_VIDEO_FILES_INPUT,
    pending_metadata,
    session_start_call,
    session_start_payload,
    session_start_request_body,
    validation_error_payload,
)
from tests.api_boundary_test_support import request


@pytest.mark.parametrize(
    ("request_body", "expected_call", "expected_payload"),
    [
        (
            session_start_request_body(),
            session_start_call(),
            session_start_payload(session_id="test-session-123"),
        ),
        (
            session_start_request_body(
                mode="api_stream",
                input_path="https://example.com/live/index.m3u8",
                selected_detectors=["video_metrics", "video_blur"],
            ),
            session_start_call(
                mode="api_stream",
                input_path="https://example.com/live/index.m3u8",
                selected_detectors=["video_metrics", "video_blur"],
            ),
            session_start_payload(
                session_id="api-stream-session-123",
                mode="api_stream",
                input_path="https://example.com/live/index.m3u8",
                selected_detectors=["video_metrics", "video_blur"],
            ),
        ),
    ],
)
def test_sessions_start_happy_path(
    monkeypatch,
    request_body: dict[str, object],
    expected_call: tuple[InputMode, str, list[str]],
    expected_payload: dict[str, object],
) -> None:
    calls: list[tuple[InputMode, str, list[str]]] = []

    def fake_start_session_service(
        *,
        mode: InputMode,
        input_path: str,
        selected_detectors: list[str],
    ) -> SessionMetadata:
        calls.append((mode, input_path, selected_detectors))
        return pending_metadata(
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


def test_sessions_start_validation_failure(monkeypatch) -> None:
    detail = "Input path does not exist: missing.mp4"
    monkeypatch.setattr(
        "api.routers.sessions.start_session_service",
        lambda **kwargs: (_ for _ in ()).throw(OSError(detail)),
    )

    response = request(
        "POST",
        "/sessions",
        json=session_start_request_body(input_path=DEFAULT_VIDEO_FILES_INPUT),
    )

    assert response.status_code == 400
    assert response.json() == validation_error_payload(detail)


def test_sessions_start_failure(monkeypatch) -> None:
    monkeypatch.setattr(
        "api.routers.sessions.start_session_service",
        lambda **kwargs: (_ for _ in ()).throw(SessionServiceStartFailedError("spawn failed")),
    )

    response = request(
        "POST",
        "/sessions",
        json=session_start_request_body(input_path=DEFAULT_VIDEO_FILES_INPUT),
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
        lambda **kwargs: pending_metadata(
            session_id="session-no-log-path",
            mode="video_files",
            input_path=DEFAULT_VIDEO_FILES_INPUT,
            selected_detectors=["video_metrics"],
        ),
    )

    response = request(
        "POST",
        "/sessions",
        json=session_start_request_body(input_path=DEFAULT_VIDEO_FILES_INPUT),
    )

    assert response.status_code == 200
    assert "worker_log_path" not in response.json()
