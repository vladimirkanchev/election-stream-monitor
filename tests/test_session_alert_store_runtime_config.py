"""Focused tests for runtime alert-store backend selection.

This file stays at the runtime-config seam and does not exercise bootstrap or
concrete store behavior.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from session_alert_store_runtime_config import (
    ALERT_STORE_BACKEND_ENV,
    AlertStoreRuntimeConfigurationError,
    AlertStoreRuntimeSettings,
    clear_alert_store_runtime_settings_cache,
    get_alert_store_runtime_settings,
    validate_alert_store_runtime_settings,
)


@pytest.fixture(autouse=True)
def _clear_alert_store_runtime_settings_cache() -> Iterator[None]:
    """Keep cached runtime backend-selection settings isolated between tests."""
    clear_alert_store_runtime_settings_cache()
    yield
    clear_alert_store_runtime_settings_cache()


def test_get_alert_store_runtime_settings_defaults_to_file_backend(
    monkeypatch,
) -> None:
    """The runtime backend selector should stay file-backed by default."""
    monkeypatch.delenv(ALERT_STORE_BACKEND_ENV, raising=False)

    settings = get_alert_store_runtime_settings()

    assert settings == AlertStoreRuntimeSettings(backend="file")


def test_get_alert_store_runtime_settings_reads_supported_backend_override(
    monkeypatch,
) -> None:
    """The runtime selector should ingest the explicit backend env var."""
    monkeypatch.setenv(ALERT_STORE_BACKEND_ENV, "postgres")

    settings = get_alert_store_runtime_settings()

    assert settings == AlertStoreRuntimeSettings(backend="postgres")


def test_get_alert_store_runtime_settings_falls_back_to_file_on_invalid_env_value(
    monkeypatch,
) -> None:
    """Invalid runtime backend env values should resolve to the safe file default."""
    monkeypatch.setenv(ALERT_STORE_BACKEND_ENV, "sqlite")

    settings = get_alert_store_runtime_settings()

    assert settings == AlertStoreRuntimeSettings(backend="file")


def test_validate_alert_store_runtime_settings_rejects_unsupported_backend() -> None:
    """Validation should fail clearly for unsupported backend modes."""
    with pytest.raises(
        AlertStoreRuntimeConfigurationError,
        match=f"{ALERT_STORE_BACKEND_ENV} must be one of: file, postgres",
    ):
        validate_alert_store_runtime_settings(
            AlertStoreRuntimeSettings(backend="sqlite")  # type: ignore[arg-type]
        )
