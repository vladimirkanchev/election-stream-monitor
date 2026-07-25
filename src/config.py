"""Active configuration for the local stream analysis PoC.

This module keeps the repo's broad project constants in one place. The newer
FastAPI boundary settings live in `api_boundary_config.py`, but are re-exported
here so existing imports do not need to churn all at once.
"""

from pathlib import Path
import tempfile
from typing import Literal

import api_boundary_config as _api_boundary_config

PROJECT_ROOT = Path(__file__).resolve().parent.parent
VIDEO_METRICS_PATH = PROJECT_ROOT / "./data/metrics/video_metrics.csv"
BLUR_METRICS_PATH = PROJECT_ROOT / "./data/metrics/blur_metrics.csv"
SESSION_OUTPUT_FOLDER = PROJECT_ROOT / "./data/sessions"

VIDEO_INPUT_FOLDER = PROJECT_ROOT / "./data/streams/"
API_STREAM_SESSION_FOLDER = PROJECT_ROOT / "./data/api_stream_sessions"
API_STREAM_DEFAULT_SOURCE_URL = ""
API_STREAM_POLL_INTERVAL_SEC = 2.0
API_STREAM_CANCEL_CHECK_SKIP_COUNT = 8
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

VIDEO_BLUR_SAMPLE_MAX_WIDTH = 320
VIDEO_BLUR_SAMPLE_MAX_HEIGHT = 180
VIDEO_BLUR_SAMPLE_FPS = 1.0
VIDEO_BLUR_MAX_SAMPLES = 9
VIDEO_BLUR_MIN_MOTION_SAMPLES = 5
VIDEO_BLUR_MAX_MOTION_SAMPLE_FPS = 5.0
VIDEO_BLUR_WINDOW_SIZE = 3
VIDEO_BLUR_ALERT_THRESHOLD = 0.88
VIDEO_BLUR_RECOVERY_THRESHOLD = 0.68
VIDEO_BLUR_MIN_CONSECUTIVE_WINDOWS = 2
VIDEO_BLUR_MIN_TOTAL_SAMPLES = 5
VIDEO_BLUR_MOTION_AMBIGUOUS_MEDIAN_THRESHOLD = 0.10
VIDEO_BLUR_MOTION_GUARD_MEDIAN_THRESHOLD = 0.18
VIDEO_BLUR_MOTION_GUARD_PEAK_THRESHOLD = 0.24
VIDEO_BLUR_MOTION_AMBIGUOUS_ALERT_THRESHOLD = 0.93

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
    "motion_mean",
    "motion_p90",
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

ApiAuthMode = _api_boundary_config.ApiAuthMode
SUPPORTED_API_AUTH_MODES = _api_boundary_config.SUPPORTED_API_AUTH_MODES
FastApiRunMode = _api_boundary_config.FastApiRunMode
SUPPORTED_FASTAPI_RUN_MODES = _api_boundary_config.SUPPORTED_FASTAPI_RUN_MODES
FASTAPI_RUN_MODE = _api_boundary_config.FASTAPI_RUN_MODE
API_AUTH_ENABLED = _api_boundary_config.API_AUTH_ENABLED
API_AUTH_MODE = _api_boundary_config.API_AUTH_MODE
API_AUTH_ALLOWED_KEYS = _api_boundary_config.API_AUTH_ALLOWED_KEYS
ApiRateLimitStrategy = _api_boundary_config.ApiRateLimitStrategy
SUPPORTED_API_RATE_LIMIT_STRATEGIES = _api_boundary_config.SUPPORTED_API_RATE_LIMIT_STRATEGIES
API_RATE_LIMIT_ENABLED = _api_boundary_config.API_RATE_LIMIT_ENABLED
API_RATE_LIMIT_STRATEGY = _api_boundary_config.API_RATE_LIMIT_STRATEGY
API_RATE_LIMIT_WINDOW_SEC = _api_boundary_config.API_RATE_LIMIT_WINDOW_SEC
API_RATE_LIMIT_MAX_REQUESTS = _api_boundary_config.API_RATE_LIMIT_MAX_REQUESTS
API_RATE_LIMIT_MAX_REQUESTS_CEILING = (
    _api_boundary_config.API_RATE_LIMIT_MAX_REQUESTS_CEILING
)
PLAYBACK_RESOLUTION_RATE_LIMIT_MAX_REQUESTS = (
    _api_boundary_config.PLAYBACK_RESOLUTION_RATE_LIMIT_MAX_REQUESTS
)
MAX_HTTP_REQUEST_BODY_BYTES = _api_boundary_config.MAX_HTTP_REQUEST_BODY_BYTES
ApiBoundaryConfigurationError = _api_boundary_config.ApiBoundaryConfigurationError
FastApiRunModeSettings = _api_boundary_config.FastApiRunModeSettings
ApiAuthSettings = _api_boundary_config.ApiAuthSettings
ApiRateLimitSettings = _api_boundary_config.ApiRateLimitSettings
get_fastapi_run_mode_settings = _api_boundary_config.get_fastapi_run_mode_settings
clear_fastapi_boundary_settings_caches = _api_boundary_config.clear_fastapi_boundary_settings_caches
get_api_auth_settings = _api_boundary_config.get_api_auth_settings
get_api_rate_limit_settings = _api_boundary_config.get_api_rate_limit_settings
get_session_control_rate_limit_settings = (
    _api_boundary_config.get_session_control_rate_limit_settings
)
get_session_start_rate_limit_settings = (
    _api_boundary_config.get_session_start_rate_limit_settings
)
get_playback_resolution_rate_limit_settings = (
    _api_boundary_config.get_playback_resolution_rate_limit_settings
)
validate_api_auth_settings = _api_boundary_config.validate_api_auth_settings
validate_api_rate_limit_settings = _api_boundary_config.validate_api_rate_limit_settings
validate_fastapi_boundary_settings = _api_boundary_config.validate_fastapi_boundary_settings
