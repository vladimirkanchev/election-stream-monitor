"""Focused tests for FastAPI auth and rate-limit startup configuration rules.

These tests stay below the route layer and protect the settings-validation
seam that now runs during FastAPI startup. They prove bad boundary
configuration fails early instead of waiting for the first protected request.
"""

from __future__ import annotations

import anyio
import pytest

from api.app import app
from tests.api_alert_test_support import (
    build_authentication_failed_payload,
    build_session_not_found_payload,
)
from tests.api_boundary_test_support import request
from config import (
    ApiAuthSettings,
    ApiBoundaryConfigurationError,
    ApiRateLimitSettings,
    ApiRateLimitStrategy,
    get_api_auth_settings,
    get_api_rate_limit_settings,
    validate_fastapi_boundary_settings,
    validate_api_auth_settings,
    validate_api_rate_limit_settings,
)


@pytest.fixture(autouse=True)
def _clear_boundary_settings_caches() -> None:
    """Keep cached FastAPI boundary settings isolated between config tests."""

    get_api_auth_settings.cache_clear()
    get_api_rate_limit_settings.cache_clear()
    yield
    get_api_auth_settings.cache_clear()
    get_api_rate_limit_settings.cache_clear()


# Direct validation helpers


def test_validate_api_auth_settings_rejects_enabled_auth_without_allowed_keys() -> None:
    """Enabled API-key auth should fail early when no keys are configured."""
    with pytest.raises(
        ApiBoundaryConfigurationError,
        match="FastAPI auth is enabled but no allowed API keys are configured",
    ):
        validate_api_auth_settings(
            ApiAuthSettings(
                enabled=True,
                mode="api_key",
                allowed_api_keys=(),
            )
        )


def test_validate_api_auth_settings_rejects_unimplemented_auth_mode() -> None:
    """Startup validation should reject auth modes the current runtime cannot serve."""
    with pytest.raises(
        ApiBoundaryConfigurationError,
        match="FastAPI auth mode must be 'api_key' for the current implementation",
    ):
        validate_api_auth_settings(
            ApiAuthSettings(
                enabled=True,
                mode="jwt",
                allowed_api_keys=("alpha-secret",),
            )
        )


def test_validate_api_rate_limit_settings_rejects_unsupported_strategy() -> None:
    """Unsupported limiter strategies should fail before the app accepts requests."""
    with pytest.raises(
        ApiBoundaryConfigurationError,
        match="FastAPI rate-limit strategy must be one of: ip, principal",
    ):
        validate_api_rate_limit_settings(
            ApiRateLimitSettings(
                enabled=True,
                strategy="unsupported",  # type: ignore[arg-type]
                window_seconds=60,
                max_requests=1,
            )
        )


def test_validate_api_rate_limit_settings_rejects_non_positive_window() -> None:
    """The fixed-window limiter must reject non-positive window sizes."""
    with pytest.raises(
        ApiBoundaryConfigurationError,
        match="FastAPI rate-limit window_seconds must be a positive integer",
    ):
        validate_api_rate_limit_settings(
            ApiRateLimitSettings(
                enabled=True,
                strategy="principal",
                window_seconds=0,
                max_requests=1,
            )
        )


def test_validate_api_rate_limit_settings_rejects_non_positive_max_requests() -> None:
    """The fixed-window limiter must reject non-positive request budgets."""
    with pytest.raises(
        ApiBoundaryConfigurationError,
        match="FastAPI rate-limit max_requests must be a positive integer",
    ):
        validate_api_rate_limit_settings(
            ApiRateLimitSettings(
                enabled=True,
                strategy="principal",
                window_seconds=60,
                max_requests=0,
            )
        )


# Startup integration


def test_fastapi_app_startup_runs_boundary_settings_validation(monkeypatch) -> None:
    """The FastAPI app lifespan should execute the shared boundary validation seam."""
    seen: list[tuple[bool, ApiRateLimitStrategy]] = []

    def fake_validate_fastapi_boundary_settings() -> None:
        seen.append((True, "principal"))

    monkeypatch.setattr(
        "api.app.validate_fastapi_boundary_settings",
        fake_validate_fastapi_boundary_settings,
    )

    async def run() -> None:
        async with app.router.lifespan_context(app):
            assert seen == [(True, "principal")]

    anyio.run(run)


# Environment parsing and settings-ingestion behavior


def test_get_api_auth_settings_rejects_invalid_env_auth_mode(monkeypatch) -> None:
    """Invalid auth-mode environment overrides should fail during settings load."""

    monkeypatch.setenv("ESM_API_AUTH_MODE", "invalid")

    with pytest.raises(
        ApiBoundaryConfigurationError,
        match="ESM_API_AUTH_MODE must be one of: api_key, jwt",
    ):
        get_api_auth_settings()


def test_get_api_auth_settings_falls_back_to_default_on_invalid_bool_env(monkeypatch) -> None:
    """Invalid boolean auth-enabled overrides should keep the current default behavior."""

    monkeypatch.setenv("ESM_API_AUTH_ENABLED", "not-a-bool")

    settings = get_api_auth_settings()

    assert settings.enabled is False


def test_get_api_rate_limit_settings_rejects_invalid_env_strategy(monkeypatch) -> None:
    """Invalid limiter-strategy environment overrides should fail during settings load."""

    monkeypatch.setenv("ESM_API_RATE_LIMIT_STRATEGY", "invalid")

    with pytest.raises(
        ApiBoundaryConfigurationError,
        match="ESM_API_RATE_LIMIT_STRATEGY must be one of: ip, principal",
    ):
        get_api_rate_limit_settings()


def test_get_api_rate_limit_settings_falls_back_to_default_on_invalid_bool_env(
    monkeypatch,
) -> None:
    """Invalid boolean limiter-enabled overrides should keep the current default behavior."""

    monkeypatch.setenv("ESM_API_RATE_LIMIT_ENABLED", "not-a-bool")

    settings = get_api_rate_limit_settings()

    assert settings.enabled is False


def test_get_api_rate_limit_settings_rejects_invalid_env_window(monkeypatch) -> None:
    """Invalid limiter-window environment overrides should fail during settings load."""

    monkeypatch.setenv("ESM_API_RATE_LIMIT_WINDOW_SEC", "zero")

    with pytest.raises(
        ApiBoundaryConfigurationError,
        match="ESM_API_RATE_LIMIT_WINDOW_SEC must be a positive integer",
    ):
        get_api_rate_limit_settings()


def test_get_api_rate_limit_settings_rejects_invalid_env_max_requests(monkeypatch) -> None:
    """Invalid limiter-budget environment overrides should fail during settings load."""

    monkeypatch.setenv("ESM_API_RATE_LIMIT_MAX_REQUESTS", "0")

    with pytest.raises(
        ApiBoundaryConfigurationError,
        match="ESM_API_RATE_LIMIT_MAX_REQUESTS must be a positive integer",
    ):
        get_api_rate_limit_settings()


# Real boundary-validation seam through configured settings


def test_fastapi_boundary_validation_fails_through_real_settings_seam(monkeypatch) -> None:
    """The shared boundary validator should fail through the real settings seam.

    This stays closer to a deployment-shape failure than monkeypatching the
    validator itself because the bad state enters through the same settings
    getters the app lifespan uses.
    """

    monkeypatch.setenv("ESM_API_AUTH_ENABLED", "true")
    monkeypatch.delenv("ESM_API_AUTH_ALLOWED_KEYS", raising=False)

    with pytest.raises(
        ApiBoundaryConfigurationError,
        match="FastAPI auth is enabled but no allowed API keys are configured",
    ):
        validate_fastapi_boundary_settings()


# Regression checks for additive response-header support


def test_authentication_failed_error_keeps_legacy_payload_and_no_headers(
    monkeypatch,
) -> None:
    """Non-rate-limit domain errors should keep their old body shape and no headers.

    This regression test protects the additive `ApiDomainError.headers` change
    so older boundary failures like auth errors do not accidentally start
    returning unrelated transport headers.
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

    This is the symmetric regression case for a route-level `404`. It makes
    sure the additive `ApiDomainError.headers` seam stays opt-in instead of
    quietly changing the broader API error contract.
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
