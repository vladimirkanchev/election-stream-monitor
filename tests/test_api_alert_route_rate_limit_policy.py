"""Focused FastAPI rate-limit-policy tests for the protected alerts router.

This file owns the rate-limiting side of the shared alerts-router boundary:

- principal, IP, and local-fallback limiter identities
- budget sharing across the protected route family
- proof that unrelated public routes stay usable after protected-route throttling
- rate-limit logging and host-fallback behavior
- downstream `400` and `404` outcomes after boundary admission
- exact fixed-window behavior at the real HTTP layer

Authentication-only behavior and response-contract checks live in neighboring
files so this module can read like one policy catalog. The split is
intentional: this file is where reviewers should look first for the actual
alerts-router throttling rules and edge cases.
"""

import hashlib
import logging

import httpx

from tests.api_alert_test_support import (
    build_api_key_headers,
    build_rate_limit_exceeded_payload,
    build_session_not_found_payload,
    build_validation_error_payload,
    install_rate_limited_alert_routes,
)
from tests.api_boundary_test_support import request


# Principal-strategy and fixed-window behavior


def _assert_rate_limit_exceeded(
    response: httpx.Response,
    *,
    retry_after: str | None = None,
) -> None:
    """Assert the shared protected-route `429` payload and optional retry-after value."""
    assert response.status_code == 429
    assert response.json() == build_rate_limit_exceeded_payload(
        "Too many requests for the configured window."
    )
    if retry_after is not None:
        assert response.headers["Retry-After"] == retry_after


def _exhaust_alert_route_budget() -> tuple[httpx.Response, httpx.Response]:
    """Spend one caller's raw-alert budget and return the admitted and rejected responses."""
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
    return first_response, second_response


def test_get_session_alerts_returns_429_after_exceeding_rate_limit(monkeypatch) -> None:
    """One caller should receive the shared 429 envelope after exhausting its budget."""
    install_rate_limited_alert_routes(
        monkeypatch,
        max_requests=2,
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
    third_response = request(
        "GET",
        "/sessions/session-123/alerts",
        headers=build_api_key_headers(),
    )

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    _assert_rate_limit_exceeded(third_response)


def test_health_route_remains_usable_after_alert_route_hits_rate_limit(monkeypatch) -> None:
    """A protected-route 429 should not change unrelated unprotected route behavior."""
    install_rate_limited_alert_routes(monkeypatch)

    first_alert_response, second_alert_response = _exhaust_alert_route_budget()
    health_response = request("GET", "/health")

    assert first_alert_response.status_code == 200
    _assert_rate_limit_exceeded(second_alert_response)
    assert health_response.status_code == 200
    assert health_response.json() == {"status": "ok"}


def test_docs_route_remains_usable_after_alert_route_hits_rate_limit(monkeypatch) -> None:
    """Protected-route rate limits should not spill into public documentation routes."""
    install_rate_limited_alert_routes(monkeypatch)

    first_alert_response, second_alert_response = _exhaust_alert_route_budget()
    docs_response = request("GET", "/docs")

    assert first_alert_response.status_code == 200
    _assert_rate_limit_exceeded(second_alert_response)
    assert docs_response.status_code == 200


def test_get_session_alerts_reopens_budget_exactly_at_window_boundary(monkeypatch) -> None:
    """The real HTTP boundary should reopen the budget exactly when the window expires."""
    install_rate_limited_alert_routes(
        monkeypatch,
        max_requests=1,
        window_seconds=10,
    )

    times = iter([100.0, 109.0, 110.0])
    monkeypatch.setattr("api_rate_limit.monotonic", lambda: next(times))

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
    third_response = request(
        "GET",
        "/sessions/session-123/alerts",
        headers=build_api_key_headers(),
    )

    assert first_response.status_code == 200
    assert second_response.status_code == 429
    assert third_response.status_code == 200


def test_rate_limit_rejections_log_strategy_and_safe_subject(monkeypatch, caplog) -> None:
    """Rate-limit logs should include strategy and subject without leaking raw keys."""
    install_rate_limited_alert_routes(monkeypatch)
    fingerprint = hashlib.sha256("valid-key".encode("utf-8")).hexdigest()[:12]

    with caplog.at_level(logging.INFO, logger="api.alert_route_policy"):
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
    assert "rate_limit_exceeded" in caplog.text
    assert "/sessions/session-123/alerts" in caplog.text
    assert "strategy=principal" in caplog.text
    assert f"subject=principal:{fingerprint}" in caplog.text
    assert "valid-key" not in caplog.text


# Alternate IP-strategy and subject-resolution behavior


def test_ip_strategy_rate_limit_rejections_log_safe_host_subject(monkeypatch, caplog) -> None:
    """IP-strategy limiter logs should use the host-based subject instead of key identity."""
    install_rate_limited_alert_routes(
        monkeypatch,
        allowed_api_keys=("alpha-key", "beta-key"),
        strategy="ip",
    )

    with caplog.at_level(logging.INFO, logger="api.alert_route_policy"):
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
    assert "rate_limit_exceeded" in caplog.text
    assert "strategy=ip" in caplog.text
    assert "subject=ip:" in caplog.text
    assert "alpha-key" not in caplog.text
    assert "beta-key" not in caplog.text


def test_ip_strategy_rate_limit_rejections_fall_back_to_unknown_host_subject(
    monkeypatch,
    caplog,
) -> None:
    """Missing request-host information should fall back to the stable unknown-host subject."""
    install_rate_limited_alert_routes(
        monkeypatch,
        allowed_api_keys=("alpha-key", "beta-key"),
        strategy="ip",
    )
    monkeypatch.setattr("api.alert_route_policy._get_request_host", lambda request: None)

    with caplog.at_level(logging.INFO, logger="api.alert_route_policy"):
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
    assert "subject=ip:unknown" in caplog.text


def test_ip_strategy_unknown_host_returns_real_429_with_retry_after(monkeypatch) -> None:
    """Unknown-host IP strategy should still enforce and shape the real HTTP 429 response."""
    install_rate_limited_alert_routes(
        monkeypatch,
        allowed_api_keys=("alpha-key", "beta-key"),
        strategy="ip",
        window_seconds=13,
    )
    monkeypatch.setattr("api.alert_route_policy._get_request_host", lambda request: None)

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
    assert second_response.json() == build_rate_limit_exceeded_payload(
        "Too many requests for the configured window."
    )
    assert second_response.headers["Retry-After"] == "13"


def test_local_fallback_rate_limit_rejections_log_local_subject(monkeypatch, caplog) -> None:
    """Auth-disabled limiter logs should identify the deterministic local fallback subject."""
    install_rate_limited_alert_routes(
        monkeypatch,
        auth_enabled=False,
    )

    with caplog.at_level(logging.INFO, logger="api.alert_route_policy"):
        first_response = request("GET", "/sessions/session-123/alerts")
        second_response = request("GET", "/sessions/session-123/alerts")

    assert first_response.status_code == 200
    assert second_response.status_code == 429
    assert "rate_limit_exceeded" in caplog.text
    assert "auth_type=local" in caplog.text
    assert "subject=principal:local-api-client" in caplog.text


# Budget sharing and downstream outcomes after boundary admission


def test_get_session_alerts_keeps_rate_limits_separate_per_api_key(monkeypatch) -> None:
    """Distinct authenticated callers should keep independent per-principal budgets."""
    install_rate_limited_alert_routes(
        monkeypatch,
        allowed_api_keys=("alpha-key", "beta-key"),
    )

    alpha_first = request(
        "GET",
        "/sessions/session-123/alerts",
        headers=build_api_key_headers("alpha-key"),
    )
    beta_first = request(
        "GET",
        "/sessions/session-123/alerts",
        headers=build_api_key_headers("beta-key"),
    )
    alpha_second = request(
        "GET",
        "/sessions/session-123/alerts",
        headers=build_api_key_headers("alpha-key"),
    )

    assert alpha_first.status_code == 200
    assert beta_first.status_code == 200
    assert alpha_second.status_code == 429
    assert alpha_second.json() == build_rate_limit_exceeded_payload(
        "Too many requests for the configured window."
    )


def test_get_session_alerts_can_rate_limit_by_request_host_instead_of_api_key(
    monkeypatch,
) -> None:
    """IP strategy should bucket requests by request host instead of authenticated principal."""
    install_rate_limited_alert_routes(
        monkeypatch,
        allowed_api_keys=("alpha-key", "beta-key"),
        strategy="ip",
    )

    alpha_response = request(
        "GET",
        "/sessions/session-123/alerts",
        headers=build_api_key_headers("alpha-key"),
    )
    beta_response = request(
        "GET",
        "/sessions/session-123/alerts",
        headers=build_api_key_headers("beta-key"),
    )

    assert alpha_response.status_code == 200
    assert beta_response.status_code == 429
    assert beta_response.json() == build_rate_limit_exceeded_payload(
        "Too many requests for the configured window."
    )


def test_alert_routes_share_one_rate_limit_budget_across_route_family(monkeypatch) -> None:
    """The router-level limiter should share one caller budget across raw and timeline routes."""
    install_rate_limited_alert_routes(
        monkeypatch,
        max_requests=2,
    )

    list_response = request(
        "GET",
        "/sessions/session-123/alerts",
        headers=build_api_key_headers(),
    )
    summary_response = request(
        "GET",
        "/sessions/session-123/alerts/summary",
        headers=build_api_key_headers(),
    )
    timeline_response = request(
        "GET",
        "/sessions/session-123/alerts/timeline",
        headers=build_api_key_headers(),
    )

    assert list_response.status_code == 200
    assert summary_response.status_code == 200
    assert timeline_response.status_code == 429
    assert timeline_response.json() == build_rate_limit_exceeded_payload(
        "Too many requests for the configured window."
    )


def test_local_fallback_budget_is_shared_across_alert_route_family(monkeypatch) -> None:
    """Auth-disabled local fallback should still share one budget across the alerts router."""
    install_rate_limited_alert_routes(
        monkeypatch,
        auth_enabled=False,
        max_requests=2,
    )

    list_response = request("GET", "/sessions/session-123/alerts")
    summary_response = request("GET", "/sessions/session-123/alerts/summary")
    timeline_response = request("GET", "/sessions/session-123/alerts/timeline")

    assert list_response.status_code == 200
    assert summary_response.status_code == 200
    assert timeline_response.status_code == 429
    assert timeline_response.json() == build_rate_limit_exceeded_payload(
        "Too many requests for the configured window."
    )


def test_get_session_alerts_uses_local_fallback_rate_limit_subject_when_auth_is_disabled(
    monkeypatch,
) -> None:
    """Auth-disabled local runs should still use one deterministic router-level budget."""
    install_rate_limited_alert_routes(
        monkeypatch,
        auth_enabled=False,
    )

    first_response = request("GET", "/sessions/session-123/alerts")
    second_response = request("GET", "/sessions/session-123/alerts")

    assert first_response.status_code == 200
    assert second_response.status_code == 429
    assert second_response.json() == build_rate_limit_exceeded_payload(
        "Too many requests for the configured window."
    )


def test_get_session_alert_incident_summary_maps_rate_limit_to_429(
    monkeypatch,
) -> None:
    """Incident routes should reuse the same router-level 429 envelope and limiter policy."""
    install_rate_limited_alert_routes(monkeypatch)

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
    assert second_response.json() == build_rate_limit_exceeded_payload(
        "Too many requests for the configured window."
    )


def test_get_session_alert_timeline_returns_stable_429_contract(monkeypatch) -> None:
    """Timeline routes should keep the same 429 payload shape and retry-after contract."""
    install_rate_limited_alert_routes(
        monkeypatch,
        window_seconds=17,
    )

    first_response = request(
        "GET",
        "/sessions/session-123/alerts/timeline",
        headers=build_api_key_headers(),
    )
    second_response = request(
        "GET",
        "/sessions/session-123/alerts/timeline",
        headers=build_api_key_headers(),
    )

    assert first_response.status_code == 200
    _assert_rate_limit_exceeded(second_response, retry_after="17")


def test_get_session_alert_summary_returns_stable_429_contract(monkeypatch) -> None:
    """Summary routes should keep the same 429 payload shape and Retry-After header."""
    install_rate_limited_alert_routes(
        monkeypatch,
        window_seconds=19,
    )

    first_response = request(
        "GET",
        "/sessions/session-123/alerts/summary",
        headers=build_api_key_headers(),
    )
    second_response = request(
        "GET",
        "/sessions/session-123/alerts/summary",
        headers=build_api_key_headers(),
    )

    assert first_response.status_code == 200
    _assert_rate_limit_exceeded(second_response, retry_after="19")


def test_authenticated_missing_session_requests_count_against_rate_limit_budget(
    monkeypatch,
) -> None:
    """Authenticated requests should still consume budget even when route logic later returns 404."""
    install_rate_limited_alert_routes(
        monkeypatch,
        install_services=False,
    )

    first_response = request(
        "GET",
        "/sessions/missing-session/alerts",
        headers=build_api_key_headers(),
    )
    second_response = request(
        "GET",
        "/sessions/missing-session/alerts",
        headers=build_api_key_headers(),
    )

    assert first_response.status_code == 404
    assert first_response.json() == build_session_not_found_payload("missing-session")
    assert second_response.status_code == 429
    assert second_response.json() == build_rate_limit_exceeded_payload(
        "Too many requests for the configured window."
    )


def test_authenticated_validation_failures_count_against_rate_limit_budget(
    monkeypatch,
) -> None:
    """Authenticated requests should still spend budget when route logic later returns 400."""
    install_rate_limited_alert_routes(
        monkeypatch,
        install_services=False,
    )

    def fake_summarize_session_alert_events(
        session_id: str,
        **_: object,
    ) -> dict[str, object]:
        raise ValueError("start_time_utc must be earlier than or equal to end_time_utc")

    monkeypatch.setattr(
        "api.routers.alerts.summarize_session_alert_events",
        fake_summarize_session_alert_events,
    )

    first_response = request(
        "GET",
        "/sessions/session-123/alerts/summary",
        headers=build_api_key_headers(),
    )
    second_response = request(
        "GET",
        "/sessions/session-123/alerts/summary",
        headers=build_api_key_headers(),
    )

    assert first_response.status_code == 400
    assert first_response.json() == build_validation_error_payload(
        "start_time_utc must be earlier than or equal to end_time_utc"
    )
    assert "Retry-After" not in first_response.headers
    assert second_response.status_code == 429
    assert second_response.json() == build_rate_limit_exceeded_payload(
        "Too many requests for the configured window."
    )
