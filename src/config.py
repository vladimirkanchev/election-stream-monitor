"""Active configuration for the local stream analysis PoC.

This module still keeps most settings as module-level constants because the
project remains a local-first modular monolith. When a setting group benefits
from clearer structure, use a small frozen settings object rather than reading
environment variables inline across multiple modules.
"""

from dataclasses import dataclass
from functools import lru_cache
import os
from pathlib import Path
import tempfile
from typing import Literal, cast

PROJECT_ROOT = Path(__file__).resolve().parent.parent
VIDEO_METRICS_PATH = PROJECT_ROOT / "./data/metrics/video_metrics.csv"
BLUR_METRICS_PATH = PROJECT_ROOT / "./data/metrics/blur_metrics.csv"
SESSION_OUTPUT_FOLDER = PROJECT_ROOT / "./data/sessions"

VIDEO_INPUT_FOLDER = PROJECT_ROOT / "./data/streams/"
API_STREAM_SESSION_FOLDER = PROJECT_ROOT / "./data/api_stream_sessions"
API_STREAM_DEFAULT_SOURCE_URL = ""
API_STREAM_POLL_INTERVAL_SEC = 2.0
API_STREAM_MAX_IDLE_PLAYLIST_POLLS = 3
API_STREAM_RECONNECT_BACKOFF_SEC = 5.0
API_STREAM_ALLOWED_SCHEMES = ("https", "http")
API_STREAM_ALLOWED_HOSTS: tuple[str, ...] = ()
API_STREAM_ALLOW_PRIVATE_HOSTS = False
API_STREAM_VALIDATE_DNS_HOSTS = False
API_STREAM_TRUST_MODE = "local"
API_STREAM_SERVICE_ALLOWED_HOSTS: tuple[str, ...] = ()
API_STREAM_SERVICE_ALLOW_PRIVATE_HOSTS = False
API_STREAM_MAX_RECONNECT_ATTEMPTS = 3
API_STREAM_FETCH_TIMEOUT_SEC = 15.0
API_STREAM_MAX_FETCH_BYTES = 50_000_000
API_STREAM_MAX_SESSION_RUNTIME_SEC = 1_800.0
API_STREAM_MAX_PLAYLIST_REFRESHES = 1_000
API_STREAM_MASTER_PLAYLIST_POLICY: Literal["first_variant"] = "first_variant"
API_STREAM_ACCEPTED_PLAYLIST_TYPES = ("media", "master")
API_STREAM_TEMP_ROOT = Path(tempfile.gettempdir()) / "election-stream-monitor" / "api_stream"
API_STREAM_TEMP_MAX_BYTES = 500_000_000

VIDEO_BLACK_PICTURE_THRESHOLD = 0.98
VIDEO_BLACK_PIXEL_THRESHOLD = 0.10
VIDEO_BLACK_MIN_DURATION_SEC = 0.50
VIDEO_BLACK_ALERT_DURATION_SEC = 1.00
VIDEO_BLACK_SAMPLE_WINDOW_SEC = 3.0
VIDEO_BLACK_SAMPLE_RATIO_THRESHOLD = 0.80
VIDEO_BLACK_RECOVERY_RATIO_THRESHOLD = 0.20

VIDEO_BLUR_SAMPLE_WIDTH = 160
VIDEO_BLUR_SAMPLE_HEIGHT = 90
VIDEO_BLUR_SAMPLE_FPS = 1.0
VIDEO_BLUR_MAX_SAMPLES = 9
VIDEO_BLUR_WINDOW_SIZE = 3
VIDEO_BLUR_ALERT_THRESHOLD = 0.72
VIDEO_BLUR_RECOVERY_THRESHOLD = 0.55
VIDEO_BLUR_MIN_CONSECUTIVE_WINDOWS = 2

VIDEO_METRICS_COLUMNS = [
    "analyzer",
    "source_type",
    "source_group",
    "source_name",
    "window_index",
    "window_start_sec",
    "window_duration_sec",
    "timestamp_utc",
    "processing_sec",
    "duration_sec",
    "black_detected",
    "black_segment_count",
    "total_black_sec",
    "longest_black_sec",
    "black_ratio",
    "picture_threshold_used",
    "pixel_threshold_used",
    "min_duration_sec",
]

BLUR_METRICS_COLUMNS = [
    "analyzer",
    "source_type",
    "source_group",
    "source_name",
    "window_index",
    "window_start_sec",
    "window_duration_sec",
    "timestamp_utc",
    "processing_sec",
    "sample_count",
    "sharpness_p10",
    "sharpness_p90",
    "blur_score",
    "blur_detected",
    "threshold_used",
    "window_size",
    "consecutive_blurry_windows",
]

DATA_SOURCE = (
    "video_segments"  # Supported modes: "video_segments", "video_files", or "api_stream"
)

STORE_BUFFER_SIZE = 20  # Number of rows to buffer before writing to CSV
FFMPEG_TIMEOUT_SEC = 20.0
FFPROBE_TIMEOUT_SEC = 10.0
LOCAL_MEDIA_MAX_BYTES = 1_000_000_000
LOCAL_VIDEO_MAX_DURATION_SEC = 21600.0

ApiAuthMode = Literal["api_key", "jwt"]
SUPPORTED_API_AUTH_MODES: tuple[ApiAuthMode, ...] = ("api_key", "jwt")
API_AUTH_ENABLED = False
API_AUTH_MODE: ApiAuthMode = "api_key"
API_AUTH_ALLOWED_KEYS: tuple[str, ...] = ()
ApiRateLimitStrategy = Literal["principal", "ip"]
SUPPORTED_API_RATE_LIMIT_STRATEGIES: tuple[ApiRateLimitStrategy, ...] = (
    "principal",
    "ip",
)
API_RATE_LIMIT_ENABLED = False
API_RATE_LIMIT_STRATEGY: ApiRateLimitStrategy = "principal"
API_RATE_LIMIT_WINDOW_SEC = 60
API_RATE_LIMIT_MAX_REQUESTS = 100


class ApiBoundaryConfigurationError(RuntimeError):
    """Raised when FastAPI auth or rate-limit settings are invalid.

    This error is intentionally specific to the current HTTP boundary seams so
    bad configuration can fail early at startup with one clear operational
    message instead of surfacing later as scattered request-time failures.
    """


@dataclass(frozen=True)
class ApiAuthSettings:
    """Structured FastAPI authentication settings.

    The names are intentionally auth-neutral so the same seam can later support
    JWT-backed caller identity without redesigning the route boundary.
    """

    enabled: bool
    mode: ApiAuthMode
    allowed_api_keys: tuple[str, ...]


@dataclass(frozen=True)
class ApiRateLimitSettings:
    """Structured FastAPI rate-limiting settings.

    The initial contract stays small on purpose: one enable flag, one caller
    identification strategy, and one fixed-window limit model. That keeps the
    later limiter implementation readable while leaving room for JWT-backed
    principals or a shared backend store in a follow-up step.
    """

    enabled: bool
    strategy: ApiRateLimitStrategy
    window_seconds: int
    max_requests: int


def _parse_bool_env(name: str, default: bool) -> bool:
    """Parse one optional boolean environment override.

    Invalid boolean strings currently fall back to the supplied default rather
    than failing startup. The stricter fail-fast behavior is reserved for the
    auth and limiter settings whose incorrect values would otherwise create a
    misleading protected-boundary state.
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


def _parse_csv_env(name: str, default: tuple[str, ...]) -> tuple[str, ...]:
    """Parse one comma-separated environment value into a tuple of strings."""

    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    values = tuple(
        part.strip()
        for part in raw_value.split(",")
        if part.strip()
    )
    return values or default


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


def _parse_positive_int_env(name: str, default: int) -> int:
    """Parse one positive integer environment value for boundary settings."""

    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    try:
        parsed = int(raw_value.strip())
    except ValueError:
        raise ApiBoundaryConfigurationError(f"{name} must be a positive integer") from None
    if parsed <= 0:
        raise ApiBoundaryConfigurationError(f"{name} must be a positive integer")
    return parsed


@lru_cache(maxsize=1)
def get_api_auth_settings() -> ApiAuthSettings:
    """Return the current FastAPI authentication settings.

    Environment overrides stay centralized here so the API auth boundary can
    consume one small settings object instead of scattering auth-mode parsing
    and API-key parsing across transport code.
    """
    return ApiAuthSettings(
        enabled=_parse_bool_env("ESM_API_AUTH_ENABLED", API_AUTH_ENABLED),
        mode=_parse_auth_mode_env("ESM_API_AUTH_MODE", API_AUTH_MODE),
        allowed_api_keys=_parse_csv_env(
            "ESM_API_AUTH_ALLOWED_KEYS",
            API_AUTH_ALLOWED_KEYS,
        ),
    )


@lru_cache(maxsize=1)
def get_api_rate_limit_settings() -> ApiRateLimitSettings:
    """Return the current FastAPI rate-limiting settings.

    The first rate-limit step is contract-first, so this settings seam exists
    before any request-counting logic. Later HTTP dependencies can consume one
    structured object instead of scattering strategy and window parsing across
    route code.
    """

    return ApiRateLimitSettings(
        enabled=_parse_bool_env("ESM_API_RATE_LIMIT_ENABLED", API_RATE_LIMIT_ENABLED),
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
        ),
    )


def validate_api_auth_settings(settings: ApiAuthSettings) -> None:
    """Validate one FastAPI auth settings object for the current implementation.

    The auth seam is intentionally small today, so the validation rules stay
    small too: only implemented modes are allowed when auth is enabled, and
    enabled API-key auth must have at least one configured key.
    """

    if settings.enabled and settings.mode != "api_key":
        raise ApiBoundaryConfigurationError(
            "FastAPI auth mode must be 'api_key' for the current implementation"
        )
    if settings.enabled and not settings.allowed_api_keys:
        raise ApiBoundaryConfigurationError(
            "FastAPI auth is enabled but no allowed API keys are configured"
        )


def validate_api_rate_limit_settings(settings: ApiRateLimitSettings) -> None:
    """Validate one FastAPI rate-limit settings object for the current implementation.

    The limiter contract is intentionally small today, so validation focuses
    on the currently supported strategy names plus sane fixed-window numeric
    parameters.
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

    This is the single startup-time entrypoint used by the FastAPI lifespan
    hook so the protected HTTP boundary fails early and consistently when its
    current configuration cannot be served safely.
    """

    active_auth_settings = auth_settings or get_api_auth_settings()
    active_rate_limit_settings = rate_limit_settings or get_api_rate_limit_settings()
    validate_api_auth_settings(active_auth_settings)
    validate_api_rate_limit_settings(active_rate_limit_settings)
