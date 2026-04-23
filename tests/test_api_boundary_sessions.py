from tests.api_boundary_test_support import request


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


def test_get_session_returns_terminal_completed_snapshot(monkeypatch) -> None:
    def fake_read_session_snapshot(session_id: str) -> dict[str, object]:
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
        "api.routers.sessions.read_session_snapshot",
        fake_read_session_snapshot,
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
    def fake_read_session_snapshot(session_id: str) -> dict[str, object]:
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
        "api.routers.sessions.read_session_snapshot",
        fake_read_session_snapshot,
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


def test_sessions_start_api_stream_happy_path(monkeypatch) -> None:
    build_calls: list[tuple[str, list[str]]] = []

    monkeypatch.setattr(
        "api.routers.sessions.validate_source_input",
        lambda mode, input_path: input_path,
    )
    monkeypatch.setattr(
        "api.routers.sessions.create_session_id",
        lambda: "api-stream-session-123",
    )

    def fake_build_api_stream_start_session_contract(
        *,
        input_path: str,
        selected_detectors: list[str],
    ) -> object:
        build_calls.append((input_path, selected_detectors))
        return object()

    monkeypatch.setattr(
        "api.routers.sessions.build_api_stream_start_session_contract",
        fake_build_api_stream_start_session_contract,
    )

    class DummyPopen:
        def __init__(self, *args, **kwargs) -> None:
            pass

    monkeypatch.setattr("api.routers.sessions.subprocess.Popen", DummyPopen)

    response = request(
        "POST",
        "/sessions",
        json={
            "mode": "api_stream",
            "input_path": "https://example.com/live/index.m3u8",
            "selected_detectors": ["video_metrics", "video_blur"],
        },
    )

    assert response.status_code == 200
    assert build_calls == [
        (
            "https://example.com/live/index.m3u8",
            ["video_metrics", "video_blur"],
        )
    ]
    assert response.json() == {
        "session_id": "api-stream-session-123",
        "mode": "api_stream",
        "input_path": "https://example.com/live/index.m3u8",
        "selected_detectors": ["video_metrics", "video_blur"],
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


def test_cancel_session_allows_already_cancelling_state(monkeypatch) -> None:
    cancelled: list[str] = []

    def fake_request_session_cancel(session_id: str) -> None:
        cancelled.append(session_id)

    def fake_read_session_snapshot(session_id: str) -> dict[str, object]:
        return {
            "session": {
                "session_id": session_id,
                "mode": "api_stream",
                "input_path": "https://example.com/live/index.m3u8",
                "selected_detectors": ["video_metrics"],
                "status": "cancelling",
            },
            "progress": {
                "session_id": session_id,
                "status": "cancelling",
                "processed_count": 2,
                "total_count": 0,
                "current_item": "segment_001.ts",
                "latest_result_detector": "video_metrics",
                "latest_result_detectors": ["video_metrics"],
                "alert_count": 0,
                "last_updated_utc": "2026-04-22 10:00:00",
                "status_reason": "cancelling",
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

    response = request("POST", "/sessions/session-cancelling/cancel")

    assert response.status_code == 200
    assert cancelled == ["session-cancelling"]
    assert response.json() == {
        "session_id": "session-cancelling",
        "mode": "api_stream",
        "input_path": "https://example.com/live/index.m3u8",
        "selected_detectors": ["video_metrics"],
        "status": "cancelling",
    }


def test_cancel_session_rejects_terminal_state(monkeypatch) -> None:
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

    assert response.status_code == 409
    assert cancelled == []
    assert response.json() == {
        "detail": "Session cannot be cancelled from its current state",
        "error_code": "cancel_failed",
        "status_reason": "cancel_failed",
        "status_detail": "Session test-session-123 is already completed.",
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
