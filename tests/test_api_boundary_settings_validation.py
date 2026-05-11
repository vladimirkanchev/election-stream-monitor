"""Focused validation-seam tests for FastAPI boundary settings.

This file owns direct validator behavior and the startup-facing validation seam.
Environment parsing and mode-driven defaulting live in the neighboring env
test file so reviewers can read policy loading and policy enforcement
separately.
"""

from __future__ import annotations

import anyio
import pytest

from api.app import app
from config import (
    ApiAuthSettings,
    ApiBoundaryConfigurationError,
    ApiRateLimitSettings,
    ApiRateLimitStrategy,
    validate_api_auth_settings,
    validate_api_rate_limit_settings,
    validate_fastapi_boundary_settings,
)
from tests.api_boundary_env_test_support import (
    reset_boundary_test_state,
    restore_boundary_test_state,
    snapshot_boundary_env,
)


@pytest.fixture(autouse=True)
def _clear_boundary_settings_caches() -> None:
    """Keep cached FastAPI boundary settings isolated between validation tests."""

    original_values = snapshot_boundary_env()
    reset_boundary_test_state()
    yield
    restore_boundary_test_state(original_values)


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


def test_fastapi_boundary_validation_fails_through_real_settings_seam(monkeypatch) -> None:
    """The shared boundary validator should fail through the real settings seam.

    This stays closer to a deployment-shape failure than monkeypatching the
    validator itself because the bad state enters through the same cached
    settings getters that the FastAPI lifespan and CLI startup paths use.
    """

    monkeypatch.setenv("ESM_API_AUTH_ENABLED", "true")
    monkeypatch.delenv("ESM_API_AUTH_ALLOWED_KEYS", raising=False)

    with pytest.raises(
        ApiBoundaryConfigurationError,
        match="FastAPI auth is enabled but no allowed API keys are configured",
    ):
        validate_fastapi_boundary_settings()
