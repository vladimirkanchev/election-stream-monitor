"""Shared helpers for FastAPI alert-route tests.

This module owns only small response-payload builders for the alert-route
slice. Keeping the common error shapes here makes the route tests read like
boundary scenarios instead of long literal-comparison fixtures.

It intentionally covers both the raw alert routes and the grouped incident
routes because they share the same FastAPI error envelope plus the same
router-level auth and rate-limit seams.
"""

from collections.abc import Mapping

from config import ApiAuthSettings, ApiRateLimitSettings
from api_auth import AuthPrincipal, AuthenticationError
from api_rate_limit import reset_api_rate_limit_state
from tests.session_alert_test_support import (
    build_alert_summary_payload,
    build_incident_summary_payload,
)


def build_session_not_found_payload(session_id: str) -> dict[str, str]:
    """Return the stable API payload for one alert-route not-found response."""
    return {
        "detail": "Session not found",
        "error_code": "session_not_found",
        "status_reason": "session_not_found",
        "status_detail": f"No persisted session snapshot found for session_id={session_id}",
    }


def build_validation_error_payload(detail: str) -> dict[str, str]:
    """Return the stable API payload for one alert-route validation failure."""
    return {
        "detail": detail,
        "error_code": "validation_failed",
        "status_reason": "validation_failed",
        "status_detail": detail,
    }


def build_authentication_failed_payload(detail: str) -> dict[str, str]:
    """Return the stable API payload for one alert-route auth failure."""
    return {
        "detail": "Authentication failed",
        "error_code": "authentication_failed",
        "status_reason": "authentication_failed",
        "status_detail": detail,
    }


def build_rate_limit_exceeded_payload(detail: str) -> dict[str, str]:
    """Return the stable API payload for one alert-route rate-limit failure."""
    return {
        "detail": "Rate limit exceeded",
        "error_code": "rate_limit_exceeded",
        "status_reason": "rate_limit_exceeded",
        "status_detail": detail,
    }


def assert_request_validation_payload(
    payload: Mapping[str, object],
    *,
    field_name: str,
) -> None:
    """Assert the repo's stable FastAPI validation-envelope shape."""
    assert payload["detail"] == "Request validation failed"
    assert payload["error_code"] == "validation_failed"
    assert payload["status_reason"] == "validation_failed"
    status_detail = payload.get("status_detail")
    assert isinstance(status_detail, str)
    assert field_name in status_detail


def build_api_key_headers(api_key: str = "valid-key") -> dict[str, str]:
    """Build the one documented API-key header for protected alert-route requests.

    Keeping this in shared test support removes low-value literal dictionaries
    from the split route-policy files while still leaving request scenarios
    straightforward to scan.
    """
    return {"X-API-Key": api_key}


def build_test_auth_principal(
    *,
    auth_type: str = "api_key",
    subject: str = "api-key:test",
    key_id: str | None = "test",
) -> AuthPrincipal:
    """Return one small authenticated principal for route-boundary tests.

    Route tests do not care about real key fingerprints, only that the auth
    seam returned an authenticated caller object.
    """
    return AuthPrincipal(
        auth_type=auth_type,
        subject=subject,
        key_id=key_id,
    )


def install_alert_route_auth_success(
    monkeypatch,
    *,
    expected_key: str | None = None,
) -> None:
    """Patch the alert router auth seam to accept one request in tests."""

    def fake_authenticate_api_request(*, x_api_key: str | None, settings=None) -> AuthPrincipal:
        if expected_key is not None:
            assert x_api_key == expected_key
        return build_test_auth_principal()

    monkeypatch.setattr(
        "api.alert_route_policy.authenticate_api_request",
        fake_authenticate_api_request,
    )


def install_alert_route_auth_failure(monkeypatch, *, detail: str) -> None:
    """Patch the alert router auth seam to reject one request in tests."""

    def fake_authenticate_api_request(*, x_api_key: str | None, settings=None) -> AuthPrincipal:
        raise AuthenticationError(detail)

    monkeypatch.setattr(
        "api.alert_route_policy.authenticate_api_request",
        fake_authenticate_api_request,
    )


def install_api_auth_settings(
    monkeypatch,
    *,
    enabled: bool,
    mode: str = "api_key",
    allowed_api_keys: tuple[str, ...] = (),
) -> None:
    """Patch the shared auth-settings seam used by the real alert router auth path.

    This helper is for tests that exercise the actual `api_auth.py` logic
    rather than monkeypatching the router-level auth call directly.
    """
    monkeypatch.setattr(
        "api_auth.get_api_auth_settings",
        lambda: ApiAuthSettings(
            enabled=enabled,
            mode=mode,
            allowed_api_keys=allowed_api_keys,
        ),
    )


def install_api_rate_limit_settings(
    monkeypatch,
    *,
    enabled: bool,
    strategy: str = "principal",
    window_seconds: int = 60,
    max_requests: int = 100,
) -> None:
    """Patch the shared rate-limit settings seam used by the alert router.

    The current HTTP boundary resolves limiter settings through
    `api_rate_limit.py`, then reuses the resolved context for logging and
    `Retry-After`. Keeping the patch at the shared limiter seam lets the route
    tests describe one consistent configuration without reaching into router
    internals.
    """

    settings = ApiRateLimitSettings(
        enabled=enabled,
        strategy=strategy,
        window_seconds=window_seconds,
        max_requests=max_requests,
    )

    monkeypatch.setattr(
        "api_rate_limit.get_api_rate_limit_settings",
        lambda: settings,
    )


def install_real_alert_route_auth(
    monkeypatch,
    *,
    enabled: bool,
    allowed_api_keys: tuple[str, ...] = ("valid-key",),
    install_services: bool = False,
) -> None:
    """Install the real auth settings seam for alerts-router boundary tests.

    This is the small shared counterpart to the direct auth-success and
    auth-failure monkeypatch helpers above. Use it when the test should
    exercise the real `api_auth.py` behavior through configured settings.
    """

    install_api_auth_settings(
        monkeypatch,
        enabled=enabled,
        allowed_api_keys=allowed_api_keys,
    )
    if install_services:
        install_empty_alert_route_services(monkeypatch)


def reset_alert_route_rate_limit_state() -> None:
    """Reset the shared in-memory alert-route limiter state for tests."""

    reset_api_rate_limit_state()


def install_rate_limited_alert_routes(
    monkeypatch,
    *,
    auth_enabled: bool = True,
    allowed_api_keys: tuple[str, ...] = ("valid-key",),
    strategy: str = "principal",
    max_requests: int = 1,
    window_seconds: int = 60,
    rate_limit_enabled: bool = True,
    install_services: bool = True,
) -> None:
    """Install one real alerts-router auth and limiter configuration for tests.

    The split policy and contract files repeatedly need the same setup:

    - reset the shared in-memory limiter
    - configure the real auth settings seam
    - configure the real limiter settings seam
    - optionally install simple successful route adapters

    Centralizing that setup keeps those files focused on policy assertions
    instead of repeating the same multi-step arrangement logic.
    """

    reset_alert_route_rate_limit_state()
    install_api_auth_settings(
        monkeypatch,
        enabled=auth_enabled,
        allowed_api_keys=allowed_api_keys,
    )
    install_api_rate_limit_settings(
        monkeypatch,
        enabled=rate_limit_enabled,
        strategy=strategy,
        max_requests=max_requests,
        window_seconds=window_seconds,
    )
    if install_services:
        install_empty_alert_route_services(monkeypatch)


def install_empty_alert_route_services(
    monkeypatch,
) -> None:
    """Patch the alerts router with successful empty responses for all read models.

    Route-policy tests often need the protected alerts router to succeed so
    they can focus on auth or rate-limit behavior instead of route-specific
    payload construction. Keeping that setup here removes repetitive one-off
    lambdas from the policy file.
    """

    monkeypatch.setattr(
        "api.routers.alerts.filter_session_alert_events",
        lambda current_session_id, **_: [],
    )
    monkeypatch.setattr(
        "api.routers.alerts.summarize_session_alert_events",
        lambda current_session_id, **_: build_alert_summary_payload(
            current_session_id,
            total_alerts=0,
            counts_by_detector={},
            counts_by_severity={},
            first_alert_timestamp_utc=None,
            last_alert_timestamp_utc=None,
        ),
    )
    monkeypatch.setattr(
        "api.routers.alerts.build_session_timeline",
        lambda current_session_id, **_: {
            "session_id": current_session_id,
            "entries": [],
        },
    )
    monkeypatch.setattr(
        "api.routers.alerts.build_session_incident_summary",
        lambda current_session_id, **_: build_incident_summary_payload(
            current_session_id,
            total_alerts=0,
            total_incidents=0,
            counts_by_detector={},
            counts_by_severity={},
            top_incident_categories={},
            first_alert_timestamp_utc=None,
            last_alert_timestamp_utc=None,
            narrative_summary=f"Session {current_session_id} had no alerts.",
        ),
    )
