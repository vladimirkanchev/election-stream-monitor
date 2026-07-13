"""Runtime backend selection for the alert persistence seam.

This module owns only the backend-mode choice for the default alert store.
Unset or unsupported values stay on the safe file-backed default, while
explicit PostgreSQL bootstrap validation happens in the narrower Postgres
config module.
"""

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
    """Raised when explicit alert-store runtime configuration cannot be honored."""


@dataclass(frozen=True)
class AlertStoreRuntimeSettings:
    """Structured settings for choosing the default alert-store backend."""

    backend: AlertStoreBackend


def _parse_backend_env(name: str, default: AlertStoreBackend) -> AlertStoreBackend:
    """Parse one backend env var and normalize unsupported values to the default."""
    raw_value = os.getenv(name)
    if raw_value is None:
        return default

    normalized = raw_value.strip().lower()
    if normalized in SUPPORTED_ALERT_STORE_BACKENDS:
        return cast(AlertStoreBackend, normalized)
    return default


@lru_cache(maxsize=1)
def get_alert_store_runtime_settings() -> AlertStoreRuntimeSettings:
    """Return cached runtime backend-selection settings.

    Missing or invalid backend env values resolve to the safe file-backed
    default for this rollout stage.
    """
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
    """Validate one runtime backend-selection object defensively."""
    if settings.backend not in SUPPORTED_ALERT_STORE_BACKENDS:
        raise AlertStoreRuntimeConfigurationError(
            UNSUPPORTED_ALERT_STORE_BACKEND_MESSAGE
        )
