"""Focused FastAPI adapter tests for session read routes."""

from tests.api_boundary_sessions_test_support import (
    session_not_found_payload,
    validation_error_payload,
)
from tests.api_boundary_test_support import request


def test_sessions_missing_id() -> None:
    response = request("GET", "/sessions/missing-session-id")
    assert response.status_code == 404
    assert response.json() == session_not_found_payload("missing-session-id")


def test_get_session_returns_fully_populated_snapshot(monkeypatch) -> None:
    snapshot: dict[str, object] = {
        "session": {
            "session_id": "test-session-123",
            "mode": "video_files",
            "input_path": "/tmp/input.mp4",
            "selected_detectors": ["video_metrics"],
            "status": "running",
        },
        "progress": {
            "session_id": "test-session-123",
            "status": "running",
            "processed_count": 1,
            "total_count": 2,
            "current_item": "segment_001.ts",
            "latest_result_detector": "video_metrics",
            "latest_result_detectors": ["video_metrics"],
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
                "message": "Black segment exceeded threshold.",
                "severity": "warning",
                "source_name": "segment_001.ts",
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

    monkeypatch.setattr(
        "api.routers.sessions.read_session_snapshot_or_none",
        lambda session_id: snapshot,
    )

    response = request("GET", "/sessions/test-session-123")

    assert response.status_code == 200
    payload = response.json()
    assert payload["session"] == snapshot["session"]
    assert payload["progress"] == snapshot["progress"]
    assert payload["results"] == snapshot["results"]
    assert payload["latest_result"] == snapshot["latest_result"]
    assert payload["alerts"][0]["detector_id"] == "video_metrics"
    assert payload["alerts"][0]["source_name"] == "segment_001.ts"


def test_get_session_validation_failure_returns_structured_error(monkeypatch) -> None:
    detail = "session directory requires a single safe path component"
    monkeypatch.setattr(
        "api.routers.sessions.read_session_snapshot_or_none",
        lambda session_id: (_ for _ in ()).throw(ValueError(detail)),
    )

    response = request("GET", "/sessions/bad-session-id")

    assert response.status_code == 400
    assert response.json() == validation_error_payload(detail)
