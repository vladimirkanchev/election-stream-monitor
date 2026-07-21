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

import os
from collections.abc import Generator

import pytest

from config import (
    ApiBoundaryConfigurationError,
    clear_fastapi_boundary_settings_caches,
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
def _clear_boundary_settings_caches() -> Generator[None, None, None]:
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


def test_get_api_auth_settings_generates_share_mode_api_key_when_unconfigured(
    monkeypatch,
) -> None:
    """Share mode should generate one API key only when none is configured."""

    monkeypatch.setenv("ESM_FASTAPI_RUN_MODE", "share")
    monkeypatch.delenv("ESM_API_AUTH_ENABLED", raising=False)
    monkeypatch.delenv("ESM_API_AUTH_ALLOWED_KEYS", raising=False)

    settings = get_api_auth_settings()

    assert settings.enabled is True
    assert len(settings.allowed_api_keys) == 1
    assert settings.generated_api_key == settings.allowed_api_keys[0]
    assert settings.generated_api_key is not None
    assert settings.generated_api_key.startswith("esm_share_")


def test_get_api_auth_settings_generates_one_in_memory_key_per_settings_lifetime(
    monkeypatch,
) -> None:
    """Generated keys should use the fixed entropy budget without environment storage."""

    token_sizes: list[int] = []
    tokens = iter(("first-token", "second-token"))

    def fake_token_urlsafe(size: int) -> str:
        token_sizes.append(size)
        return next(tokens)

    monkeypatch.setenv("ESM_FASTAPI_RUN_MODE", "share")
    monkeypatch.delenv("ESM_API_AUTH_ALLOWED_KEYS", raising=False)
    monkeypatch.setattr(
        "api_boundary_config.secrets.token_urlsafe",
        fake_token_urlsafe,
    )

    first_settings = get_api_auth_settings()
    assert get_api_auth_settings() is first_settings
    assert first_settings.generated_api_key == "esm_share_first-token"
    assert "ESM_API_AUTH_ALLOWED_KEYS" not in os.environ

    clear_fastapi_boundary_settings_caches()
    second_settings = get_api_auth_settings()

    assert second_settings.generated_api_key == "esm_share_second-token"
    assert token_sizes == [24, 24]


def test_get_api_auth_settings_keeps_manual_key_in_share_mode(monkeypatch) -> None:
    """Share mode should prefer an explicitly configured key over auto-generation."""

    monkeypatch.setenv("ESM_FASTAPI_RUN_MODE", "share")
    monkeypatch.delenv("ESM_API_AUTH_ENABLED", raising=False)
    monkeypatch.setenv("ESM_API_AUTH_ALLOWED_KEYS", "manual-demo-key")

    settings = get_api_auth_settings()

    assert settings.enabled is True
    assert settings.allowed_api_keys == ("manual-demo-key",)
    assert settings.generated_api_key is None


@pytest.mark.parametrize(
    "configured_keys",
    ("", "   ", "alpha,", ",beta", "alpha,  ,beta"),
)
def test_get_api_auth_settings_rejects_blank_configured_key_entries(
    monkeypatch,
    configured_keys: str,
) -> None:
    """Present but blank key entries must not silently trigger generation."""

    monkeypatch.setenv("ESM_FASTAPI_RUN_MODE", "share")
    monkeypatch.setenv("ESM_API_AUTH_ALLOWED_KEYS", configured_keys)

    with pytest.raises(
        ApiBoundaryConfigurationError,
        match="ESM_API_AUTH_ALLOWED_KEYS must contain one or more non-blank",
    ):
        get_api_auth_settings()


def test_get_api_auth_settings_does_not_echo_invalid_configured_key(monkeypatch) -> None:
    """Configuration failures should identify the setting without exposing its value."""

    configured_keys = "sensitive-key,"
    monkeypatch.setenv("ESM_FASTAPI_RUN_MODE", "share")
    monkeypatch.setenv("ESM_API_AUTH_ALLOWED_KEYS", configured_keys)

    with pytest.raises(ApiBoundaryConfigurationError) as raised:
        get_api_auth_settings()

    assert "ESM_API_AUTH_ALLOWED_KEYS" in str(raised.value)
    assert configured_keys not in str(raised.value)


@pytest.mark.parametrize("auth_override", ("false", "0", "off"))
def test_get_api_auth_settings_rejects_share_mode_auth_disabling_overrides(
    monkeypatch,
    auth_override: str,
) -> None:
    """Reject false-like auth overrides before a share server can start."""

    monkeypatch.setenv("ESM_FASTAPI_RUN_MODE", "share")
    monkeypatch.setenv("ESM_API_AUTH_ENABLED", auth_override)
    monkeypatch.setenv("ESM_API_AUTH_ALLOWED_KEYS", "manual-demo-key")

    with pytest.raises(
        ApiBoundaryConfigurationError,
        match="Share mode requires FastAPI authentication",
    ):
        get_api_auth_settings()


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
