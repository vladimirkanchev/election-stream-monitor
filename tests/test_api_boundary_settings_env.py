"""Focused env-ingestion tests for FastAPI run-mode and boundary settings.

This file owns environment parsing and mode-driven defaults. It intentionally
stays below the startup-validation seam so reviewers can read:

- how boundary policy is loaded
- how `local` and `share` affect defaults
- how invalid env values are handled

Direct validator behavior and startup-seam validation live in the neighboring
boundary settings validation file.
"""

from __future__ import annotations

import pytest

from config import (
    ApiBoundaryConfigurationError,
    get_api_auth_settings,
    get_api_rate_limit_settings,
    get_fastapi_run_mode_settings,
)
from tests.api_boundary_env_test_support import (
    reset_boundary_test_state,
    restore_boundary_test_state,
    snapshot_boundary_env,
)


@pytest.fixture(autouse=True)
def _clear_boundary_settings_caches() -> None:
    """Keep cached FastAPI boundary settings isolated between env tests."""

    original_values = snapshot_boundary_env()
    reset_boundary_test_state()
    yield
    restore_boundary_test_state(original_values)


def test_get_fastapi_run_mode_settings_defaults_to_local(monkeypatch) -> None:
    """The top-level FastAPI run mode should default to the trusted local preset."""

    monkeypatch.delenv("ESM_FASTAPI_RUN_MODE", raising=False)

    settings = get_fastapi_run_mode_settings()

    assert settings.mode == "local"


def test_get_fastapi_run_mode_settings_rejects_invalid_env_value(monkeypatch) -> None:
    """Unsupported run-mode overrides should fail while loading boundary settings."""

    monkeypatch.setenv("ESM_FASTAPI_RUN_MODE", "invalid")

    with pytest.raises(
        ApiBoundaryConfigurationError,
        match="ESM_FASTAPI_RUN_MODE must be one of: local, share",
    ):
        get_fastapi_run_mode_settings()


@pytest.mark.parametrize(
    ("mode", "expected_enabled"),
    [("local", False), ("share", True)],
)
def test_get_api_auth_settings_defaults_follow_run_mode(
    monkeypatch,
    mode: str,
    expected_enabled: bool,
) -> None:
    """Auth defaults should come from the selected high-level FastAPI run mode."""

    monkeypatch.setenv("ESM_FASTAPI_RUN_MODE", mode)
    monkeypatch.delenv("ESM_API_AUTH_ENABLED", raising=False)

    settings = get_api_auth_settings()

    assert settings.enabled is expected_enabled


def test_get_api_auth_settings_generates_share_mode_api_key_when_missing(
    monkeypatch,
) -> None:
    """Share mode should auto-provision one API key when no manual key is supplied."""

    monkeypatch.setenv("ESM_FASTAPI_RUN_MODE", "share")
    monkeypatch.delenv("ESM_API_AUTH_ENABLED", raising=False)
    monkeypatch.delenv("ESM_API_AUTH_ALLOWED_KEYS", raising=False)

    settings = get_api_auth_settings()

    assert settings.enabled is True
    assert len(settings.allowed_api_keys) == 1
    assert settings.generated_api_key == settings.allowed_api_keys[0]
    assert settings.generated_api_key is not None
    assert settings.generated_api_key.startswith("esm_share_")


def test_get_api_auth_settings_keeps_manual_key_in_share_mode(monkeypatch) -> None:
    """Share mode should prefer an explicitly configured key over auto-generation."""

    monkeypatch.setenv("ESM_FASTAPI_RUN_MODE", "share")
    monkeypatch.delenv("ESM_API_AUTH_ENABLED", raising=False)
    monkeypatch.setenv("ESM_API_AUTH_ALLOWED_KEYS", "manual-demo-key")

    settings = get_api_auth_settings()

    assert settings.enabled is True
    assert settings.allowed_api_keys == ("manual-demo-key",)
    assert settings.generated_api_key is None


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


@pytest.mark.parametrize(
    ("mode", "expected_enabled"),
    [("local", False), ("share", True)],
)
def test_get_api_rate_limit_settings_defaults_follow_run_mode(
    monkeypatch,
    mode: str,
    expected_enabled: bool,
) -> None:
    """Limiter defaults should come from the selected high-level FastAPI run mode."""

    monkeypatch.setenv("ESM_FASTAPI_RUN_MODE", mode)
    monkeypatch.delenv("ESM_API_RATE_LIMIT_ENABLED", raising=False)

    settings = get_api_rate_limit_settings()

    assert settings.enabled is expected_enabled


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
