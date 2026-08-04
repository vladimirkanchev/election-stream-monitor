"""Focused resource-policy tests for playback-source resolution."""

import logging
from collections.abc import Generator

import pytest

from api.app import app
from api_auth import AuthPrincipal
from api_boundary_config import ApiRateLimitSettings
from api_rate_limit import reset_api_rate_limit_state
from tests.api_alert_test_support import build_rate_limit_exceeded_payload
from tests.api_boundary_test_support import request


@pytest.fixture(autouse=True)
def _reset_rate_limit_state() -> Generator[None, None, None]:
    """Keep the process-local playback budget isolated between scenarios."""

    reset_api_rate_limit_state()
    yield
    reset_api_rate_limit_state()


def _install_playback_route_policy(
    monkeypatch,
    *,
    enabled: bool,
    max_requests: int = 30,
) -> None:
    """Install deterministic auth, budget, and resolution seams for one case."""

    principal = AuthPrincipal(
        auth_type="api_key",
        subject="api-key:playback-policy",
        key_id="playback-policy",
    )
    monkeypatch.setattr(
        "api.http_auth_policy.authenticate_api_request",
        lambda **_: principal,
    )
    monkeypatch.setattr(
        "api.playback_route_policy.get_playback_resolution_rate_limit_settings",
        lambda: ApiRateLimitSettings(
            enabled=enabled,
            strategy="principal",
            window_seconds=60,
            max_requests=max_requests,
        ),
    )
    monkeypatch.setattr(
        "api.routers.playback.validate_source_input",
        lambda _mode, input_path: input_path,
    )
    monkeypatch.setattr(
        "api.routers.playback.resolve_playback_source",
        lambda **_: "/tmp/resolved-playback.mp4",
    )


def _playback_request_body() -> dict[str, object]:
    """Return the smallest valid local playback request body."""

    return {
        "mode": "video_files",
        "input_path": "clip.mp4",
        "current_item": None,
    }


def test_playback_resolution_uses_a_dedicated_rate_limit_budget(monkeypatch, caplog) -> None:
    """Source resolution should reject the next request after its own budget."""

    _install_playback_route_policy(monkeypatch, enabled=True, max_requests=2)

    with caplog.at_level(logging.INFO, logger="api.http_rate_limit_policy"):
        first = request("POST", "/playback/resolve", json=_playback_request_body())
        second = request("POST", "/playback/resolve", json=_playback_request_body())
        rejected = request("POST", "/playback/resolve", json=_playback_request_body())

    assert first.status_code == 200
    assert second.status_code == 200
    assert rejected.status_code == 429
    assert rejected.json() == build_rate_limit_exceeded_payload(
        "Too many requests for the configured window."
    )
    assert rejected.headers["Retry-After"] == "60"
    assert "budget=playback-resolution" in caplog.text


def test_playback_resolution_stays_unthrottled_in_default_local_mode(monkeypatch) -> None:
    """The explicit local path should not spend a playback budget by default."""

    _install_playback_route_policy(monkeypatch, enabled=False, max_requests=1)

    for _ in range(2):
        assert request("POST", "/playback/resolve", json=_playback_request_body()).status_code == 200


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("input_path", "x" * 4097),
        ("current_item", "x" * 1025),
    ],
)
def test_playback_resolution_rejects_oversized_request_strings(
    field_name: str,
    value: str,
) -> None:
    """Field bounds should run before source or filesystem validation."""

    body = _playback_request_body()
    body[field_name] = value

    response = request("POST", "/playback/resolve", json=body)

    assert response.status_code == 422
    assert response.json()["detail"] == "Request validation failed"
    assert f"body.{field_name}" in response.json()["status_detail"]


def test_playback_route_advertises_the_shared_rate_limit_response() -> None:
    """OpenAPI should expose the rate-limit contract to API clients."""

    responses = app.openapi()["paths"]["/playback/resolve"]["post"]["responses"]

    assert responses["429"]["description"] == "Rate limit exceeded"
