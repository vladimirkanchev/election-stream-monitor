"""Tests for CLI runtime selection and bind admission before server handoff.

Route behavior and operator-facing output belong in neighboring test modules.
"""

from __future__ import annotations

import argparse
import io
import re
from collections.abc import Generator
from typing import Literal
from unittest.mock import ANY, Mock

import pytest

from api_boundary_config import get_api_auth_settings
from api_server_cli import prepare_cli_runtime, run_from_args
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
    ],
)
def test_prepare_cli_runtime_resolves_mode_defaults_and_share_key_source(
    monkeypatch,
    mode: Literal["local", "share"],
    manual_api_key: str | None,
    auth_enabled: bool,
    rate_limit_enabled: bool,
    expected_keys: tuple[str, ...] | None,
    generated: bool,
) -> None:
    """Mode and key-source combinations should resolve a stable boundary posture."""

    if mode == "share" and manual_api_key is None:
        monkeypatch.delenv("ESM_API_AUTH_ALLOWED_KEYS", raising=False)

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


def test_prepare_cli_runtime_uses_environment_key_when_cli_key_is_omitted(
    monkeypatch,
) -> None:
    """An omitted CLI key should preserve the configured environment key."""

    monkeypatch.setenv("ESM_API_AUTH_ALLOWED_KEYS", "environment-key")

    runtime = prepare_cli_runtime(mode="share", manual_api_key=None)

    assert runtime.auth_settings.allowed_api_keys == ("environment-key",)
    assert runtime.auth_settings.generated_api_key is None


def test_prepare_cli_runtime_manual_key_overrides_environment_key(monkeypatch) -> None:
    """The explicit CLI key should take precedence for this startup process."""

    monkeypatch.setenv("ESM_API_AUTH_ALLOWED_KEYS", "environment-key")

    runtime = prepare_cli_runtime(mode="share", manual_api_key="cli-key")

    assert runtime.auth_settings.allowed_api_keys == ("cli-key",)
    assert runtime.auth_settings.generated_api_key is None


def test_prepare_cli_runtime_rejects_blank_manual_share_key() -> None:
    """An explicit blank CLI key must not silently trigger key generation."""

    with pytest.raises(
        ApiBoundaryConfigurationError,
        match="Manual share-mode API key must not be blank",
    ):
        prepare_cli_runtime(mode="share", manual_api_key="   ")


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


def test_prepare_cli_runtime_share_mode_rejects_disabled_auth_override(monkeypatch) -> None:
    """Share mode must fail before an auth-disabling override opens HTTP routes."""

    monkeypatch.setenv("ESM_API_AUTH_ENABLED", "false")

    with pytest.raises(
        ApiBoundaryConfigurationError,
        match="Share mode requires FastAPI authentication",
    ):
        prepare_cli_runtime(
            mode="share",
            manual_api_key=None,
        )


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


@pytest.mark.parametrize(
    "host",
    ["0.0.0.0", "::", "192.168.1.20", "demo.example.test", "::ffff:127.0.0.1"],
)
def test_run_from_args_rejects_network_visible_local_bind_before_server_handoff(
    host: str,
) -> None:
    """Local mode must fail before startup reaches the Uvicorn handoff."""

    server_runner = Mock()

    with pytest.raises(
        ApiBoundaryConfigurationError,
        match="Local FastAPI mode only permits loopback bind hosts",
    ):
        run_from_args(
            argparse.Namespace(mode="local", host=host, port=8000, api_key=None),
            stdout=io.StringIO(),
            server_runner=server_runner,
        )

    server_runner.assert_not_called()


@pytest.mark.parametrize("host", ["[::1]", "127.0.0.1:8000", " bad-host"])
def test_run_from_args_rejects_invalid_bind_before_server_handoff(host: str) -> None:
    """Malformed bind values must fail in both modes rather than reach Uvicorn."""

    server_runner = Mock()

    with pytest.raises(
        ApiBoundaryConfigurationError,
        match="FastAPI bind host must be a numeric address or valid ASCII hostname",
    ):
        run_from_args(
            argparse.Namespace(mode="share", host=host, port=8000, api_key=None),
            stdout=io.StringIO(),
            server_runner=server_runner,
        )

    server_runner.assert_not_called()


@pytest.mark.parametrize(
    ("mode", "host", "expected_auth_enabled"),
    [
        ("local", "127.0.0.1", False),
        ("local", "localhost", False),
        ("local", "::1", False),
        ("share", "0.0.0.0", True),
        ("share", "::", True),
        ("share", "2001:db8::10", True),
    ],
)
def test_run_from_args_admits_policy_permitted_binds_without_opening_a_socket(
    mode: Literal["local", "share"],
    host: str,
    expected_auth_enabled: bool,
) -> None:
    """Permitted loopback and share binds should reach only the fake handoff.

    This tests CLI admission, not whether a particular machine can bind the
    address. `share` must resolve API-key authentication before the handoff.
    """

    server_runner = Mock()

    run_from_args(
        argparse.Namespace(mode=mode, host=host, port=8000, api_key=None),
        stdout=io.StringIO(),
        server_runner=server_runner,
    )

    server_runner.assert_called_once_with(ANY, host=host, port=8000)
    assert get_api_auth_settings().enabled is expected_auth_enabled
