"""Shared test helpers for env-driven FastAPI boundary settings.

These helpers keep the CLI/run-mode tests and boundary-settings tests aligned
around one small environment snapshot seam instead of duplicating the same
cleanup logic across several split files. They intentionally own only:

- env snapshot/restore
- cached boundary-settings reset
- in-memory limiter reset
"""

from __future__ import annotations

import os

from config import clear_fastapi_boundary_settings_caches
from tests.api_alert_test_support import reset_alert_route_rate_limit_state

BOUNDARY_ENV_NAMES: tuple[str, ...] = (
    "ESM_FASTAPI_RUN_MODE",
    "ESM_API_AUTH_ENABLED",
    "ESM_API_AUTH_ALLOWED_KEYS",
    "ESM_API_AUTH_MODE",
    "ESM_API_RATE_LIMIT_ENABLED",
    "ESM_API_RATE_LIMIT_STRATEGY",
    "ESM_API_RATE_LIMIT_WINDOW_SEC",
    "ESM_API_RATE_LIMIT_MAX_REQUESTS",
)


def snapshot_boundary_env() -> dict[str, str | None]:
    """Capture the current env-driven FastAPI boundary settings."""

    return {name: os.environ.get(name) for name in BOUNDARY_ENV_NAMES}


def restore_boundary_env(snapshot: dict[str, str | None]) -> None:
    """Restore one previously captured FastAPI boundary env snapshot."""

    for name, value in snapshot.items():
        if value is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = value


def reset_boundary_test_state() -> None:
    """Reset env-driven FastAPI boundary caches plus in-memory limiter state."""

    clear_fastapi_boundary_settings_caches()
    reset_alert_route_rate_limit_state()


def restore_boundary_test_state(snapshot: dict[str, str | None]) -> None:
    """Restore one env snapshot and reset shared boundary-local process state."""

    restore_boundary_env(snapshot)
    reset_boundary_test_state()
