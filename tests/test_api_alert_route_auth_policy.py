"""Focused FastAPI auth-policy tests for the protected alerts router.

This file owns the authentication side of the shared alerts-router boundary:

- stable `401` mapping for missing, blank, and invalid credentials
- router-scoped protection versus unrelated routes
- the real API-key settings seam, including auth-disabled local runs
- cross-route consistency for the protected alerts family
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


def _assert_authentication_failed(
    response,
    *,
    detail: str,
) -> None:
    """Assert the stable protected-route `401` payload for one auth failure branch."""
    assert response.status_code == 401
    assert response.json() == build_authentication_failed_payload(detail)


def _request_with_invalid_api_key(path: str):
    """Issue one protected-route request with the documented header and a wrong key."""
    return request(
        "GET",
        path,
        headers=build_api_key_headers("wrong-key"),
    )


def test_get_session_alerts_maps_authentication_failure_to_401(monkeypatch) -> None:
    """Missing or invalid credentials should surface as the stable 401 envelope."""
    install_alert_route_auth_failure(monkeypatch, detail="Missing API key")

    response = request("GET", "/sessions/session-123/alerts")

    _assert_authentication_failed(response, detail="Missing API key")


def test_get_session_alert_timeline_rejects_missing_api_key_with_same_401_contract(
    monkeypatch,
) -> None:
    """Timeline routes should share the same missing-key contract as raw alerts."""
    install_real_alert_route_auth(monkeypatch, enabled=True)

    response = request("GET", "/sessions/session-123/alerts/timeline")

    _assert_authentication_failed(response, detail="Missing API key")


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

    _assert_authentication_failed(alert_response, detail="Missing API key")
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

    _assert_authentication_failed(response, detail="Missing API key")


def test_invalid_key_failure_does_not_block_later_valid_authenticated_request(
    monkeypatch,
) -> None:
    """Rejected callers should not poison later valid access to the protected route."""
    reset_alert_route_rate_limit_state()
    install_real_alert_route_auth(monkeypatch, enabled=True)
    install_api_rate_limit_settings(
        monkeypatch,
        enabled=True,
        max_requests=1,
        window_seconds=60,
    )
    install_empty_alert_route_services(monkeypatch)

    rejected_response = _request_with_invalid_api_key("/sessions/session-123/alerts")
    allowed_response = request(
        "GET",
        "/sessions/session-123/alerts",
        headers=build_api_key_headers(),
    )

    _assert_authentication_failed(rejected_response, detail="Invalid API key")
    assert allowed_response.status_code == 200
    assert allowed_response.json() == {
        "session_id": "session-123",
        "alerts": [],
    }


def test_authentication_failures_log_safe_boundary_context(monkeypatch, caplog) -> None:
    """Auth logs should retain path and code without recording key material."""
    configured_key = "configured-alert-key-secret"
    presented_key = "presented-alert-key-secret"
    install_real_alert_route_auth(
        monkeypatch,
        enabled=True,
        allowed_api_keys=(configured_key,),
    )

    with caplog.at_level(logging.WARNING, logger="api.http_auth_policy"):
        response = request(
            "GET",
            "/sessions/session-123/alerts",
            headers=build_api_key_headers(presented_key),
        )

    assert response.status_code == 401
    assert "auth_failed" in caplog.text
    assert "/sessions/session-123/alerts" in caplog.text
    assert "reason_code=invalid_api_key" in caplog.text
    assert "Invalid API key" not in caplog.text
    assert configured_key not in caplog.text
    assert presented_key not in caplog.text


def test_blank_api_key_auth_failures_log_missing_key_reason(monkeypatch, caplog) -> None:
    """Whitespace-only keys should log a missing-key code without raw input."""
    install_real_alert_route_auth(monkeypatch, enabled=True)

    with caplog.at_level(logging.WARNING, logger="api.http_auth_policy"):
        response = request(
            "GET",
            "/sessions/session-123/alerts",
            headers=build_api_key_headers("   "),
        )

    assert response.status_code == 401
    assert "auth_failed" in caplog.text
    assert "reason_code=missing_api_key" in caplog.text
    assert "Missing API key" not in caplog.text


def test_authentication_logs_do_not_use_untrusted_error_detail(monkeypatch, caplog) -> None:
    """A future auth error detail must not become credential-bearing log text."""
    leaked_detail = "provider rejected api_key=unexpected-secret"
    install_alert_route_auth_failure(monkeypatch, detail=leaked_detail)

    with caplog.at_level(logging.WARNING, logger="api.http_auth_policy"):
        response = request("GET", "/sessions/session-123/alerts")

    assert response.status_code == 401
    assert "reason_code=authentication_failed" in caplog.text
    assert leaked_detail not in caplog.text
    assert "unexpected-secret" not in caplog.text


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

    _assert_authentication_failed(response, detail="Missing API key")


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

    _assert_authentication_failed(
        response,
        detail="API key authentication is enabled but no allowed API keys are configured",
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

    _assert_authentication_failed(response, detail="Missing API key")


def test_get_session_alert_incident_summary_rejects_invalid_key_with_same_401_contract(
    monkeypatch,
) -> None:
    """Incident-summary routes should share the same real invalid-key boundary behavior."""
    install_real_alert_route_auth(monkeypatch, enabled=True)

    response = _request_with_invalid_api_key("/sessions/session-123/alerts/incident-summary")

    _assert_authentication_failed(response, detail="Invalid API key")


def test_get_session_alert_summary_and_timeline_reject_invalid_key_with_same_401_contract(
    monkeypatch,
) -> None:
    """Protected alert routes should share the same invalid-key 401 envelope."""
    install_real_alert_route_auth(monkeypatch, enabled=True)

    summary_response = _request_with_invalid_api_key("/sessions/session-123/alerts/summary")
    timeline_response = _request_with_invalid_api_key("/sessions/session-123/alerts/timeline")

    _assert_authentication_failed(summary_response, detail="Invalid API key")
    _assert_authentication_failed(timeline_response, detail="Invalid API key")
