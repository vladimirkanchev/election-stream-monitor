"""Focused rate-limit tests for session start and cancellation.

The session-control family intentionally reserves capacity for cancellation:
admitted starts consume both a strict spawn guard and the broader control
budget, while cancellation consumes only the broader budget.
"""

from collections.abc import Generator

import pytest

from analyzer_contract import InputMode
from api_auth import AuthPrincipal
from api_boundary_config import ApiRateLimitSettings
from api_rate_limit import reset_api_rate_limit_state
from session_models import SessionMetadata
from tests.api_boundary_sessions_test_support import (
    DEFAULT_VIDEO_FILES_INPUT,
    pending_metadata,
    session_cancel_payload,
    session_start_request_body,
)
from tests.api_boundary_test_support import request


@pytest.fixture(autouse=True)
def _reset_rate_limit_state() -> Generator[None, None, None]:
    """Keep the process-local limiter isolated across policy scenarios."""

    reset_api_rate_limit_state()
    yield
    reset_api_rate_limit_state()


def _install_session_route_policy(
    monkeypatch,
    *,
    enabled: bool,
    start_max_requests: int = 6,
    control_max_requests: int = 12,
) -> None:
    """Install deterministic auth and budget settings for one route scenario."""

    principal = AuthPrincipal(
        auth_type="api_key",
        subject="api-key:session-policy",
        key_id="session-policy",
    )
    monkeypatch.setattr(
        "api.http_auth_policy.authenticate_api_request",
        lambda **_: principal,
    )
    monkeypatch.setattr(
        "api.session_route_policy.get_session_start_rate_limit_settings",
        lambda: ApiRateLimitSettings(
            enabled=enabled,
            strategy="principal",
            window_seconds=60,
            max_requests=start_max_requests,
        ),
    )
    monkeypatch.setattr(
        "api.session_route_policy.get_session_control_rate_limit_settings",
        lambda: ApiRateLimitSettings(
            enabled=enabled,
            strategy="principal",
            window_seconds=60,
            max_requests=control_max_requests,
        ),
    )


def _install_session_services(monkeypatch) -> None:
    """Make route-policy tests independent of worker and store behavior."""

    def fake_start_session_service(
        *,
        mode: InputMode,
        input_path: str,
        selected_detectors: list[str],
    ) -> SessionMetadata:
        return pending_metadata(
            session_id="rate-limited-session",
            mode=mode,
            input_path=input_path,
            selected_detectors=selected_detectors,
        )

    monkeypatch.setattr(
        "api.routers.sessions.start_session_service",
        fake_start_session_service,
    )
    monkeypatch.setattr(
        "api.routers.sessions.cancel_session_service",
        lambda session_id: session_cancel_payload(session_id=session_id),
    )


def test_session_start_guard_reserves_control_capacity_for_cancellation(monkeypatch) -> None:
    """A rejected seventh start must not prevent an otherwise valid cancellation."""

    _install_session_route_policy(monkeypatch, enabled=True)
    _install_session_services(monkeypatch)

    for _ in range(6):
        assert request(
            "POST",
            "/sessions",
            json=session_start_request_body(),
        ).status_code == 200

    rejected_start = request(
        "POST",
        "/sessions",
        json=session_start_request_body(),
    )
    cancel_response = request("POST", "/sessions/rate-limited-session/cancel")

    assert rejected_start.status_code == 429
    assert cancel_response.status_code == 200
    assert cancel_response.json() == session_cancel_payload(
        session_id="rate-limited-session"
    )


def test_session_control_budget_is_shared_by_admitted_starts_and_cancellations(
    monkeypatch,
) -> None:
    """Starts and cancels share one bounded control family for each caller."""

    _install_session_route_policy(monkeypatch, enabled=True)
    _install_session_services(monkeypatch)

    for _ in range(6):
        assert request(
            "POST",
            "/sessions",
            json=session_start_request_body(),
        ).status_code == 200
    for _ in range(6):
        assert request("POST", "/sessions/rate-limited-session/cancel").status_code == 200

    rejected_cancel = request("POST", "/sessions/rate-limited-session/cancel")

    assert rejected_cancel.status_code == 429


def test_session_start_budget_remains_disabled_for_the_default_local_path(monkeypatch) -> None:
    """The local desktop path should not be throttled unless explicitly enabled."""

    _install_session_route_policy(monkeypatch, enabled=False)
    _install_session_services(monkeypatch)

    for _ in range(7):
        assert request(
            "POST",
            "/sessions",
            json=session_start_request_body(),
        ).status_code == 200


@pytest.mark.parametrize(
    ("body", "field_name"),
    [
        (
            {
                "mode": "video_files",
                "input_path": "x" * 4097,
                "selected_detectors": [],
            },
            "body.input_path",
        ),
        (
            {
                "mode": "video_files",
                "input_path": DEFAULT_VIDEO_FILES_INPUT,
                "selected_detectors": ["video_metrics"] * 33,
            },
            "body.selected_detectors",
        ),
        (
            {
                "mode": "video_files",
                "input_path": DEFAULT_VIDEO_FILES_INPUT,
                "selected_detectors": ["x" * 129],
            },
            "body.selected_detectors.0",
        ),
    ],
)
def test_start_session_rejects_oversized_operator_input(
    body: dict[str, object],
    field_name: str,
) -> None:
    """Start validation should reject bounded fields before worker creation."""

    response = request("POST", "/sessions", json=body)

    assert response.status_code == 422
    assert response.json()["detail"] == "Request validation failed"
    assert field_name in response.json()["status_detail"]
