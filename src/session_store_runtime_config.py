"""Parse and validate runtime settings for default session-store selection.

Today this configuration is intentionally small: `file` is the only supported
backend, and missing or invalid environment values fall back to that default.
Future PostgreSQL rollout should extend this module instead of spreading
backend rules across runtime code.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import os
from typing import Literal, cast


SessionStoreBackend = Literal["file"]
DEFAULT_SESSION_STORE_BACKEND: SessionStoreBackend = "file"
SESSION_STORE_BACKEND_ENV = "ESM_SESSION_STORE_BACKEND"
SUPPORTED_SESSION_STORE_BACKENDS: tuple[SessionStoreBackend, ...] = ("file",)
UNSUPPORTED_SESSION_STORE_BACKEND_MESSAGE = (
    f"{SESSION_STORE_BACKEND_ENV} must be one of: file"
)


class SessionStoreRuntimeConfigurationError(RuntimeError):
    """Raised when code tries to use an unsupported session-store backend."""


@dataclass(frozen=True)
class SessionStoreRuntimeSettings:
    """Normalized settings used to choose the default runtime store."""

    backend: SessionStoreBackend


def _parse_backend_env(name: str, default: SessionStoreBackend) -> SessionStoreBackend:
    """Read one backend env var, normalize it, and fall back on invalid input."""
    raw_value = os.getenv(name)
    if raw_value is None:
        return default

    normalized = raw_value.strip().lower()
    if normalized in SUPPORTED_SESSION_STORE_BACKENDS:
        return cast(SessionStoreBackend, normalized)
    return default


@lru_cache(maxsize=1)
def get_session_store_runtime_settings() -> SessionStoreRuntimeSettings:
    """Return cached runtime settings for default store selection."""
    return SessionStoreRuntimeSettings(
        backend=_parse_backend_env(
            SESSION_STORE_BACKEND_ENV,
            DEFAULT_SESSION_STORE_BACKEND,
        )
    )


def clear_session_store_runtime_settings_cache() -> None:
    """Clear the cached session-store runtime settings."""
    get_session_store_runtime_settings.cache_clear()


def validate_session_store_runtime_settings(
    settings: SessionStoreRuntimeSettings,
) -> None:
    """Reject runtime settings that name an unsupported backend."""
    if settings.backend not in SUPPORTED_SESSION_STORE_BACKENDS:
        raise SessionStoreRuntimeConfigurationError(
            UNSUPPORTED_SESSION_STORE_BACKEND_MESSAGE
        )
