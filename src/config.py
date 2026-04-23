"""Active configuration for the local stream analysis PoC."""

from pathlib import Path
import tempfile

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
API_STREAM_MASTER_PLAYLIST_POLICY = "first_variant"
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
