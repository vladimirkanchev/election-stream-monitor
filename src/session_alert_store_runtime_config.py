"""Runtime backend selection for the alert persistence seam."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import os
from typing import Literal, cast


AlertStoreBackend = Literal["file", "postgres"]
DEFAULT_ALERT_STORE_BACKEND: AlertStoreBackend = "file"
ALERT_STORE_BACKEND_ENV = "ESM_ALERT_STORE_BACKEND"
SUPPORTED_ALERT_STORE_BACKENDS: tuple[AlertStoreBackend, ...] = ("file", "postgres")
UNSUPPORTED_ALERT_STORE_BACKEND_MESSAGE = (
    f"{ALERT_STORE_BACKEND_ENV} must be one of: file, postgres"
)


class AlertStoreRuntimeConfigurationError(RuntimeError):
    """Raised when the configured alert-store backend is unsupported."""


@dataclass(frozen=True)
class AlertStoreRuntimeSettings:
    """Structured settings for default alert-store selection."""

    backend: AlertStoreBackend


def _parse_backend_env(name: str, default: AlertStoreBackend) -> AlertStoreBackend:
    """Parse one backend env var and fall back to the default on invalid values."""
    raw_value = os.getenv(name)
    if raw_value is None:
        return default

    normalized = raw_value.strip().lower()
    if normalized in SUPPORTED_ALERT_STORE_BACKENDS:
        return cast(AlertStoreBackend, normalized)
    return default


@lru_cache(maxsize=1)
def get_alert_store_runtime_settings() -> AlertStoreRuntimeSettings:
    """Return cached runtime backend-selection settings."""
    return AlertStoreRuntimeSettings(
        backend=_parse_backend_env(
            ALERT_STORE_BACKEND_ENV,
            DEFAULT_ALERT_STORE_BACKEND,
        )
    )


def clear_alert_store_runtime_settings_cache() -> None:
    """Clear the cached alert-store runtime settings."""
    get_alert_store_runtime_settings.cache_clear()


def validate_alert_store_runtime_settings(
    settings: AlertStoreRuntimeSettings,
) -> None:
    """Validate one runtime backend-selection settings object defensively."""
    if settings.backend not in SUPPORTED_ALERT_STORE_BACKENDS:
        raise AlertStoreRuntimeConfigurationError(
            UNSUPPORTED_ALERT_STORE_BACKEND_MESSAGE
        )
