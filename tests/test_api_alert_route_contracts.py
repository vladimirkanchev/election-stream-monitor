"""Focused FastAPI response-contract tests for the protected alerts router.

This file owns the public response-shaping side of the alerts-router boundary:

- `Retry-After` presence on `429` responses
- absence of limiter headers when no throttling happened
- OpenAPI exposure of the stable `429` error envelope

Authentication and rate-limit policy mechanics live in neighboring files so
this module can stay centered on client-visible HTTP contracts. That keeps the
contract assertions separate from the policy mechanics that cause them.
"""

from api.app import app
from tests.api_alert_test_support import (
    build_api_key_headers,
    install_rate_limited_alert_routes,
)
from tests.api_boundary_test_support import request


# `429` header shaping


def test_get_session_alerts_sets_retry_after_header_on_429(monkeypatch) -> None:
    """Protected alerts routes should expose a coarse Retry-After header on 429."""
    install_rate_limited_alert_routes(
        monkeypatch,
        window_seconds=7,
    )

    first_response = request(
        "GET",
        "/sessions/session-123/alerts",
        headers=build_api_key_headers(),
    )
    second_response = request(
        "GET",
        "/sessions/session-123/alerts",
        headers=build_api_key_headers(),
    )

    assert first_response.status_code == 200
    assert second_response.status_code == 429
    assert second_response.headers["Retry-After"] == "7"
    assert second_response.headers["Retry-After"].isdigit()


def test_ip_strategy_429_sets_retry_after_header(monkeypatch) -> None:
    """IP-strategy rejections should expose the same coarse Retry-After header."""
    install_rate_limited_alert_routes(
        monkeypatch,
        allowed_api_keys=("alpha-key", "beta-key"),
        strategy="ip",
        window_seconds=11,
    )

    first_response = request(
        "GET",
        "/sessions/session-123/alerts",
        headers=build_api_key_headers("alpha-key"),
    )
    second_response = request(
        "GET",
        "/sessions/session-123/alerts",
        headers=build_api_key_headers("beta-key"),
    )

    assert first_response.status_code == 200
    assert second_response.status_code == 429
    assert second_response.headers["Retry-After"] == "11"
    assert second_response.headers["Retry-After"].isdigit()


def test_incident_route_429_sets_retry_after_header(monkeypatch) -> None:
    """Incident routes should expose the same coarse Retry-After header on 429."""
    install_rate_limited_alert_routes(
        monkeypatch,
        window_seconds=9,
    )

    first_response = request(
        "GET",
        "/sessions/session-123/alerts/incident-summary",
        headers=build_api_key_headers(),
    )
    second_response = request(
        "GET",
        "/sessions/session-123/alerts/incident-summary",
        headers=build_api_key_headers(),
    )

    assert first_response.status_code == 200
    assert second_response.status_code == 429
    assert second_response.headers["Retry-After"] == "9"
    assert second_response.headers["Retry-After"].isdigit()


def test_alert_route_responses_do_not_include_retry_after_when_limiter_is_disabled(
    monkeypatch,
) -> None:
    """Ordinary successful responses should not carry limiter headers when throttling is off."""
    install_rate_limited_alert_routes(
        monkeypatch,
        rate_limit_enabled=False,
    )

    response = request(
        "GET",
        "/sessions/session-123/alerts",
        headers=build_api_key_headers(),
    )

    assert response.status_code == 200
    assert "Retry-After" not in response.headers


# OpenAPI contract exposure


def test_raw_alert_route_openapi_contract_advertises_429_rate_limit_response() -> None:
    """Protected raw alert routes should advertise the stable 429 envelope in OpenAPI."""
    route_contract = app.openapi()["paths"]["/sessions/{session_id}/alerts"]["get"]
    responses = route_contract["responses"]

    assert "429" in responses
    assert responses["429"]["description"] == "Rate limit exceeded"
    schema_ref = responses["429"]["content"]["application/json"]["schema"]["$ref"]
    assert schema_ref.endswith("/ApiRateLimitErrorResponse")


def test_incident_route_openapi_contract_advertises_429_rate_limit_response() -> None:
    """Incident routes should advertise the same stable 429 envelope in OpenAPI."""
    route_contract = app.openapi()["paths"]["/sessions/{session_id}/alerts/incident-summary"][
        "get"
    ]
    responses = route_contract["responses"]

    assert "429" in responses
    assert responses["429"]["description"] == "Rate limit exceeded"
    schema_ref = responses["429"]["content"]["application/json"]["schema"]["$ref"]
    assert schema_ref.endswith("/ApiRateLimitErrorResponse")
