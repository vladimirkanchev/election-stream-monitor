import asyncio

import httpx
from api.app import app


async def _request(
    method: str,
    path: str,
    *,
    json: dict[str, object] | None = None,
) -> httpx.Response:
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        return await client.request(method, path, json=json)


def request(
    method: str,
    path: str,
    *,
    json: dict[str, object] | None = None,
) -> httpx.Response:
    return asyncio.run(_request(method, path, json=json))


def test_health() -> None:
    response = request("GET", "/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_detectors() -> None:
    response = request("GET", "/detectors")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_detectors_invalid_mode() -> None:
    response = request("GET", "/detectors?mode=invalid_mode")
    assert response.status_code == 422
    assert response.json() == {
        "detail": "Request validation failed",
        "error_code": "validation_failed",
        "status_reason": "validation_failed",
        "status_detail": "query.mode: Input should be 'video_segments', 'video_files' or 'api_stream'",
    }


def test_playback_resolve_requires_payload() -> None:
    response = request("POST", "/playback/resolve")
    assert response.status_code == 422
    assert response.json() == {
        "detail": "Request validation failed",
        "error_code": "validation_failed",
        "status_reason": "validation_failed",
        "status_detail": "body: Field required",
    }


def test_playback_resolve_api_stream_requires_direct_media_url() -> None:
    response = request(
        "POST",
        "/playback/resolve",
        json={
            "mode": "api_stream",
            "input_path": "https://example.com/watch/live",
            "current_item": None,
        },
    )

    assert response.status_code == 400
    assert response.json() == {
        "detail": "api_stream requires a direct .m3u8 or .mp4 URL, not a webpage URL.",
        "error_code": "validation_failed",
        "status_reason": "validation_failed",
        "status_detail": "api_stream requires a direct .m3u8 or .mp4 URL, not a webpage URL.",
    }


def test_playback_resolve_api_stream_rejects_private_host() -> None:
    response = request(
        "POST",
        "/playback/resolve",
        json={
            "mode": "api_stream",
            "input_path": "http://127.0.0.1/live/index.m3u8",
            "current_item": None,
        },
    )

    assert response.status_code == 400
    assert response.json() == {
        "detail": "api_stream host is not allowed in local mode: 127.0.0.1",
        "error_code": "validation_failed",
        "status_reason": "validation_failed",
        "status_detail": "api_stream host is not allowed in local mode: 127.0.0.1",
    }


def test_playback_resolve_invalid_mode() -> None:
    response = request(
        "POST",
        "/playback/resolve",
        json={
            "mode": "invalid_mode",
            "input_path": "tests/fixtures/media/video_files/black_trigger.mp4",
            "current_item": None,
        },
    )
    assert response.status_code == 422
    assert response.json() == {
        "detail": "Request validation failed",
        "error_code": "validation_failed",
        "status_reason": "validation_failed",
        "status_detail": "body.mode: Input should be 'video_segments', 'video_files' or 'api_stream'",
    }


def test_playback_resolve_with_payload() -> None:
    response = request(
        "POST",
        "/playback/resolve",
        json={
            "mode": "video_files",
            "input_path": "tests/fixtures/media/video_files/black_trigger.mp4",
            "current_item": None,
        },
    )
    assert response.status_code == 200
    assert "source" in response.json()


def test_playback_resolve_validation_failure(monkeypatch) -> None:
    def fake_validate_source_input(mode: str, input_path: str) -> str:
        raise OSError("Input path does not exist: missing.mp4")

    monkeypatch.setattr(
        "api.routers.playback.validate_source_input",
        fake_validate_source_input,
    )

    response = request(
        "POST",
        "/playback/resolve",
        json={
            "mode": "video_files",
            "input_path": "missing.mp4",
            "current_item": None,
        },
    )

    assert response.status_code == 400
    assert response.json() == {
        "detail": "Input path does not exist: missing.mp4",
        "error_code": "validation_failed",
        "status_reason": "validation_failed",
        "status_detail": "Input path does not exist: missing.mp4",
    }


def test_playback_resolve_unavailable(monkeypatch) -> None:
    monkeypatch.setattr(
        "api.routers.playback.validate_source_input",
        lambda mode, input_path: input_path,
    )

    def fake_resolve_playback_source(
        mode: str,
        input_path: str,
        current_item: str | None = None,
    ) -> str | None:
        _ = (mode, input_path, current_item)
        raise ValueError("Playable source missing for current item")

    monkeypatch.setattr(
        "api.routers.playback.resolve_playback_source",
        fake_resolve_playback_source,
    )

    response = request(
        "POST",
        "/playback/resolve",
        json={
            "mode": "video_files",
            "input_path": "tests/fixtures/media/video_files/black_trigger.mp4",
            "current_item": "black_trigger.mp4",
        },
    )

    assert response.status_code == 400
    assert response.json() == {
        "detail": "Playback source could not be resolved",
        "error_code": "playback_unavailable",
        "status_reason": "playback_unavailable",
        "status_detail": "Playable source missing for current item",
    }


def test_sessions_missing_id() -> None:
    response = request("GET", "/sessions/missing-session-id")
    assert response.status_code == 404
    assert response.json() == {
        "detail": "Session not found",
        "error_code": "session_not_found",
        "status_reason": "session_not_found",
        "status_detail": "No persisted session snapshot found for session_id=missing-session-id",
    }


def test_get_session_returns_fully_populated_snapshot(monkeypatch) -> None:
    def fake_read_session_snapshot(session_id: str) -> dict[str, object]:
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
        "api.routers.sessions.read_session_snapshot",
        fake_read_session_snapshot,
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


def test_sessions_start_requires_payload() -> None:
    response = request("POST", "/sessions")

    assert response.status_code == 422
    assert response.json() == {
        "detail": "Request validation failed",
        "error_code": "validation_failed",
        "status_reason": "validation_failed",
        "status_detail": "body: Field required",
    }


def test_sessions_start_rejects_malformed_body() -> None:
    response = request(
        "POST",
        "/sessions",
        json={
            "mode": "video_files",
            "selected_detectors": ["video_metrics"],
        },
    )

    assert response.status_code == 422
    payload = response.json()
    assert payload["detail"] == "Request validation failed"
    assert payload["error_code"] == "validation_failed"
    assert payload["status_reason"] == "validation_failed"
    assert "body.input_path" in payload["status_detail"]


def test_sessions_start_invalid_mode() -> None:
    response = request(
        "POST",
        "/sessions",
        json={
            "mode": "invalid_mode",
            "input_path": "tests/fixtures/media/video_files/black_trigger.mp4",
            "selected_detectors": ["video_metrics"],
        },
    )
    assert response.status_code == 422
    assert response.json() == {
        "detail": "Request validation failed",
        "error_code": "validation_failed",
        "status_reason": "validation_failed",
        "status_detail": "body.mode: Input should be 'video_segments', 'video_files' or 'api_stream'",
    }


def test_sessions_start_api_stream_requires_direct_media_url() -> None:
    response = request(
        "POST",
        "/sessions",
        json={
            "mode": "api_stream",
            "input_path": "https://example.com/watch/live",
            "selected_detectors": ["video_metrics"],
        },
    )

    assert response.status_code == 400
    assert response.json() == {
        "detail": "api_stream requires a direct .m3u8 or .mp4 URL, not a webpage URL.",
        "error_code": "validation_failed",
        "status_reason": "validation_failed",
        "status_detail": "api_stream requires a direct .m3u8 or .mp4 URL, not a webpage URL.",
    }


def test_sessions_start_happy_path(monkeypatch) -> None:
    monkeypatch.setattr(
        "api.routers.sessions.validate_source_input",
        lambda mode, input_path: input_path,
    )
    monkeypatch.setattr(
        "api.routers.sessions.create_session_id",
        lambda: "test-session-123",
    )

    class DummyPopen:
        def __init__(self, *args, **kwargs) -> None:
            pass

    monkeypatch.setattr("api.routers.sessions.subprocess.Popen", DummyPopen)

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
    assert response.json() == {
        "session_id": "test-session-123",
        "mode": "video_files",
        "input_path": "tests/fixtures/media/video_files/black_trigger.mp4",
        "selected_detectors": ["video_metrics"],
        "status": "pending",
    }


def test_sessions_start_validation_failure(monkeypatch) -> None:
    def fake_validate_source_input(mode: str, input_path: str) -> str:
        raise OSError("Input path does not exist: missing.mp4")

    monkeypatch.setattr(
        "api.routers.sessions.validate_source_input",
        fake_validate_source_input,
    )

    response = request(
        "POST",
        "/sessions",
        json={
            "mode": "video_files",
            "input_path": "missing.mp4",
            "selected_detectors": ["video_metrics"],
        },
    )

    assert response.status_code == 400
    assert response.json() == {
        "detail": "Input path does not exist: missing.mp4",
        "error_code": "validation_failed",
        "status_reason": "validation_failed",
        "status_detail": "Input path does not exist: missing.mp4",
    }


def test_sessions_start_failure(monkeypatch) -> None:
    monkeypatch.setattr(
        "api.routers.sessions.validate_source_input",
        lambda mode, input_path: input_path,
    )
    monkeypatch.setattr(
        "api.routers.sessions.create_session_id",
        lambda: "test-session-123",
    )

    def fake_popen(*args, **kwargs) -> None:
        _ = (args, kwargs)
        raise OSError("spawn failed")

    monkeypatch.setattr("api.routers.sessions.subprocess.Popen", fake_popen)

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


def test_sessions_unexpected_failure_returns_structured_payload(monkeypatch) -> None:
    monkeypatch.setattr(
        "api.routers.sessions.validate_source_input",
        lambda mode, input_path: input_path,
    )
    monkeypatch.setattr(
        "api.routers.sessions.create_session_id",
        lambda: "test-session-123",
    )

    def fake_model_validate(*args, **kwargs) -> None:
        _ = (args, kwargs)
        raise RuntimeError("response serialization blew up")

    monkeypatch.setattr(
        "api.routers.sessions.SessionSummaryResponse.model_validate",
        fake_model_validate,
    )

    class DummyPopen:
        def __init__(self, *args, **kwargs) -> None:
            pass

    monkeypatch.setattr("api.routers.sessions.subprocess.Popen", DummyPopen)

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
        "detail": "Unexpected backend error",
        "error_code": "internal_error",
        "status_reason": "internal_error",
        "status_detail": "response serialization blew up",
    }


def test_detectors_unexpected_failure_returns_structured_payload(monkeypatch) -> None:
    def fake_list_available_detectors(mode: object = None) -> list[dict[str, object]]:
        _ = mode
        raise RuntimeError("catalog exploded")

    monkeypatch.setattr(
        "api.routers.detectors.list_available_detectors",
        fake_list_available_detectors,
    )

    response = request("GET", "/detectors")

    assert response.status_code == 500
    assert response.json() == {
        "detail": "Unexpected backend error",
        "error_code": "internal_error",
        "status_reason": "internal_error",
        "status_detail": "catalog exploded",
    }


def test_cancel_session_happy_path(monkeypatch) -> None:
    cancelled: list[str] = []

    def fake_request_session_cancel(session_id: str) -> None:
        cancelled.append(session_id)

    def fake_read_session_snapshot(session_id: str) -> dict[str, object]:
        return {
            "session": {
                "session_id": session_id,
                "mode": "video_files",
                "input_path": "tests/fixtures/media/video_files/black_trigger.mp4",
                "selected_detectors": ["video_metrics"],
                "status": "running",
            },
            "progress": None,
            "alerts": [],
            "results": [],
            "latest_result": None,
        }

    monkeypatch.setattr(
        "api.routers.sessions.request_session_cancel",
        fake_request_session_cancel,
    )
    monkeypatch.setattr(
        "api.routers.sessions.read_session_snapshot",
        fake_read_session_snapshot,
    )

    response = request("POST", "/sessions/test-session-123/cancel")

    assert response.status_code == 200
    assert cancelled == ["test-session-123"]
    assert response.json() == {
        "session_id": "test-session-123",
        "mode": "video_files",
        "input_path": "tests/fixtures/media/video_files/black_trigger.mp4",
        "selected_detectors": ["video_metrics"],
        "status": "cancelling",
    }


def test_cancel_session_terminal_state_current_behavior(monkeypatch) -> None:
    cancelled: list[str] = []

    def fake_request_session_cancel(session_id: str) -> None:
        cancelled.append(session_id)

    def fake_read_session_snapshot(session_id: str) -> dict[str, object]:
        return {
            "session": {
                "session_id": session_id,
                "mode": "video_files",
                "input_path": "tests/fixtures/media/video_files/black_trigger.mp4",
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
                "last_updated_utc": "2026-04-18 12:00:00",
                "status_reason": "completed",
                "status_detail": None,
            },
            "alerts": [],
            "results": [],
            "latest_result": None,
        }

    monkeypatch.setattr(
        "api.routers.sessions.request_session_cancel",
        fake_request_session_cancel,
    )
    monkeypatch.setattr(
        "api.routers.sessions.read_session_snapshot",
        fake_read_session_snapshot,
    )

    response = request("POST", "/sessions/test-session-123/cancel")

    assert response.status_code == 200
    assert cancelled == ["test-session-123"]
    assert response.json() == {
        "session_id": "test-session-123",
        "mode": "video_files",
        "input_path": "tests/fixtures/media/video_files/black_trigger.mp4",
        "selected_detectors": ["video_metrics"],
        "status": "cancelling",
    }


def test_cancel_session_missing_id() -> None:
    response = request("POST", "/sessions/missing-session-id/cancel")

    assert response.status_code == 404
    assert response.json() == {
        "detail": "Session not found",
        "error_code": "session_not_found",
        "status_reason": "session_not_found",
        "status_detail": "No persisted session snapshot found for session_id=missing-session-id",
    }


def test_playback_resolve_api_stream_rejects_credentials_in_url() -> None:
    response = request(
        "POST",
        "/playback/resolve",
        json={
            "mode": "api_stream",
            "input_path": "https://user:secret@example.com/live/index.m3u8",
            "current_item": None,
        },
    )

    assert response.status_code == 400
    assert response.json() == {
        "detail": "api_stream URLs must not include credentials.",
        "error_code": "validation_failed",
        "status_reason": "validation_failed",
        "status_detail": "api_stream URLs must not include credentials.",
    }
