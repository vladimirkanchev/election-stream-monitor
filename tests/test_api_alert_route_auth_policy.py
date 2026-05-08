"""Focused FastAPI auth-policy tests for the protected alerts router.

This file owns the authentication side of the shared alerts-router boundary:

- stable `401` mapping for missing, blank, and invalid credentials
- router-scoped protection versus unrelated routes
- the real API-key settings seam, including auth-disabled local runs
- auth-failure logging
- proof that auth failure short-circuits before rate limiting

Rate-limit behavior and response-contract checks live in the neighboring
alerts-router policy files so this module stays centered on one boundary
concern. That keeps the file readable as one catalog of admission rules rather
than mixing auth, throttling, and transport-contract assertions together.
"""

import logging

from tests.api_alert_test_support import (
    build_api_key_headers,
    build_authentication_failed_payload,
    install_alert_route_auth_failure,
    install_alert_route_auth_success,
    install_api_rate_limit_settings,
    install_empty_alert_route_services,
    install_real_alert_route_auth,
    reset_alert_route_rate_limit_state,
)
from tests.api_boundary_test_support import request


# Authentication policy


def test_get_session_alerts_maps_authentication_failure_to_401(monkeypatch) -> None:
    """Missing or invalid credentials should surface as the stable 401 envelope."""
    install_alert_route_auth_failure(monkeypatch, detail="Missing API key")

    response = request("GET", "/sessions/session-123/alerts")

    assert response.status_code == 401
    assert response.json() == build_authentication_failed_payload("Missing API key")


def test_get_session_alerts_allows_authenticated_requests(monkeypatch) -> None:
    """The alerts route should still work when the auth boundary accepts the caller."""
    install_alert_route_auth_success(monkeypatch, expected_key="valid-key")
    install_empty_alert_route_services(monkeypatch)

    response = request(
        "GET",
        "/sessions/session-123/alerts",
        headers=build_api_key_headers(),
    )

    assert response.status_code == 200
    assert response.json() == {
        "session_id": "session-123",
        "alerts": [],
    }


def test_alert_routes_are_protected_while_health_route_remains_unprotected(
    monkeypatch,
) -> None:
    """Router-scoped auth should protect alerts routes without becoming app-wide policy."""
    install_real_alert_route_auth(monkeypatch, enabled=True)

    alert_response = request("GET", "/sessions/session-123/alerts")
    health_response = request("GET", "/health")

    assert alert_response.status_code == 401
    assert alert_response.json() == build_authentication_failed_payload("Missing API key")
    assert health_response.status_code == 200
    assert health_response.json() == {"status": "ok"}


def test_get_session_alerts_treats_blank_api_key_header_as_missing(monkeypatch) -> None:
    """Whitespace-only API-key headers should be rejected at the real HTTP boundary."""
    install_real_alert_route_auth(monkeypatch, enabled=True)

    response = request(
        "GET",
        "/sessions/session-123/alerts",
        headers=build_api_key_headers("   "),
    )

    assert response.status_code == 401
    assert response.json() == build_authentication_failed_payload("Missing API key")


def test_authentication_failures_log_safe_boundary_context(monkeypatch, caplog) -> None:
    """Auth-boundary logs should include path and reason without leaking raw keys."""
    install_real_alert_route_auth(monkeypatch, enabled=True)

    with caplog.at_level(logging.WARNING, logger="api.alert_route_policy"):
        response = request(
            "GET",
            "/sessions/session-123/alerts",
            headers=build_api_key_headers("secret-raw-key"),
        )

    assert response.status_code == 401
    assert "auth_failed" in caplog.text
    assert "/sessions/session-123/alerts" in caplog.text
    assert "Invalid API key" in caplog.text
    assert "secret-raw-key" not in caplog.text


def test_blank_api_key_auth_failures_log_missing_key_reason(monkeypatch, caplog) -> None:
    """Whitespace-only keys should log the missing-key branch without leaking raw input."""
    install_real_alert_route_auth(monkeypatch, enabled=True)

    with caplog.at_level(logging.WARNING, logger="api.alert_route_policy"):
        response = request(
            "GET",
            "/sessions/session-123/alerts",
            headers=build_api_key_headers("   "),
        )

    assert response.status_code == 401
    assert "auth_failed" in caplog.text
    assert "Missing API key" in caplog.text


def test_get_session_alerts_returns_401_before_rate_limit_when_authentication_fails(
    monkeypatch,
) -> None:
    """Authentication should short-circuit before the limiter can spend route budget."""
    reset_alert_route_rate_limit_state()
    install_real_alert_route_auth(monkeypatch, enabled=True)
    install_api_rate_limit_settings(
        monkeypatch,
        enabled=True,
        max_requests=1,
        window_seconds=60,
    )

    response = request("GET", "/sessions/session-123/alerts")

    assert response.status_code == 401
    assert response.json() == build_authentication_failed_payload("Missing API key")


def test_get_session_alerts_skips_auth_when_disabled_in_settings(monkeypatch) -> None:
    """Disabled FastAPI auth should allow alert routes to use the shared service seam."""
    install_real_alert_route_auth(monkeypatch, enabled=False, install_services=True)

    response = request("GET", "/sessions/session-123/alerts")

    assert response.status_code == 200
    assert response.json() == {
        "session_id": "session-123",
        "alerts": [],
    }


def test_get_session_alerts_rejects_enabled_auth_without_configured_keys(
    monkeypatch,
) -> None:
    """Enabled auth without configured keys should fail clearly as boundary misconfiguration."""
    install_real_alert_route_auth(monkeypatch, enabled=True, allowed_api_keys=())

    response = request(
        "GET",
        "/sessions/session-123/alerts",
        headers=build_api_key_headers(),
    )

    assert response.status_code == 401
    assert response.json() == build_authentication_failed_payload(
        "API key authentication is enabled but no allowed API keys are configured"
    )


def test_get_session_alert_summary_rejects_wrong_header_name_even_with_valid_key(
    monkeypatch,
) -> None:
    """Only the documented ``X-API-Key`` header should satisfy the route auth contract."""
    install_real_alert_route_auth(monkeypatch, enabled=True)

    response = request(
        "GET",
        "/sessions/session-123/alerts/summary",
        headers={"X-Wrong-Key": "valid-key"},
    )

    assert response.status_code == 401
    assert response.json() == build_authentication_failed_payload("Missing API key")


def test_get_session_alert_incident_summary_rejects_invalid_key_with_same_401_contract(
    monkeypatch,
) -> None:
    """Incident-summary routes should share the same real invalid-key boundary behavior."""
    install_real_alert_route_auth(monkeypatch, enabled=True)

    response = request(
        "GET",
        "/sessions/session-123/alerts/incident-summary",
        headers=build_api_key_headers("wrong-key"),
    )

    assert response.status_code == 401
    assert response.json() == build_authentication_failed_payload("Invalid API key")
