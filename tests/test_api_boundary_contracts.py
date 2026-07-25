"""FastAPI boundary tests for structured failures and stable detector/session shapes.

This suite protects the outer HTTP contract when backend internals move:

- read-only route smoke shapes
- detector catalog error handling and canonical catalog export
- fail-closed session snapshot validation
"""

import pytest

from api.errors import UNEXPECTED_BACKEND_ERROR_STATUS_DETAIL

from api.routers.sessions import SessionServiceCancelFailedError
from detectors.registry import list_available_detectors
from tests.api_boundary_test_support import request


@pytest.mark.parametrize(
    ("path", "expected_body"),
    [
        ("/health", {"status": "ok"}),
        ("/detectors", list),
    ],
)
def test_basic_read_only_routes_return_expected_smoke_shapes(
    path: str,
    expected_body: object,
) -> None:
    response = request("GET", path)

    assert response.status_code == 200
    body = response.json()
    if expected_body is list:
        assert isinstance(body, list)
    else:
        assert body == expected_body


def test_sessions_unexpected_failure_returns_structured_payload(monkeypatch) -> None:
    class DummyMetadata:
        def to_dict(self) -> dict[str, object]:
            return {
                "session_id": "test-session-123",
                "mode": "video_files",
                "input_path": "tests/fixtures/media/video_files/black_trigger.mp4",
                "selected_detectors": ["video_metrics"],
                "status": "pending",
            }

    monkeypatch.setattr(
        "api.routers.sessions.start_session_service",
        lambda mode, input_path, selected_detectors: DummyMetadata(),
    )

    def fake_model_validate(*args, **kwargs) -> None:
        _ = (args, kwargs)
        raise RuntimeError("response serialization blew up")

    monkeypatch.setattr(
        "api.routers.sessions.SessionSummaryResponse.model_validate",
        fake_model_validate,
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
        "detail": "Unexpected backend error",
        "error_code": "internal_error",
        "status_reason": "internal_error",
        "status_detail": UNEXPECTED_BACKEND_ERROR_STATUS_DETAIL,
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
        "status_detail": UNEXPECTED_BACKEND_ERROR_STATUS_DETAIL,
    }


def test_detectors_route_returns_canonical_registry_catalog_for_video_segments() -> None:
    """The API detector catalog should match the canonical registry contract."""
    expected_catalog = list_available_detectors("video_segments")
    response = request("GET", "/detectors?mode=video_segments")

    assert response.status_code == 200
    assert response.json() == expected_catalog


def test_read_session_malformed_nested_payload_fails_closed_with_structured_error(
    monkeypatch,
) -> None:
    def fake_read_session_snapshot_or_none(session_id: str) -> dict[str, object]:
        return {
            "session": {
                "session_id": session_id,
                "mode": "video_files",
                "input_path": "tests/fixtures/media/video_files/black_trigger.mp4",
                "selected_detectors": ["video_metrics"],
                "status": "running",
            },
            "progress": {
                "session_id": session_id,
                "status": "running",
                "processed_count": "two",
                "total_count": 4,
                "current_item": "segment_0002.ts",
                "latest_result_detector": "video_metrics",
                "latest_result_detectors": ["video_metrics"],
                "alert_count": 0,
                "last_updated_utc": "2026-04-22 10:00:00",
                "status_reason": "running",
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

    response = request("GET", "/sessions/test-session-123")

    assert response.status_code == 500
    assert response.json()["detail"] == "Unexpected backend error"
    assert response.json()["error_code"] == "internal_error"
    assert response.json()["status_reason"] == "internal_error"
    assert response.json()["status_detail"] == UNEXPECTED_BACKEND_ERROR_STATUS_DETAIL


def test_read_session_malformed_alert_and_result_payloads_fail_closed_with_structured_error(
    monkeypatch,
) -> None:
    def fake_read_session_snapshot_or_none(session_id: str) -> dict[str, object]:
        return {
            "session": {
                "session_id": session_id,
                "mode": "video_files",
                "input_path": "tests/fixtures/media/video_files/black_trigger.mp4",
                "selected_detectors": ["video_metrics"],
                "status": "running",
            },
            "progress": {
                "session_id": session_id,
                "status": "running",
                "processed_count": 2,
                "total_count": 4,
                "current_item": "segment_0002.ts",
                "latest_result_detector": "video_metrics",
                "latest_result_detectors": ["video_metrics"],
                "alert_count": 1,
                "last_updated_utc": "2026-04-22 10:00:00",
                "status_reason": "running",
                "status_detail": None,
            },
            "alerts": [
                {
                    "session_id": session_id,
                    "timestamp_utc": "2026-04-22 10:00:00",
                    "detector_id": "video_metrics",
                    "title": "Black screen detected",
                    "message": "Black content detected.",
                    "severity": "critical",
                    "source_name": "segment_0002.ts",
                }
            ],
            "results": [
                {
                    "session_id": session_id,
                    "detector_id": "video_metrics",
                    "payload": "broken",
                }
            ],
            "latest_result": {
                "session_id": session_id,
                "detector_id": "video_metrics",
                "payload": "broken",
            },
        }

    monkeypatch.setattr(
        "api.routers.sessions.read_session_snapshot_or_none",
        fake_read_session_snapshot_or_none,
    )

    response = request("GET", "/sessions/test-session-broken-alerts")

    assert response.status_code == 500
    body = response.json()
    assert body["detail"] == "Unexpected backend error"
    assert body["error_code"] == "internal_error"
    assert body["status_reason"] == "internal_error"
    assert body["status_detail"] == UNEXPECTED_BACKEND_ERROR_STATUS_DETAIL


def test_read_session_snapshot_contract_keeps_results_and_latest_result_shape_after_store_move(
    monkeypatch,
) -> None:
    """Session reads should keep the public snapshot shape stable above the store seam."""

    def fake_read_session_snapshot_or_none(session_id: str) -> dict[str, object]:
        ordered_results = [
            {
                "session_id": session_id,
                "detector_id": "video_metrics",
                "payload": {
                    "timestamp_utc": "2026-07-01 10:00:00",
                    "source_name": "segment_0000.ts",
                    "window_index": 0,
                    "black_ratio": 0.12,
                },
            },
            {
                "session_id": session_id,
                "detector_id": "video_blur",
                "payload": {
                    "timestamp_utc": "2026-07-01 10:00:00",
                    "source_name": "segment_0001.ts",
                    "window_index": 1,
                    "blur_score": 0.91,
                },
            },
        ]
        return {
            "session": {
                "session_id": session_id,
                "mode": "video_segments",
                "input_path": "/tmp/segments",
                "selected_detectors": ["video_metrics", "video_blur"],
                "status": "running",
            },
            "progress": {
                "session_id": session_id,
                "status": "running",
                "processed_count": 2,
                "total_count": 8,
                "current_item": "segment_0001.ts",
                "latest_result_detector": "video_blur",
                "latest_result_detectors": ["video_metrics", "video_blur"],
                "alert_count": 1,
                "last_updated_utc": "2026-07-01 10:00:05",
                "status_reason": "running",
                "status_detail": None,
            },
            "alerts": [],
            "results": ordered_results,
            "latest_result": ordered_results[-1],
        }

    monkeypatch.setattr(
        "api.routers.sessions.read_session_snapshot_or_none",
        fake_read_session_snapshot_or_none,
    )

    response = request("GET", "/sessions/test-session-store-results")

    assert response.status_code == 200
    body = response.json()
    assert tuple(body.keys()) == (
        "session",
        "progress",
        "alerts",
        "results",
        "latest_result",
    )
    assert [row["detector_id"] for row in body["results"]] == [
        "video_metrics",
        "video_blur",
    ]
    assert body["latest_result"] == body["results"][-1]
    assert body["latest_result"]["payload"]["blur_score"] == 0.91


@pytest.mark.parametrize(
    ("method", "path", "payload", "expected_status"),
    [
        ("GET", "/sessions/missing-session-id", None, 404),
        (
            "POST",
            "/sessions",
            {
                "mode": "video_files",
                "input_path": "missing.mp4",
                "selected_detectors": ["video_metrics"],
            },
            400,
        ),
        (
            "POST",
            "/sessions/test-session-123/cancel",
            None,
            409,
        ),
        (
            "POST",
            "/sessions",
            {"mode": "video_files"},
            422,
        ),
    ],
)
def test_error_responses_keep_consistent_envelope_keys(
    monkeypatch,
    method: str,
    path: str,
    payload: dict[str, object] | None,
    expected_status: int,
) -> None:
    if expected_status == 409:
        monkeypatch.setattr(
            "api.routers.sessions.cancel_session_service",
            lambda session_id: (_ for _ in ()).throw(
                SessionServiceCancelFailedError(
                    session_id,
                    "completed",
                )
            ),
        )

    response = request(method, path, json=payload)

    assert response.status_code == expected_status
    body = response.json()
    assert set(body) == {
        "detail",
        "error_code",
        "status_reason",
        "status_detail",
    }


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/sessions/..%5Cescape"),
        ("POST", "/sessions/..%5Cescape/cancel"),
    ],
)
def test_session_routes_reject_unsafe_session_ids_with_validation_error(
    method: str,
    path: str,
) -> None:
    response = request(method, path)

    assert response.status_code == 400
    assert response.json()["detail"] == "session directory requires a single safe path component"
    assert response.json()["error_code"] == "validation_failed"
    assert response.json()["status_reason"] == "validation_failed"
