"""FastAPI boundary configuration and startup validation.

This module owns the user-facing `local`/`share` runtime policy plus the
lower-level authentication and limiter settings used by protected FastAPI
routes.

It deliberately keeps three related concerns together:

- env parsing for the boundary-local settings
- small immutable settings objects for auth and rate limiting
- fail-fast validation used by startup code and CLI tooling

Keeping those concerns separate from the repo's broader project config makes
the HTTP protection seam easier to find, review, and evolve.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import os
import secrets
from typing import Literal, cast

ApiAuthMode = Literal["api_key", "jwt"]
SUPPORTED_API_AUTH_MODES: tuple[ApiAuthMode, ...] = ("api_key", "jwt")
FastApiRunMode = Literal["local", "share"]
SUPPORTED_FASTAPI_RUN_MODES: tuple[FastApiRunMode, ...] = ("local", "share")
FASTAPI_RUN_MODE: FastApiRunMode = "local"
API_AUTH_ENABLED = False
API_AUTH_MODE: ApiAuthMode = "api_key"
API_AUTH_ALLOWED_KEYS: tuple[str, ...] = ()
# `token_urlsafe` receives random bytes, so this preserves 192 bits of entropy.
GENERATED_SHARE_API_KEY_TOKEN_BYTES = 24
ApiRateLimitStrategy = Literal["principal", "ip"]
SUPPORTED_API_RATE_LIMIT_STRATEGIES: tuple[ApiRateLimitStrategy, ...] = (
    "principal",
    "ip",
)
API_RATE_LIMIT_ENABLED = False
API_RATE_LIMIT_STRATEGY: ApiRateLimitStrategy = "principal"
API_RATE_LIMIT_WINDOW_SEC = 60
API_RATE_LIMIT_MAX_REQUESTS = 100
API_RATE_LIMIT_MAX_REQUESTS_CEILING = 200
SESSION_CONTROL_RATE_LIMIT_MAX_REQUESTS = 12
SESSION_START_RATE_LIMIT_MAX_REQUESTS = 6
PLAYBACK_RESOLUTION_RATE_LIMIT_MAX_REQUESTS = 30


class ApiBoundaryConfigurationError(RuntimeError):
    """Raised when FastAPI auth or rate-limit settings are invalid.

    The exception is boundary-specific on purpose. It lets the FastAPI app and
    the user-facing CLI fail early with one clear operational error instead of
    surfacing the same misconfiguration later as scattered request-time
    failures.
    """


@dataclass(frozen=True)
class FastApiRunModeSettings:
    """High-level FastAPI runtime policy for the current project stage.

    The mode is intentionally small and user-facing:

    - `local` keeps trusted local use friction-free
    - `share` enables the lightweight protected sharing preset

    Lower-level auth and limiter settings still exist, but this mode is the
    main place where their default security posture is chosen.
    """

    mode: FastApiRunMode


@dataclass(frozen=True)
class ApiAuthSettings:
    """Structured FastAPI authentication settings.

    The shape stays intentionally auth-neutral so the route boundary can carry
    one caller-identity settings object today for API keys and later for other
    auth models without redesigning the transport seam. A generated key exists
    only for this cached settings lifetime and must not be logged or persisted.
    """

    enabled: bool
    mode: ApiAuthMode
    allowed_api_keys: tuple[str, ...]
    generated_api_key: str | None = None


@dataclass(frozen=True)
class ApiRateLimitSettings:
    """Structured FastAPI rate-limiting settings.

    This shared base is used directly by alert reads and by fixed-budget route
    families that inherit its enablement, identity strategy, and window:

    - one enable flag
    - one caller-identification strategy
    - one fixed-window setting set
    """

    enabled: bool
    strategy: ApiRateLimitStrategy
    window_seconds: int
    max_requests: int


def _parse_bool_env(name: str, default: bool) -> bool:
    """Parse one optional boolean environment override.

    Invalid values currently fall back to the supplied default instead of
    failing startup. The stricter fail-fast behavior is reserved for the
    settings that would otherwise create a misleading protected-boundary
    posture.
    """

    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    normalized = raw_value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return default


def _parse_fastapi_run_mode_env(
    name: str,
    default: FastApiRunMode,
) -> FastApiRunMode:
    """Parse one FastAPI run-mode override or raise on unsupported values."""

    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    normalized = raw_value.strip().lower()
    if normalized not in SUPPORTED_FASTAPI_RUN_MODES:
        supported_values = ", ".join(sorted(SUPPORTED_FASTAPI_RUN_MODES))
        raise ApiBoundaryConfigurationError(
            f"{name} must be one of: {supported_values}"
        )
    return cast(FastApiRunMode, normalized)


def _parse_auth_mode_env(name: str, default: ApiAuthMode) -> ApiAuthMode:
    """Parse one FastAPI auth-mode override or raise on unsupported values."""

    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    normalized = raw_value.strip().lower()
    if normalized not in SUPPORTED_API_AUTH_MODES:
        supported_values = ", ".join(sorted(SUPPORTED_API_AUTH_MODES))
        raise ApiBoundaryConfigurationError(
            f"{name} must be one of: {supported_values}"
        )
    return cast(ApiAuthMode, normalized)


def _parse_api_auth_allowed_keys_env() -> tuple[str, ...]:
    """Return configured API keys or reject explicitly blank entries.

    An unset variable means no configured key. A present-but-empty value is a
    configuration mistake, not a request to generate another share-mode key.
    """

    name = "ESM_API_AUTH_ALLOWED_KEYS"
    raw_value = os.getenv(name)
    if raw_value is None:
        return API_AUTH_ALLOWED_KEYS

    values = tuple(part.strip() for part in raw_value.split(","))
    if any(not value for value in values):
        raise ApiBoundaryConfigurationError(
            f"{name} must contain one or more non-blank comma-separated API keys"
        )
    return values


def _parse_rate_limit_strategy_env(
    name: str,
    default: ApiRateLimitStrategy,
) -> ApiRateLimitStrategy:
    """Parse one limiter-strategy override or raise on unsupported values."""

    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    normalized = raw_value.strip().lower()
    if normalized not in SUPPORTED_API_RATE_LIMIT_STRATEGIES:
        supported_values = ", ".join(sorted(SUPPORTED_API_RATE_LIMIT_STRATEGIES))
        raise ApiBoundaryConfigurationError(
            f"{name} must be one of: {supported_values}"
        )
    return cast(ApiRateLimitStrategy, normalized)


def _parse_positive_int_env(
    name: str,
    default: int,
    *,
    maximum: int | None = None,
) -> int:
    """Parse one bounded positive integer environment value for boundary settings."""

    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    try:
        parsed = int(raw_value.strip())
    except ValueError:
        raise ApiBoundaryConfigurationError(f"{name} must be a positive integer") from None
    if parsed <= 0:
        raise ApiBoundaryConfigurationError(f"{name} must be a positive integer")
    if maximum is not None and parsed > maximum:
        raise ApiBoundaryConfigurationError(f"{name} must not exceed {maximum}")
    return parsed


@lru_cache(maxsize=1)
def get_fastapi_run_mode_settings() -> FastApiRunModeSettings:
    """Return the current high-level FastAPI runtime mode.

    The result is cached because normal request handling treats the selected
    startup posture as process-local configuration rather than something that
    changes per request.
    """

    return FastApiRunModeSettings(
        mode=_parse_fastapi_run_mode_env(
            "ESM_FASTAPI_RUN_MODE",
            FASTAPI_RUN_MODE,
        ),
    )


def is_fastapi_documentation_enabled() -> bool:
    """Return whether FastAPI's framework documentation may be served.

    Local development keeps `/docs`, `/redoc`, and `/openapi.json` available.
    Share mode hides those discovery surfaces by default; a future remote API
    integration can add an explicit opt-in without weakening that default.
    """

    return get_fastapi_run_mode_settings().mode == "local"


def clear_fastapi_boundary_settings_caches() -> None:
    """Clear cached FastAPI run-mode, auth, and limiter settings.

    Startup-oriented tooling such as the explicit FastAPI CLI uses this after
    mutating process environment variables so the next settings read observes
    the intended mode and generated-key state.
    """

    get_fastapi_run_mode_settings.cache_clear()
    get_api_auth_settings.cache_clear()
    get_api_rate_limit_settings.cache_clear()
    get_session_control_rate_limit_settings.cache_clear()
    get_session_start_rate_limit_settings.cache_clear()
    get_playback_resolution_rate_limit_settings.cache_clear()


@lru_cache(maxsize=1)
def get_api_auth_settings() -> ApiAuthSettings:
    """Return the current FastAPI authentication settings.

    Environment parsing stays centralized here so auth code can consume one
    small immutable settings object instead of re-reading multiple env vars
    across the transport boundary.
    """

    run_mode = get_fastapi_run_mode_settings().mode
    enabled = _resolve_api_auth_enabled(run_mode)
    allowed_api_keys, generated_api_key = _resolve_api_auth_allowed_keys(
        run_mode=run_mode,
        enabled=enabled,
    )
    return ApiAuthSettings(
        enabled=enabled,
        mode=_parse_auth_mode_env("ESM_API_AUTH_MODE", API_AUTH_MODE),
        allowed_api_keys=allowed_api_keys,
        generated_api_key=generated_api_key,
    )


@lru_cache(maxsize=1)
def get_api_rate_limit_settings() -> ApiRateLimitSettings:
    """Return the shared limiter settings used by alert reads and route families."""

    run_mode = get_fastapi_run_mode_settings().mode
    return ApiRateLimitSettings(
        enabled=_parse_bool_env(
            "ESM_API_RATE_LIMIT_ENABLED",
            _get_default_api_rate_limit_enabled(run_mode),
        ),
        strategy=_parse_rate_limit_strategy_env(
            "ESM_API_RATE_LIMIT_STRATEGY",
            API_RATE_LIMIT_STRATEGY,
        ),
        window_seconds=_parse_positive_int_env(
            "ESM_API_RATE_LIMIT_WINDOW_SEC",
            API_RATE_LIMIT_WINDOW_SEC,
        ),
        max_requests=_parse_positive_int_env(
            "ESM_API_RATE_LIMIT_MAX_REQUESTS",
            API_RATE_LIMIT_MAX_REQUESTS,
            maximum=API_RATE_LIMIT_MAX_REQUESTS_CEILING,
        ),
    )


def _fixed_rate_limit_settings(max_requests: int) -> ApiRateLimitSettings:
    """Return the shared limiter policy with one fixed family ceiling."""

    base_settings = get_api_rate_limit_settings()
    return ApiRateLimitSettings(
        enabled=base_settings.enabled,
        strategy=base_settings.strategy,
        window_seconds=base_settings.window_seconds,
        max_requests=max_requests,
    )


@lru_cache(maxsize=1)
def get_session_control_rate_limit_settings() -> ApiRateLimitSettings:
    """Return the shared session-control budget for start and cancel requests.

    The budget follows the current local/share enablement, identity strategy,
    and window settings. Its fixed ceiling is separate from alert reads; the
    stricter start guard preserves capacity for cancellation.
    """

    return _fixed_rate_limit_settings(SESSION_CONTROL_RATE_LIMIT_MAX_REQUESTS)


@lru_cache(maxsize=1)
def get_session_start_rate_limit_settings() -> ApiRateLimitSettings:
    """Return the stricter spawn guard applied only to session starts."""

    return _fixed_rate_limit_settings(SESSION_START_RATE_LIMIT_MAX_REQUESTS)


@lru_cache(maxsize=1)
def get_playback_resolution_rate_limit_settings() -> ApiRateLimitSettings:
    """Return the dedicated budget for source-resolution work.

    Playback validation can touch the filesystem and, when explicitly enabled,
    DNS. It therefore stays separate from session control and alert reads while
    sharing the current mode, caller identity, and fixed window.
    """

    return _fixed_rate_limit_settings(PLAYBACK_RESOLUTION_RATE_LIMIT_MAX_REQUESTS)


def validate_api_auth_settings(settings: ApiAuthSettings) -> None:
    """Validate one FastAPI auth settings object for the current implementation.

    The current boundary supports only API-key auth when authentication is
    enabled, and protected mode must have at least one usable key.
    """

    if settings.enabled and settings.mode != "api_key":
        raise ApiBoundaryConfigurationError(
            "FastAPI auth mode must be 'api_key' for the current implementation"
        )
    if settings.enabled and not settings.allowed_api_keys:
        raise ApiBoundaryConfigurationError(
            "FastAPI auth is enabled but no allowed API keys are configured"
        )
    if any(not api_key.strip() for api_key in settings.allowed_api_keys):
        raise ApiBoundaryConfigurationError(
            "FastAPI auth contains a blank allowed API key"
        )


def _get_default_api_auth_enabled(run_mode: FastApiRunMode) -> bool:
    """Return the default auth-enabled state for one FastAPI run mode."""

    if run_mode == "local":
        return False
    if run_mode == "share":
        return True
    raise ApiBoundaryConfigurationError(f"Unsupported FastAPI run mode: {run_mode}")


def _resolve_api_auth_enabled(run_mode: FastApiRunMode) -> bool:
    """Resolve auth enablement without permitting an open share-mode server."""

    enabled = _parse_bool_env(
        "ESM_API_AUTH_ENABLED",
        _get_default_api_auth_enabled(run_mode),
    )
    if run_mode == "share" and not enabled:
        raise ApiBoundaryConfigurationError(
            "Share mode requires FastAPI authentication; "
            "ESM_API_AUTH_ENABLED cannot be disabled"
        )
    return enabled


def _resolve_api_auth_allowed_keys(
    *,
    run_mode: FastApiRunMode,
    enabled: bool,
) -> tuple[tuple[str, ...], str | None]:
    """Resolve configured API keys plus any generated share-mode key.

    Share mode is intentionally lightweight. When auth is active there and no
    configured key exists, generate one strong process-local key so protected
    sharing remains usable without a separate user-management step.
    """

    configured_keys = _parse_api_auth_allowed_keys_env()
    if configured_keys or not enabled or run_mode != "share":
        return configured_keys, None

    generated_api_key = _generate_share_mode_api_key()
    return (generated_api_key,), generated_api_key


def _generate_share_mode_api_key() -> str:
    """Return one 192-bit API key for the current share-mode settings lifetime."""

    return f"esm_share_{secrets.token_urlsafe(GENERATED_SHARE_API_KEY_TOKEN_BYTES)}"


def _get_default_api_rate_limit_enabled(run_mode: FastApiRunMode) -> bool:
    """Return the default limiter-enabled state for one FastAPI run mode."""

    if run_mode == "local":
        return False
    if run_mode == "share":
        return True
    raise ApiBoundaryConfigurationError(f"Unsupported FastAPI run mode: {run_mode}")


def validate_api_rate_limit_settings(settings: ApiRateLimitSettings) -> None:
    """Validate one FastAPI rate-limit settings object for the current implementation.

    Validation stays focused on the current contract: supported strategy names
    plus sane fixed-window numeric parameters.
    """

    if settings.strategy not in SUPPORTED_API_RATE_LIMIT_STRATEGIES:
        supported_values = ", ".join(sorted(SUPPORTED_API_RATE_LIMIT_STRATEGIES))
        raise ApiBoundaryConfigurationError(
            f"FastAPI rate-limit strategy must be one of: {supported_values}"
        )
    if settings.window_seconds <= 0:
        raise ApiBoundaryConfigurationError(
            "FastAPI rate-limit window_seconds must be a positive integer"
        )
    if settings.max_requests <= 0:
        raise ApiBoundaryConfigurationError(
            "FastAPI rate-limit max_requests must be a positive integer"
        )


def validate_fastapi_boundary_settings(
    *,
    auth_settings: ApiAuthSettings | None = None,
    rate_limit_settings: ApiRateLimitSettings | None = None,
) -> None:
    """Validate the current FastAPI auth and rate-limit configuration together.

    This is the single startup-facing entrypoint used by the FastAPI app
    lifespan and the CLI runtime preparation path so protected startup fails
    early and consistently.
    """

    active_auth_settings = auth_settings or get_api_auth_settings()
    active_rate_limit_settings = rate_limit_settings or get_api_rate_limit_settings()
    validate_api_auth_settings(active_auth_settings)
    validate_api_rate_limit_settings(active_rate_limit_settings)
