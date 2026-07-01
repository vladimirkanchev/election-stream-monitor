"""Focused FastAPI adapter tests for cancel-route behavior and shared error mapping.

The shared session service owns cancel validity. This suite keeps the route
layer focused on HTTP status mapping and on the transient `cancelling` ->
durable `cancelled` flow visible to API callers.
"""

import pytest
import config

from api.routers.sessions import (
    SessionServiceCancelFailedError,
    SessionServiceNotFoundError,
)
from session_store_file import FileSessionStore
from tests.api_boundary_sessions_test_support import (
    session_cancel_payload,
    session_not_found_payload,
    validation_error_payload,
)
from tests.api_boundary_test_support import request
from tests.session_runner_execution_test_support import (
    build_metadata,
    build_progress,
    persist_session_state,
    settle_cancelled_local_session_once,
)


@pytest.mark.parametrize(
    ("path", "service_attr", "error_factory", "expected_status", "expected_payload"),
    [
        (
            "/sessions/test-session-123/cancel",
            "cancel_session_service",
            lambda: ValueError("session directory requires a single safe path component"),
            400,
            validation_error_payload("session directory requires a single safe path component"),
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
            session_not_found_payload("missing-session-id"),
        ),
    ],
)
def test_session_cancel_adapter_error_mapping(
    monkeypatch,
    path: str,
    service_attr: str,
    error_factory,
    expected_status: int,
    expected_payload: dict[str, object],
) -> None:
    monkeypatch.setattr(
        f"api.routers.sessions.{service_attr}",
        lambda *args, **kwargs: (_ for _ in ()).throw(error_factory()),
    )

    response = request("POST", path)

    assert response.status_code == expected_status
    assert response.json() == expected_payload


def test_cancel_session_happy_path(monkeypatch) -> None:
    """The route should pass through the shared cancel summary unchanged."""
    calls: list[str] = []

    def fake_cancel_session_service(session_id: str) -> dict[str, object]:
        calls.append(session_id)
        return session_cancel_payload(session_id=session_id)

    monkeypatch.setattr(
        "api.routers.sessions.cancel_session_service",
        fake_cancel_session_service,
    )

    response = request("POST", "/sessions/test-session-123/cancel")

    assert response.status_code == 200
    assert calls == ["test-session-123"]
    assert response.json() == session_cancel_payload(session_id="test-session-123")


def test_cancel_route_keeps_snapshot_honest_until_runtime_settles_cancelled(
    monkeypatch,
    tmp_path,
) -> None:
    """The API should return `cancelling` first, then expose `cancelled` after worker settlement."""
    monkeypatch.setattr(config, "SESSION_OUTPUT_FOLDER", tmp_path / "sessions")
    metadata = build_metadata(
        session_id="session-route-cancel-runtime",
        mode="video_files",
    )
    progress = build_progress(
        session_id=metadata.session_id,
        status="running",
        processed_count=0,
        total_count=1,
    )
    persist_session_state(metadata, progress)

    cancel_response = request("POST", f"/sessions/{metadata.session_id}/cancel")
    immediate_read = request("GET", f"/sessions/{metadata.session_id}")

    assert cancel_response.status_code == 200
    assert cancel_response.json() == session_cancel_payload(
        session_id=metadata.session_id,
        input_path="input-path",
    )
    assert immediate_read.status_code == 200
    assert immediate_read.json()["session"]["status"] == "running"
    assert immediate_read.json()["progress"]["status"] == "running"

    bundle_called = settle_cancelled_local_session_once(
        tmp_path=tmp_path,
        metadata=metadata,
        progress=progress,
        session_store=FileSessionStore(),
    )

    settled_read = request("GET", f"/sessions/{metadata.session_id}")

    assert bundle_called is False
    assert settled_read.status_code == 200
    assert settled_read.json()["session"]["status"] == "cancelled"
    assert settled_read.json()["progress"]["status"] == "cancelled"
    assert settled_read.json()["progress"]["status_reason"] == "cancel_requested"
