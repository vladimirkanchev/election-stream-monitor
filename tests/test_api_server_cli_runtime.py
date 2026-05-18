"""Focused tests for CLI runtime selection and mode-driven boundary state.

This file owns `prepare_cli_runtime(...)` behavior:

- mode defaults
- manual versus generated key resolution
- override precedence
- fail-fast validation
- recovery after bad startup attempts
- CLI-specific boundary posture decisions before any HTTP request exists

Route-level behavior and startup output live in neighboring files.
"""

from __future__ import annotations

import re
from collections.abc import Generator
from typing import Literal

import pytest

from api_server_cli import prepare_cli_runtime
from config import ApiBoundaryConfigurationError
from tests.api_boundary_env_test_support import (
    reset_boundary_test_state,
    restore_boundary_test_state,
    snapshot_boundary_env,
)


@pytest.fixture(autouse=True)
def _clear_boundary_settings_caches() -> Generator[None, None, None]:
    """Keep env-driven FastAPI boundary settings isolated across CLI runtime tests."""

    original_values = snapshot_boundary_env()
    reset_boundary_test_state()
    yield
    restore_boundary_test_state(original_values)


@pytest.mark.parametrize(
    (
        "mode",
        "manual_api_key",
        "auth_enabled",
        "rate_limit_enabled",
        "expected_keys",
        "generated",
    ),
    [
        ("local", None, False, False, (), False),
        ("share", None, True, True, None, True),
        ("share", "demo-manual-key", True, True, ("demo-manual-key",), False),
        ("share", "   ", True, True, None, True),
    ],
)
def test_prepare_cli_runtime_resolves_mode_defaults_and_share_key_source(
    mode: Literal["local", "share"],
    manual_api_key: str | None,
    auth_enabled: bool,
    rate_limit_enabled: bool,
    expected_keys: tuple[str, ...] | None,
    generated: bool,
) -> None:
    """CLI runtime preparation should resolve one predictable boundary posture.

    The small parameter matrix keeps the same assertions for:

    - open local startup
    - generated-key share startup
    - manual-key share startup
    - blank-manual-key fallback to generated-key startup
    This file intentionally stops at the prepared runtime object. Questions
    about which real routes stay open or protected belong in the neighboring
    CLI route tests.
    """

    runtime = prepare_cli_runtime(mode=mode, manual_api_key=manual_api_key)

    assert runtime.mode == mode
    assert runtime.auth_settings.enabled is auth_enabled
    assert runtime.rate_limit_settings.enabled is rate_limit_enabled
    if generated:
        assert runtime.auth_settings.generated_api_key is not None
        assert runtime.auth_settings.allowed_api_keys == (
            runtime.auth_settings.generated_api_key,
        )
        assert runtime.auth_settings.generated_api_key.startswith("esm_share_")
        return
    assert runtime.auth_settings.generated_api_key is None
    assert runtime.auth_settings.allowed_api_keys == expected_keys


def test_prepare_cli_runtime_share_mode_honors_explicit_rate_limit_override(
    monkeypatch,
) -> None:
    """Explicit env overrides should still beat the higher-level share-mode defaults."""

    monkeypatch.setenv("ESM_API_RATE_LIMIT_ENABLED", "false")

    runtime = prepare_cli_runtime(
        mode="share",
        manual_api_key=None,
    )

    assert runtime.auth_settings.enabled is True
    assert runtime.rate_limit_settings.enabled is False


def test_prepare_cli_runtime_share_mode_does_not_change_route_protection_scope() -> None:
    """Share-mode runtime prep should only set boundary posture, not widen protected scope."""

    runtime = prepare_cli_runtime(
        mode="share",
        manual_api_key=None,
    )

    assert runtime.mode == "share"
    assert runtime.auth_settings.enabled is True
    assert runtime.rate_limit_settings.enabled is True
    assert runtime.auth_settings.generated_api_key is not None


def test_prepare_cli_runtime_local_mode_enabled_auth_without_key_fails_early(
    monkeypatch,
) -> None:
    """Local mode should still fail fast when explicit auth enablement has no usable key."""

    monkeypatch.setenv("ESM_API_AUTH_ENABLED", "true")

    with pytest.raises(
        ApiBoundaryConfigurationError,
        match="FastAPI auth is enabled but no allowed API keys are configured",
    ):
        prepare_cli_runtime(
            mode="local",
            manual_api_key=None,
        )


def test_prepare_cli_runtime_share_mode_rejects_impossible_auth_override(
    monkeypatch,
) -> None:
    """Share mode should still fail fast when auth mode is forced to an unimplemented value."""

    monkeypatch.setenv("ESM_API_AUTH_MODE", "jwt")

    with pytest.raises(
        ApiBoundaryConfigurationError,
        match="FastAPI auth mode must be 'api_key' for the current implementation",
    ):
        prepare_cli_runtime(
            mode="share",
            manual_api_key=None,
        )


def test_prepare_cli_runtime_generated_share_key_changes_between_startups(
    monkeypatch,
) -> None:
    """Auto-generated share-mode keys should be process-startup local, not sticky."""

    first_runtime = prepare_cli_runtime(
        mode="share",
        manual_api_key=None,
    )
    second_runtime = prepare_cli_runtime(
        mode="share",
        manual_api_key=None,
    )

    assert first_runtime.auth_settings.generated_api_key is not None
    assert second_runtime.auth_settings.generated_api_key is not None
    assert (
        first_runtime.auth_settings.generated_api_key
        != second_runtime.auth_settings.generated_api_key
    )


def test_prepare_cli_runtime_valid_share_startup_recovers_after_failed_attempt(
    monkeypatch,
) -> None:
    """A valid share-mode startup should recover cleanly after one failed config attempt.

    This protects the env-driven cached settings seam against one realistic
    operator flow: start with a bad override, correct it, then start again in
    the same process.
    """

    monkeypatch.setenv("ESM_API_AUTH_MODE", "jwt")

    with pytest.raises(
        ApiBoundaryConfigurationError,
        match="FastAPI auth mode must be 'api_key' for the current implementation",
    ):
        prepare_cli_runtime(
            mode="share",
            manual_api_key=None,
        )

    monkeypatch.setenv("ESM_API_AUTH_MODE", "api_key")

    runtime = prepare_cli_runtime(
        mode="share",
        manual_api_key=None,
    )

    assert runtime.auth_settings.enabled is True
    assert runtime.auth_settings.generated_api_key is not None


def test_prepare_cli_runtime_switching_from_share_to_local_clears_generated_key(
    monkeypatch,
) -> None:
    """Repeated CLI mode selection should not leak protected share state into local mode."""

    share_runtime = prepare_cli_runtime(
        mode="share",
        manual_api_key=None,
    )
    local_runtime = prepare_cli_runtime(
        mode="local",
        manual_api_key=None,
    )

    assert share_runtime.auth_settings.generated_api_key is not None
    assert local_runtime.mode == "local"
    assert local_runtime.auth_settings.enabled is False
    assert local_runtime.auth_settings.allowed_api_keys == ()
    assert local_runtime.auth_settings.generated_api_key is None
    assert local_runtime.rate_limit_settings.enabled is False


def test_prepare_cli_runtime_share_mode_with_auth_and_limiter_disabled_is_fully_open(
    monkeypatch,
) -> None:
    """Share mode should stay fully open when both protection layers are explicitly disabled."""

    monkeypatch.setenv("ESM_API_AUTH_ENABLED", "false")
    monkeypatch.setenv("ESM_API_RATE_LIMIT_ENABLED", "false")

    runtime = prepare_cli_runtime(
        mode="share",
        manual_api_key="manual-demo-key",
    )

    assert runtime.auth_settings.enabled is False
    assert runtime.rate_limit_settings.enabled is False


def test_prepare_cli_runtime_rejects_manual_share_key_with_comma(monkeypatch) -> None:
    """Manual share-mode CLI input should reject comma-separated multi-key values."""

    with pytest.raises(
        ApiBoundaryConfigurationError,
        match="Manual share-mode API key must be one key value and may not contain commas",
    ):
        prepare_cli_runtime(
            mode="share",
            manual_api_key="alpha,beta",
        )


def test_prepare_cli_runtime_share_mode_honors_explicit_auth_override(monkeypatch) -> None:
    """Explicit auth overrides should still be able to suppress share-mode protection."""

    monkeypatch.setenv("ESM_API_AUTH_ENABLED", "false")

    runtime = prepare_cli_runtime(
        mode="share",
        manual_api_key=None,
    )

    assert runtime.auth_settings.enabled is False
    assert runtime.auth_settings.allowed_api_keys == ()
    assert runtime.auth_settings.generated_api_key is None


def test_prepare_cli_runtime_generated_share_key_is_copy_paste_safe(monkeypatch) -> None:
    """Generated share-mode keys should stay inside a token-safe printable character set."""

    runtime = prepare_cli_runtime(
        mode="share",
        manual_api_key=None,
    )

    generated_key = runtime.auth_settings.generated_api_key
    assert generated_key is not None
    assert re.fullmatch(r"esm_share_[A-Za-z0-9_-]+", generated_key) is not None


def test_prepare_cli_runtime_share_mode_rejects_invalid_rate_limit_strategy_override(
    monkeypatch,
) -> None:
    """Share mode should fail fast when the limiter strategy is forced to an invalid value."""

    monkeypatch.setenv("ESM_API_RATE_LIMIT_STRATEGY", "invalid")

    with pytest.raises(
        ApiBoundaryConfigurationError,
        match="ESM_API_RATE_LIMIT_STRATEGY must be one of: ip, principal",
    ):
        prepare_cli_runtime(
            mode="share",
            manual_api_key=None,
        )
