"""Focused regression tests for non-rate-limit FastAPI boundary error shaping.

These cases live separately from the boundary settings tests because they own
the HTTP error-contract side of the boundary rather than the startup
validation side.
"""

from __future__ import annotations

from config import ApiAuthSettings
from tests.api_alert_test_support import (
    build_authentication_failed_payload,
    build_session_not_found_payload,
)
from tests.api_boundary_test_support import request


def test_authentication_failed_error_keeps_legacy_payload_and_no_headers(
    monkeypatch,
) -> None:
    """Non-rate-limit domain errors should keep their old body shape and no headers.

    This guards the additive `ApiDomainError.headers` seam so auth failures do
    not accidentally inherit rate-limit transport headers.
    """

    monkeypatch.setattr(
        "api_auth.get_api_auth_settings",
        lambda: ApiAuthSettings(
            enabled=True,
            mode="api_key",
            allowed_api_keys=("valid-key",),
        ),
    )

    response = request("GET", "/sessions/session-123/alerts")

    assert response.status_code == 401
    assert response.json() == build_authentication_failed_payload("Missing API key")
    assert "Retry-After" not in response.headers


def test_session_not_found_error_keeps_legacy_payload_and_no_headers(
    monkeypatch,
) -> None:
    """Ordinary non-429 domain errors should not inherit rate-limit headers.

    This is the symmetric route-level regression for ordinary `404` responses.
    """

    monkeypatch.setattr(
        "api_auth.get_api_auth_settings",
        lambda: ApiAuthSettings(
            enabled=False,
            mode="api_key",
            allowed_api_keys=(),
        ),
    )

    response = request("GET", "/sessions/missing-session/alerts")

    assert response.status_code == 404
    assert response.json() == build_session_not_found_payload("missing-session")
    assert "Retry-After" not in response.headers
