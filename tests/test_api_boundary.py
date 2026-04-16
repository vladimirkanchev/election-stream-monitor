import asyncio

import httpx
from api.app import app


async def _request(
    method: str,
    path: str,
    *,
    json: dict[str, object] | None = None,
) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
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


def test_playback_resolve_requires_payload() -> None:
    response = request("POST", "/playback/resolve")
    assert response.status_code == 422


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


def test_cancel_session_missing_id() -> None:
    response = request("POST", "/sessions/missing-session-id/cancel")

    assert response.status_code == 404
    assert response.json() == {
        "detail": "Session not found",
        "error_code": "session_not_found",
        "status_reason": "session_not_found",
        "status_detail": "No persisted session snapshot found for session_id=missing-session-id",
    }
