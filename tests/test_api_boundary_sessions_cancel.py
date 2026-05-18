"""Focused FastAPI adapter tests for session cancel routes and shared error mapping."""

import pytest

from api.routers.sessions import (
    SessionServiceCancelFailedError,
    SessionServiceNotFoundError,
)
from tests.api_boundary_sessions_test_support import (
    session_cancel_payload,
    session_not_found_payload,
    validation_error_payload,
)
from tests.api_boundary_test_support import request


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
