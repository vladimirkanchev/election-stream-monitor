"""Shared api_stream contracts and helper builders.

This module keeps the stable shapes and identity helpers used by the live
loader without mixing them with the concrete HTTP/HLS transport mechanics.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil
from typing import Iterator, Literal, Protocol

from analyzer_contract import AnalysisSlice
import config
from source_validation import validate_api_stream_url


ApiStreamFailureKind = Literal["temporary_failure", "retryable_failure", "terminal_failure"]


@dataclass(frozen=True)
class ApiStreamRuntimePolicy:
    """Current transport and trust rules for live-stream loading."""

    allowed_schemes: tuple[str, ...]
    allowed_hosts: tuple[str, ...]
    allow_private_hosts: bool
    max_reconnect_attempts: int
    fetch_timeout_sec: float
    max_fetch_bytes: int
    max_session_runtime_sec: float
    max_playlist_refreshes: int


@dataclass(frozen=True)
class ApiStreamHttpLoaderContract:
    """Concrete return and playlist policy for the HTTP/HLS loader."""

    returned_slice_kind: Literal["analysis_slice"]
    chunk_materialization: Literal["session_scoped_temp_file"]
    accepted_playlist_types: tuple[str, ...]
    master_playlist_policy: Literal["first_variant"]
    playlist_poll_interval_sec: float
    max_idle_playlist_polls: int


@dataclass(frozen=True)
class ApiStreamTempFilePolicy:
    """Lifecycle rules for temp media created by live loading."""

    temp_root: Path
    session_scoped: bool
    cleanup_on_completed: bool
    cleanup_on_cancelled: bool
    cleanup_on_failed: bool
    max_bytes: int


@dataclass(frozen=True)
class ApiStreamSourceContract:
    """Normalized source contract shared by validation, playback, and loading."""

    kind: Literal["api_stream"]
    input_path: str
    access: Literal["api_stream"] = "api_stream"


@dataclass(frozen=True)
class ApiStreamStartSessionContract:
    """Backend-facing start-session payload for one live input."""

    mode: Literal["api_stream"]
    input_path: str
    selected_detectors: list[str]


@dataclass(frozen=True)
class ApiStreamPlaybackContract:
    """Playback-resolution contract for live sources."""

    source: str


@dataclass(frozen=True)
class ApiStreamFailure:
    """Named failure shape reserved for reconnect and loader behavior."""

    kind: ApiStreamFailureKind
    message: str
    source_name: str | None = None


class ApiStreamLoaderError(RuntimeError):
    """Structured loader failure raised by fake and real stream loaders."""

    def __init__(self, failure: ApiStreamFailure) -> None:
        super().__init__(failure.message)
        self.failure = failure


def _build_api_stream_failure(
    kind: ApiStreamFailureKind,
    message: str,
    *,
    source_name: str | None = None,
) -> ApiStreamFailure:
    """Return one normalized loader failure payload."""
    return ApiStreamFailure(
        kind=kind,
        message=message,
        source_name=source_name,
    )


def _api_stream_loader_error(
    kind: ApiStreamFailureKind,
    message: str,
    *,
    source_name: str | None = None,
) -> ApiStreamLoaderError:
    """Return one structured loader exception without duplicating wrappers."""
    return ApiStreamLoaderError(
        _build_api_stream_failure(
            kind,
            message,
            source_name=source_name,
        )
    )


@dataclass(frozen=True)
class ApiStreamChunkIdentity:
    """Stable identity for one live chunk/slice across reconnect and persistence."""

    source_group: str
    chunk_index: int
    current_item: str


@dataclass(frozen=True)
class ApiStreamPlaylistSegment:
    """One normalized HLS media-playlist entry."""

    sequence: int
    uri: str
    duration_sec: float


@dataclass(frozen=True)
class ApiStreamMediaPlaylistSnapshot:
    """Normalized metadata for one HLS media-playlist refresh."""

    segments: list[ApiStreamPlaylistSegment]
    is_endlist: bool
    target_duration_sec: float | None


@dataclass(frozen=True)
class ApiStreamTelemetrySnapshot:
    """Compact transport counters and stop/failure context for one loader run."""

    source_url_class: str | None = None
    playlist_refresh_count: int = 0
    accepted_slice_count: int = 0
    skipped_replay_count: int = 0
    reconnect_attempt_count: int = 0
    reconnect_budget_exhaustion_count: int = 0
    terminal_failure_reason: str | None = None
    stop_reason: str | None = None


class ApiStreamLoader(Protocol):
    """Loader contract for connecting to a live source and yielding slices."""

    def connect(self, source: ApiStreamSourceContract) -> None:
        """Prepare one live source for iteration."""

    def iter_slices(self) -> Iterator[AnalysisSlice]:
        """Yield normalized analysis slices for one live source."""
        ...

    def close(self) -> None:
        """Release loader resources after iteration finishes."""
        ...

    def load_persisted_identity_keys(self) -> set[tuple[str, int, str]]:
        """Return reconnect de-dup keys already persisted for this session."""
        ...

    def persist_identity_key(self, key: tuple[str, int, str]) -> None:
        """Persist one accepted reconnect de-dup key for this session."""
        ...

    def accepted_slice_count(self) -> int:
        """Return the number of accepted slices discovered so far."""
        ...

    def telemetry_snapshot(self) -> ApiStreamTelemetrySnapshot:
        """Return compact transport counters and end-state context for one run."""
        ...


def build_api_stream_runtime_policy() -> ApiStreamRuntimePolicy:
    """Return the runtime policy shared by validation and live loading."""
    return ApiStreamRuntimePolicy(
        allowed_schemes=config.API_STREAM_ALLOWED_SCHEMES,
        allowed_hosts=config.API_STREAM_ALLOWED_HOSTS,
        allow_private_hosts=config.API_STREAM_ALLOW_PRIVATE_HOSTS,
        max_reconnect_attempts=config.API_STREAM_MAX_RECONNECT_ATTEMPTS,
        fetch_timeout_sec=config.API_STREAM_FETCH_TIMEOUT_SEC,
        max_fetch_bytes=config.API_STREAM_MAX_FETCH_BYTES,
        max_session_runtime_sec=config.API_STREAM_MAX_SESSION_RUNTIME_SEC,
        max_playlist_refreshes=config.API_STREAM_MAX_PLAYLIST_REFRESHES,
    )


def build_api_stream_http_loader_contract() -> ApiStreamHttpLoaderContract:
    """Return the concrete v1 contract for the HTTP/HLS loader."""
    return ApiStreamHttpLoaderContract(
        returned_slice_kind="analysis_slice",
        chunk_materialization="session_scoped_temp_file",
        accepted_playlist_types=config.API_STREAM_ACCEPTED_PLAYLIST_TYPES,
        master_playlist_policy=config.API_STREAM_MASTER_PLAYLIST_POLICY,
        playlist_poll_interval_sec=config.API_STREAM_POLL_INTERVAL_SEC,
        max_idle_playlist_polls=config.API_STREAM_MAX_IDLE_PLAYLIST_POLLS,
    )


def build_api_stream_temp_file_policy() -> ApiStreamTempFilePolicy:
    """Return the lifecycle contract for temp files created by live loading."""
    return ApiStreamTempFilePolicy(
        temp_root=config.API_STREAM_TEMP_ROOT,
        session_scoped=True,
        cleanup_on_completed=True,
        cleanup_on_cancelled=True,
        cleanup_on_failed=True,
        max_bytes=config.API_STREAM_TEMP_MAX_BYTES,
    )


def _validated_api_stream_input_path(input_path: str) -> str:
    """Return one normalized validated api_stream URL for public contracts."""
    return validate_api_stream_url(input_path)


def build_api_stream_source_contract(input_path: str) -> ApiStreamSourceContract:
    """Normalize one validated live-source input into the shared source contract."""
    return ApiStreamSourceContract(
        kind="api_stream",
        input_path=_validated_api_stream_input_path(input_path),
    )


def build_api_stream_start_session_contract(
    *,
    input_path: str,
    selected_detectors: list[str],
) -> ApiStreamStartSessionContract:
    """Return the backend-side session-start contract for one live source."""
    return ApiStreamStartSessionContract(
        mode="api_stream",
        input_path=_validated_api_stream_input_path(input_path),
        selected_detectors=list(selected_detectors),
    )


def build_api_stream_playback_contract(input_path: str) -> ApiStreamPlaybackContract:
    """Return the current playback contract for one live source."""
    return ApiStreamPlaybackContract(
        source=_validated_api_stream_input_path(input_path)
    )


def _normalize_api_stream_session_id(session_id: str) -> str:
    normalized_session_id = str(session_id).strip()
    if normalized_session_id in {".", ".."} or any(
        separator in normalized_session_id for separator in ("/", "\\")
    ):
        raise ValueError("api_stream temp session directory requires a single safe session_id")
    return normalized_session_id


def build_api_stream_temp_session_dir(session_id: str) -> Path:
    """Return the dedicated temp directory for one live session."""
    normalized_session_id = _normalize_api_stream_session_id(session_id)
    if not normalized_session_id:
        raise ValueError("api_stream temp session directory requires a non-empty session_id")
    return build_api_stream_temp_file_policy().temp_root / normalized_session_id


def cleanup_api_stream_temp_session_dir(session_id: str) -> None:
    """Remove the temp directory for one live session when it exists."""
    session_dir = build_api_stream_temp_session_dir(session_id)
    if session_dir.is_symlink():
        session_dir.unlink(missing_ok=True)
    elif session_dir.exists():
        shutil.rmtree(session_dir, ignore_errors=True)


def _classify_api_stream_source_url(url: str) -> str:
    """Return one coarse source classification for transport observability."""
    lowered = url.lower()
    if lowered.endswith(".m3u8"):
        return "hls_playlist_url"
    if lowered.endswith(".mp4"):
        return "direct_media_file_url"
    return "remote_source_url"


def _normalize_api_stream_current_item(
    current_item: str | None,
    *,
    chunk_index: int,
) -> str:
    """Return a readable stable item name for one live chunk."""
    normalized_current_item = (
        current_item.strip() if isinstance(current_item, str) and current_item.strip() else None
    )
    if normalized_current_item is not None:
        return normalized_current_item
    return f"live-chunk-{chunk_index:06d}"


def build_api_stream_chunk_identity(
    *,
    source: ApiStreamSourceContract,
    chunk_index: int,
    current_item: str | None = None,
) -> ApiStreamChunkIdentity:
    """Return one normalized live-chunk identity."""
    if chunk_index < 0:
        raise ValueError("api_stream chunk_index must be non-negative")

    return ApiStreamChunkIdentity(
        source_group=source.input_path,
        chunk_index=chunk_index,
        current_item=_normalize_api_stream_current_item(
            current_item,
            chunk_index=chunk_index,
        ),
    )


def build_api_stream_analysis_slice(
    *,
    source: ApiStreamSourceContract,
    file_path: Path,
    chunk_index: int,
    current_item: str | None = None,
    window_start_sec: float | None = None,
    window_duration_sec: float | None = None,
) -> AnalysisSlice:
    """Return one normalized analysis slice for a live chunk."""
    identity = build_api_stream_chunk_identity(
        source=source,
        chunk_index=chunk_index,
        current_item=current_item,
    )
    return AnalysisSlice(
        file_path=file_path,
        source_group=identity.source_group,
        source_name=identity.current_item,
        window_index=identity.chunk_index,
        window_start_sec=window_start_sec,
        window_duration_sec=window_duration_sec,
    )


def validate_api_stream_chunk_sequence(
    previous_slice: AnalysisSlice | None,
    next_slice: AnalysisSlice,
) -> None:
    """Raise when a live slice sequence violates current identity rules."""
    if previous_slice is None:
        return
    if next_slice.source_group != previous_slice.source_group:
        raise ValueError("api_stream source_group must remain stable across one live session")
    previous_index = previous_slice.window_index
    next_index = next_slice.window_index
    if previous_index is None or next_index is None:
        raise ValueError("api_stream slices require a monotonic window_index")
    if next_index <= previous_index:
        raise ValueError("api_stream chunk/window indexes must increase monotonically")


def build_api_stream_slice_identity_key(slice_: AnalysisSlice) -> tuple[str, int, str]:
    """Return the de-duplication key for one live slice."""
    if slice_.window_index is None:
        raise ValueError("api_stream slice identity requires window_index")
    return (slice_.source_group, slice_.window_index, slice_.source_name)


def select_api_stream_master_playlist_variant(variant_urls: list[str]) -> str:
    """Return the deterministic v1 choice for a master-playlist variant."""
    normalized_variants = [
        url.strip() for url in variant_urls if isinstance(url, str) and url.strip()
    ]
    if not normalized_variants:
        raise ValueError("api_stream master playlist requires at least one variant URL")
    return normalized_variants[0]
