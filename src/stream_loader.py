"""Transport and loader seams for ``api_stream`` monitoring.

This module now contains both the stable contracts for live-source ingestion
and the first concrete HTTP/HLS loader used by the local-first runtime. The
design goal is still the same as the original seam:

- keep connection, playlist refresh, segment download, and reconnect behavior
  inside the loader boundary
- keep session lifecycle orchestration in ``session_runner``
- keep detector execution in ``processor``
- keep alert-policy decisions in ``alert_rules``

The result is a transport layer that can be exercised with fake loaders,
checked-in HLS fixtures, and real public smoke streams without changing the
meaning of a monitoring session for the rest of the backend.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil
import time
from typing import Callable, Iterator, Literal, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

import config
from analyzer_contract import AnalysisSlice
from logger import format_log_context, get_logger
from session_io import (
    append_api_stream_seen_chunk_key,
    is_session_cancel_requested,
    read_api_stream_seen_chunk_keys,
)
from session_models import SessionStatus
from source_validation import validate_api_stream_url


ApiStreamFailureKind = Literal["temporary_failure", "retryable_failure", "terminal_failure"]
logger = get_logger(__name__)
# The loader reads upstream responses incrementally so cancel requests and byte
# budgets can interrupt long downloads before they consume whole responses.
_API_STREAM_FETCH_READ_CHUNK_BYTES = 64 * 1024
_API_STREAM_USER_AGENT = "election-stream-monitor/1.0"


@dataclass(frozen=True)
class ApiStreamRuntimePolicy:
    """Current transport and trust rules for future live-stream loading."""

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
    """Concrete return and playlist policy for the future HTTP/HLS loader.

    This keeps the first real loader implementation intentionally narrow:

    - it returns normalized ``AnalysisSlice`` values only
    - each yielded slice is backed by one session-scoped temp media file
    - it accepts media playlists directly and may also receive master playlists
    - master playlist selection stays deterministic for the first version
    """

    returned_slice_kind: Literal["analysis_slice"]
    chunk_materialization: Literal["session_scoped_temp_file"]
    accepted_playlist_types: tuple[str, ...]
    master_playlist_policy: Literal["first_variant"]
    playlist_poll_interval_sec: float
    max_idle_playlist_polls: int


@dataclass(frozen=True)
class ApiStreamLocalHttpTestHarnessContract:
    """Plan for the local HTTP integration harness used by real loader tests."""

    server_kind: Literal["local_http"]
    fixture_format: Literal["hls"]
    playlist_entrypoint: str
    serves_fixture_playlists: bool
    serves_fixture_segments: bool
    controllable_failures: tuple[str, ...]


@dataclass(frozen=True)
class ApiStreamDedupPolicy:
    """Current reconnect de-duplication policy for live slices."""

    storage_scope: Literal["loader_and_session"]
    persisted_session_side: Literal[True]
    replayed_chunk_behavior: Literal["skip_before_persistence"]


@dataclass(frozen=True)
class ApiStreamProgressSemantics:
    """Current meaning of progress fields for open-ended live sessions."""

    running_total_count_mode: Literal["latest_known"]
    allow_null_total_count: bool
    allow_zero_before_first_chunk: bool
    frontend_progress_mode: Literal["live_non_terminal"]


@dataclass(frozen=True)
class ApiStreamTempFilePolicy:
    """Lifecycle rules for temp media created by a future live loader."""

    temp_root: Path
    session_scoped: bool
    cleanup_on_completed: bool
    cleanup_on_cancelled: bool
    cleanup_on_failed: bool
    max_bytes: int


@dataclass(frozen=True)
class ApiStreamLoaderExceptionPolicy:
    """Boundary contract between the loader seam and the session runner."""

    skip_inside_loader_failure_kinds: tuple[ApiStreamFailureKind, ...]
    fail_session_immediately_on_terminal_loader_error: bool
    reconnect_owner: Literal["loader"]


@dataclass(frozen=True)
class ApiStreamFailureSemantics:
    """Current live-failure contract for session status and reconnect behavior."""

    temporary_status: SessionStatus
    retryable_status: SessionStatus
    terminal_status: SessionStatus
    max_reconnect_attempts: int
    duplicate_results_allowed: bool
    duplicate_alerts_allowed: bool


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
    """Playback-resolution contract for live sources.

    Live playback remains passthrough-based today: the backend validates the
    remote URL and the frontend plays the same URL directly.
    """

    source: str


@dataclass(frozen=True)
class ApiStreamFailure:
    """Named failure shape reserved for future reconnect and loader behavior."""

    kind: ApiStreamFailureKind
    message: str
    source_name: str | None = None


class ApiStreamLoaderError(RuntimeError):
    """Structured loader failure raised by fake and future real stream loaders."""

    def __init__(self, failure: ApiStreamFailure) -> None:
        super().__init__(failure.message)
        self.failure = failure


@dataclass(frozen=True)
class ApiStreamChunkIdentity:
    """Stable identity for one live chunk/slice across reconnect and persistence.

    `source_group` stays stable for the whole live source. `chunk_index` is the
    monotonic chunk/window number used by session progress, results, and alert
    timing. `current_item` is the readable per-chunk label that later appears
    in progress snapshots and playback alignment.
    """

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

    def close(self) -> None:
        """Release loader resources after iteration finishes."""

    def load_persisted_identity_keys(self) -> set[tuple[str, int, str]]:
        """Return reconnect de-dup keys already persisted for this session."""

    def persist_identity_key(self, key: tuple[str, int, str]) -> None:
        """Persist one accepted reconnect de-dup key for this session."""

    def accepted_slice_count(self) -> int:
        """Return the number of accepted slices discovered so far."""

    def telemetry_snapshot(self) -> ApiStreamTelemetrySnapshot:
        """Return compact transport counters and end-state context for one run."""


class PlaceholderApiStreamLoader:
    """Default loader used until real remote fetching is implemented.

    The placeholder keeps the runtime seam real without pretending to ingest
    remote media yet. Tests can replace this with deterministic fake loaders.
    """

    def __init__(self) -> None:
        self._source: ApiStreamSourceContract | None = None

    def connect(self, source: ApiStreamSourceContract) -> None:
        self._source = source

    def iter_slices(self) -> Iterator[AnalysisSlice]:
        _ = self._source
        return iter(())

    def close(self) -> None:
        self._source = None

    def load_persisted_identity_keys(self) -> set[tuple[str, int, str]]:
        return set()

    def persist_identity_key(self, key: tuple[str, int, str]) -> None:
        _ = key

    def accepted_slice_count(self) -> int:
        return 0

    def telemetry_snapshot(self) -> ApiStreamTelemetrySnapshot:
        return ApiStreamTelemetrySnapshot()


class StaticApiStreamLoader:
    """Small fake loader for tests and deterministic simulated live sessions."""

    def __init__(self, slices: list[AnalysisSlice]) -> None:
        self._slices = list(slices)
        self._connected = False

    def connect(self, source: ApiStreamSourceContract) -> None:
        validate_api_stream_url(source.input_path)
        self._connected = True

    def iter_slices(self) -> Iterator[AnalysisSlice]:
        if not self._connected:
            raise RuntimeError("ApiStreamLoader.iter_slices() called before connect().")
        yield from self._slices

    def close(self) -> None:
        self._connected = False

    def load_persisted_identity_keys(self) -> set[tuple[str, int, str]]:
        return set()

    def persist_identity_key(self, key: tuple[str, int, str]) -> None:
        _ = key

    def accepted_slice_count(self) -> int:
        return len(self._slices)

    def telemetry_snapshot(self) -> ApiStreamTelemetrySnapshot:
        return ApiStreamTelemetrySnapshot(accepted_slice_count=len(self._slices))


class HttpHlsApiStreamLoader:
    """Concrete HTTP/HLS loader for bounded local-first live-stream runs.

    The loader keeps remote concerns inside the stream-loading seam:

    - fetch initial playlist URL
    - detect master vs media playlists
    - poll media playlists for new segments
    - download new segment files into a session-scoped temp directory
    - convert each segment into a normalized ``AnalysisSlice``

    This implementation is intentionally conservative. It is suitable for
    bounded HLS runs, local HTTP integration tests, and real-stream smoke
    checks while the rest of the backend continues to work in terms of
    normalized ``AnalysisSlice`` values.
    """

    def __init__(self, session_id: str) -> None:
        self._session_id = session_id
        self._runtime_policy = build_api_stream_runtime_policy()
        self._http_loader_contract = build_api_stream_http_loader_contract()
        self._source: ApiStreamSourceContract | None = None
        self._media_playlist_url: str | None = None
        self._connected = False
        self._temp_dir = build_api_stream_temp_session_dir(session_id)
        self._persisted_identity_keys: set[tuple[str, int, str]] = set()
        self._closed = False
        self._last_telemetry_snapshot = ApiStreamTelemetrySnapshot()
        self._reset_runtime_state()

    def connect(self, source: ApiStreamSourceContract) -> None:
        validate_api_stream_url(source.input_path)
        cleanup_api_stream_temp_session_dir(self._session_id)
        self._reset_runtime_state()
        self._closed = False
        self._source = source
        self._temp_dir.mkdir(parents=True, exist_ok=True)
        self._persisted_identity_keys = read_api_stream_seen_chunk_keys(self._session_id)
        self._source_url_class = _classify_api_stream_source_url(source.input_path)
        self._session_started_monotonic = time.monotonic()
        media_playlist_url, playlist_text = self._resolve_media_playlist_url(
            source.input_path,
            allow_temporary_malformed=False,
            log_direct_media=True,
        )
        self._media_playlist_url = media_playlist_url
        try:
            self._refresh_playlist_from_text(playlist_text, self._media_playlist_url)
        except ValueError as error:
            raise ApiStreamLoaderError(
                ApiStreamFailure(
                    kind="terminal_failure",
                    message=str(error),
                )
            ) from error
        self._connected = True
        logger.info(
            "Connected api_stream source [%s]",
            self._log_context(
                source_url=source.input_path,
                source_url_class=self._source_url_class,
            ),
        )

    def iter_slices(self) -> Iterator[AnalysisSlice]:
        if not self._connected or self._source is None or self._media_playlist_url is None:
            raise RuntimeError("ApiStreamLoader.iter_slices() called before connect().")
        return _HttpHlsApiStreamIterator(self)

    def close(self) -> None:
        self._last_telemetry_snapshot = self.telemetry_snapshot()
        self._connected = False
        self._source = None
        self._media_playlist_url = None
        self._persisted_identity_keys.clear()
        self._reset_runtime_state()
        self._closed = True

    def load_persisted_identity_keys(self) -> set[tuple[str, int, str]]:
        return set(self._persisted_identity_keys)

    def persist_identity_key(self, key: tuple[str, int, str]) -> None:
        if key in self._persisted_identity_keys:
            return
        append_api_stream_seen_chunk_key(self._session_id, key)
        self._persisted_identity_keys.add(key)

    def accepted_slice_count(self) -> int:
        return len(self._persisted_identity_keys)

    def telemetry_snapshot(self) -> ApiStreamTelemetrySnapshot:
        if self._closed:
            return self._last_telemetry_snapshot
        return ApiStreamTelemetrySnapshot(
            source_url_class=self._source_url_class,
            playlist_refresh_count=self._playlist_refresh_count,
            accepted_slice_count=len(self._persisted_identity_keys),
            skipped_replay_count=self._skipped_replay_count,
            reconnect_attempt_count=self._reconnect_attempt_count,
            reconnect_budget_exhaustion_count=self._reconnect_budget_exhaustion_count,
            terminal_failure_reason=self._terminal_failure_reason,
            stop_reason=self._stop_reason,
        )

    def next_slice(self) -> AnalysisSlice:
        """Return the next available segment slice or stop when the stream ends.

        The iterator keeps three responsibilities local to the loader:

        - draining already-discovered pending segments
        - polling the playlist again when no segment is pending
        - translating loader-local stop conditions into ``StopIteration``

        Retry semantics stay below this layer; ``iter_api_stream_slices`` is
        still responsible for deciding which structured loader failures should
        be skipped, retried, or surfaced to the session runner.
        """
        if self._closed or self._source is None or self._media_playlist_url is None:
            raise StopIteration

        while True:
            self._enforce_session_runtime_limit()
            self._raise_if_cancel_requested()
            if self._pending_segments:
                segment = self._pending_segments[0]
                segment_key = _build_playlist_segment_key(segment)
                try:
                    slice_ = self._materialize_segment_slice(segment)
                except ApiStreamLoaderError as error:
                    if error.failure.kind == "temporary_failure":
                        self._pending_segments.pop(0)
                        self._queued_segment_keys.discard(segment_key)
                        self._emitted_segment_keys.add(segment_key)
                        self._segment_start_offsets.pop(segment_key, None)
                    raise
                self._pending_segments.pop(0)
                self._queued_segment_keys.discard(segment_key)
                self._emitted_segment_keys.add(segment_key)
                self._segment_start_offsets.pop(segment_key, None)
                return slice_

            if self._saw_endlist:
                self._stop_reason = "endlist_reached"
                logger.info(
                    "Stopping api_stream after ENDLIST [%s]",
                    self._log_context(
                        source_url=self._source.input_path,
                        source_url_class=self._source_url_class,
                        playlist_refresh_count=self._playlist_refresh_count,
                        current_item=None,
                    ),
                )
                raise StopIteration

            if self._idle_playlist_polls >= self._http_loader_contract.max_idle_playlist_polls:
                self._stop_reason = "idle_poll_budget_exhausted"
                logger.info(
                    "Stopping idle api_stream polling [%s]",
                    self._log_context(
                        source_url=self._source.input_path,
                        source_url_class=self._source_url_class,
                        idle_polls=self._idle_playlist_polls,
                        current_item=None,
                    ),
                )
                raise StopIteration

            time.sleep(self._current_poll_interval_sec)
            self._raise_if_cancel_requested()
            self._refresh_playlist_from_remote()

    def _refresh_playlist_from_text(self, playlist_text: str, playlist_url: str) -> None:
        """Merge one parsed playlist refresh into the loader's live state.

        The loader tracks queued segments, already-emitted segments, rolling
        start offsets, and window-advance heuristics here so the rest of the
        runtime only sees accepted normalized slices.
        """
        parsed = _parse_media_playlist(playlist_text, playlist_url)
        self._playlist_refresh_count += 1
        self._saw_endlist = parsed.is_endlist
        self._current_poll_interval_sec = _derive_api_stream_poll_interval(
            configured_poll_interval_sec=self._http_loader_contract.playlist_poll_interval_sec,
            target_duration_sec=parsed.target_duration_sec,
        )
        new_segments_discovered = 0
        skipped_replays_this_refresh = 0
        if parsed.segments:
            first_visible_sequence = min(segment.sequence for segment in parsed.segments)
            self._prune_replay_cache(first_visible_sequence)
        if parsed.segments and self._last_seen_max_sequence is not None:
            if first_visible_sequence > self._last_seen_max_sequence + 1:
                logger.info(
                    "api_stream playlist window advanced [%s]",
                    self._log_context(
                        source_url=self._source.input_path if self._source else playlist_url,
                        playlist_refresh_count=self._playlist_refresh_count,
                        missed_segment_count=first_visible_sequence - self._last_seen_max_sequence - 1,
                        resume_from_sequence=first_visible_sequence,
                    ),
                )

        for segment in parsed.segments:
            segment_key = _build_playlist_segment_key(segment)
            if (
                segment_key in self._queued_segment_keys
                or segment_key in self._emitted_segment_keys
            ):
                skipped_replays_this_refresh += 1
                continue
            self._segment_start_offsets[segment_key] = self._next_window_start_sec
            self._next_window_start_sec += max(segment.duration_sec, 0.1)
            self._pending_segments.append(segment)
            self._queued_segment_keys.add(segment_key)
            new_segments_discovered += 1

        self._skipped_replay_count += skipped_replays_this_refresh
        if parsed.segments:
            parsed_max_sequence = max(segment.sequence for segment in parsed.segments)
            if self._last_seen_max_sequence is None:
                self._last_seen_max_sequence = parsed_max_sequence
            else:
                self._last_seen_max_sequence = max(self._last_seen_max_sequence, parsed_max_sequence)

        if new_segments_discovered > 0:
            self._idle_playlist_polls = 0
        elif not self._saw_endlist:
            self._idle_playlist_polls += 1

        logger.info(
            "Refreshed api_stream playlist [%s]",
            self._log_context(
                source_url=self._source.input_path if self._source else playlist_url,
                source_url_class=self._source_url_class,
                playlist_refresh_count=self._playlist_refresh_count,
                new_segment_count=new_segments_discovered,
                skipped_replay_count=skipped_replays_this_refresh,
                skipped_replay_total=self._skipped_replay_count,
                target_duration_sec=parsed.target_duration_sec,
                idle_polls=self._idle_playlist_polls,
            ),
        )

    def _materialize_segment_slice(self, segment: ApiStreamPlaylistSegment) -> AnalysisSlice:
        source = self._source
        if source is None:
            raise StopIteration

        segment_name = Path(urlparse(segment.uri).path).name or f"segment-{segment.sequence:06d}.ts"
        segment_bytes = self._fetch_segment_bytes(segment.uri, segment_name)
        self._raise_if_cancel_requested()
        self._enforce_temp_storage_budget(len(segment_bytes))
        temp_path = self._temp_dir / f"{segment.sequence:06d}-{segment_name}"
        _write_api_stream_temp_file(temp_path, segment_bytes)
        segment_key = _build_playlist_segment_key(segment)

        return build_api_stream_analysis_slice(
            source=source,
            file_path=temp_path,
            chunk_index=segment.sequence,
            current_item=segment_name,
            window_start_sec=round(self._segment_start_offsets.get(segment_key, 0.0), 3),
            window_duration_sec=round(max(segment.duration_sec, 0.1), 3),
        )

    def _fetch_playlist_text_with_retries(self, url: str) -> tuple[str, str]:
        attempts = 0
        while True:
            self._raise_if_cancel_requested()
            try:
                payload, resolved_url = self._fetch_url_bytes(url, include_final_url=True)
                return payload.decode("utf-8"), resolved_url
            except ApiStreamLoaderError as error:
                if error.failure.kind != "retryable_failure":
                    raise
                attempts += 1
                self._reconnect_attempt_count = attempts
                if attempts > self._runtime_policy.max_reconnect_attempts:
                    self._reconnect_budget_exhaustion_count += 1
                    self._terminal_failure_reason = (
                        f"reconnect_budget_exhausted:{error.failure.message}"
                    )
                    raise ApiStreamLoaderError(
                        ApiStreamFailure(
                            kind="terminal_failure",
                            message=f"api_stream reconnect budget exhausted: {error.failure.message}",
                            source_name=error.failure.source_name,
                        )
                    ) from error
                time.sleep(config.API_STREAM_RECONNECT_BACKOFF_SEC)
                self._raise_if_cancel_requested()

    def _refresh_playlist_from_remote(self) -> None:
        media_playlist_url = self._media_playlist_url
        if media_playlist_url is None:
            raise StopIteration
        self._enforce_playlist_refresh_limit()

        refreshed_media_url, playlist_text = self._resolve_media_playlist_url(
            media_playlist_url,
            allow_temporary_malformed=True,
        )
        try:
            self._refresh_playlist_from_text(playlist_text, refreshed_media_url)
        except ValueError as error:
            raise ApiStreamLoaderError(
                ApiStreamFailure(
                    kind="retryable_failure",
                    message=f"api_stream playlist refresh was temporarily malformed: {error}",
                )
            ) from error
        self._media_playlist_url = refreshed_media_url

    def _resolve_media_playlist_url(
        self,
        playlist_url: str,
        *,
        allow_temporary_malformed: bool,
        log_direct_media: bool = False,
    ) -> tuple[str, str]:
        current_url = playlist_url
        followed_master_depth = 0
        while True:
            self._raise_if_cancel_requested()
            playlist_text, resolved_url = self._fetch_playlist_text_with_retries(current_url)
            playlist_kind = _detect_hls_playlist_kind(playlist_text)

            if playlist_kind == "media":
                if followed_master_depth == 0 and log_direct_media:
                    self._source_url_class = "media_playlist_url"
                    logger.info(
                        "Using direct api_stream media playlist [%s]",
                        self._log_context(
                            source_url=resolved_url,
                            source_url_class=self._source_url_class,
                        ),
                    )
                return resolved_url, playlist_text

            if playlist_kind == "master":
                followed_master_depth += 1
                self._source_url_class = "master_playlist_url"
                if followed_master_depth > 3:
                    raise ApiStreamLoaderError(
                        ApiStreamFailure(
                            kind="terminal_failure",
                            message="api_stream master playlist nesting exceeded supported depth",
                        )
                    )
                variant_urls = _parse_master_playlist_variants(playlist_text, current_url)
                variant_urls = _parse_master_playlist_variants(playlist_text, resolved_url)
                selected_variant = select_api_stream_master_playlist_variant(variant_urls)
                self._selected_variant_url = selected_variant
                logger.info(
                    "Selected api_stream variant [%s]",
                    self._log_context(
                        source_url=resolved_url,
                        source_url_class=self._source_url_class,
                        selected_variant=selected_variant,
                        master_depth=followed_master_depth,
                    ),
                )
                current_url = selected_variant
                continue

            failure_kind: ApiStreamFailureKind = (
                "retryable_failure" if allow_temporary_malformed else "terminal_failure"
            )
            raise ApiStreamLoaderError(
                ApiStreamFailure(
                    kind=failure_kind,
                    message="api_stream playlist refresh was temporarily malformed"
                    if allow_temporary_malformed
                    else "Unsupported api_stream playlist/source",
                )
            )

    def _fetch_segment_bytes(self, url: str, segment_name: str) -> bytes:
        try:
            return self._fetch_url_bytes(url)
        except ApiStreamLoaderError as error:
            failure_kind = error.failure.kind
            if failure_kind == "retryable_failure":
                failure_kind = "temporary_failure"
            raise ApiStreamLoaderError(
                ApiStreamFailure(
                    kind=failure_kind,
                    message=error.failure.message,
                    source_name=segment_name,
                )
            ) from error

    def _fetch_url_bytes(
        self,
        url: str,
        *,
        include_final_url: bool = False,
    ) -> bytes | tuple[bytes, str]:
        self._raise_if_cancel_requested()
        request = _build_api_stream_request(url)
        try:
            with urlopen(
                request,
                timeout=self._runtime_policy.fetch_timeout_sec,
            ) as response:
                payload = _read_api_stream_response_bytes(
                    response,
                    max_fetch_bytes=self._runtime_policy.max_fetch_bytes,
                    on_chunk_read=self._raise_if_cancel_requested,
                )
                if include_final_url:
                    resolved_url = response.geturl() if hasattr(response, "geturl") else url
                    return payload, str(resolved_url)
                return payload
        except (TimeoutError, HTTPError, URLError) as error:
            failure = _classify_api_stream_fetch_exception(error)
            if failure.kind == "terminal_failure":
                self._terminal_failure_reason = failure.message
            raise ApiStreamLoaderError(failure) from error

    def _enforce_temp_storage_budget(self, next_file_bytes: int) -> None:
        current_bytes = _count_file_bytes_in_directory(self._temp_dir)
        if current_bytes + next_file_bytes > build_api_stream_temp_file_policy().max_bytes:
            raise ApiStreamLoaderError(
                ApiStreamFailure(
                    kind="terminal_failure",
                    message="api_stream temp storage exceeded max byte budget",
                )
            )

    def _reset_runtime_state(self) -> None:
        self._pending_segments: list[ApiStreamPlaylistSegment] = []
        self._queued_segment_keys: set[tuple[int, str]] = set()
        self._emitted_segment_keys: set[tuple[int, str]] = set()
        self._segment_start_offsets: dict[tuple[int, str], float] = {}
        self._next_window_start_sec = 0.0
        self._saw_endlist = False
        self._idle_playlist_polls = 0
        self._current_poll_interval_sec = self._http_loader_contract.playlist_poll_interval_sec
        self._playlist_refresh_count = 0
        self._skipped_replay_count = 0
        self._reconnect_attempt_count = 0
        self._reconnect_budget_exhaustion_count = 0
        self._terminal_failure_reason = None
        self._stop_reason = None
        self._source_url_class = None
        self._session_started_monotonic = None
        self._last_seen_max_sequence = None
        self._selected_variant_url = None

    def _prune_replay_cache(self, first_visible_sequence: int) -> None:
        self._emitted_segment_keys = {
            key for key in self._emitted_segment_keys if key[0] >= first_visible_sequence
        }

    def _raise_if_cancel_requested(self) -> None:
        if is_session_cancel_requested(self._session_id):
            self._stop_reason = "explicit_cancel"
            logger.info(
                "Stopping api_stream after explicit cancel [%s]",
                self._log_context(
                    source_url=self._source.input_path if self._source else self._media_playlist_url,
                    source_url_class=self._source_url_class,
                    current_item=None,
                ),
            )
            raise StopIteration

    def _enforce_session_runtime_limit(self) -> None:
        started_at = self._session_started_monotonic
        if started_at is None:
            return
        if time.monotonic() - started_at <= self._runtime_policy.max_session_runtime_sec:
            return
        self._terminal_failure_reason = "api_stream session runtime exceeded max duration"
        raise ApiStreamLoaderError(
            ApiStreamFailure(
                kind="terminal_failure",
                message="api_stream session runtime exceeded max duration",
            )
        )

    def _enforce_playlist_refresh_limit(self) -> None:
        if self._playlist_refresh_count < self._runtime_policy.max_playlist_refreshes:
            return
        self._terminal_failure_reason = "api_stream playlist refresh limit exceeded"
        raise ApiStreamLoaderError(
            ApiStreamFailure(
                kind="terminal_failure",
                message="api_stream playlist refresh limit exceeded",
            )
        )

    def _log_context(self, **kwargs: object) -> str:
        return format_log_context(session_id=self._session_id, **kwargs)


@dataclass(frozen=True)
class FakeApiStreamEvent:
    """One scripted in-memory event for fake live-stream tests."""

    kind: Literal[
        "chunk",
        "temporary_failure",
        "retryable_failure",
        "terminal_failure",
        "malformed_chunk",
    ]
    chunk_index: int | None = None
    current_item: str | None = None
    file_path: Path | None = None
    window_start_sec: float | None = None
    window_duration_sec: float | None = None
    message: str | None = None


class FakeApiStreamLoader:
    """Small in-memory scripted loader for live-stream tests.

    The fake loader lets tests model live ingestion behavior while keeping the
    rest of the session pipeline unchanged. It can simulate:

    - clean chunk progression
    - temporary failures that are skipped
    - retryable failures that consume reconnect budget
    - duplicate chunks
    - malformed chunks rejected by identity validation
    - terminal failures that stop the session
    """

    def __init__(self, events: list[FakeApiStreamEvent]) -> None:
        self._events = list(events)
        self._connected = False
        self._source: ApiStreamSourceContract | None = None
        self._accepted_count = 0
        self._source_url_class: str | None = None

    def connect(self, source: ApiStreamSourceContract) -> None:
        validate_api_stream_url(source.input_path)
        self._source = source
        self._source_url_class = _classify_api_stream_source_url(source.input_path)
        self._connected = True

    def iter_slices(self) -> Iterator[AnalysisSlice]:
        if not self._connected or self._source is None:
            raise RuntimeError("ApiStreamLoader.iter_slices() called before connect().")
        return _FakeApiStreamIterator(self._source, self._events)

    def close(self) -> None:
        self._connected = False
        self._source = None

    def load_persisted_identity_keys(self) -> set[tuple[str, int, str]]:
        return set()

    def persist_identity_key(self, key: tuple[str, int, str]) -> None:
        _ = key

    def accepted_slice_count(self) -> int:
        return self._accepted_count

    def telemetry_snapshot(self) -> ApiStreamTelemetrySnapshot:
        return ApiStreamTelemetrySnapshot(
            source_url_class=self._source_url_class,
            accepted_slice_count=self._accepted_count,
        )


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


def build_api_stream_local_http_test_harness_contract() -> ApiStreamLocalHttpTestHarnessContract:
    """Return the contract for the local HTTP fixture harness used by loader tests."""
    return ApiStreamLocalHttpTestHarnessContract(
        server_kind="local_http",
        fixture_format="hls",
        playlist_entrypoint="index.m3u8",
        serves_fixture_playlists=True,
        serves_fixture_segments=True,
        controllable_failures=("timeout", "disconnect", "http_503", "playlist_replay"),
    )


def build_api_stream_dedup_policy() -> ApiStreamDedupPolicy:
    """Return the current reconnect de-duplication policy."""
    return ApiStreamDedupPolicy(
        storage_scope="loader_and_session",
        persisted_session_side=True,
        replayed_chunk_behavior="skip_before_persistence",
    )


def build_api_stream_progress_semantics() -> ApiStreamProgressSemantics:
    """Return the current snapshot semantics for open-ended live progress."""
    return ApiStreamProgressSemantics(
        running_total_count_mode="latest_known",
        allow_null_total_count=False,
        allow_zero_before_first_chunk=True,
        frontend_progress_mode="live_non_terminal",
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


def build_api_stream_loader_exception_policy() -> ApiStreamLoaderExceptionPolicy:
    """Return the current ownership and session-impact rules for loader errors."""
    return ApiStreamLoaderExceptionPolicy(
        skip_inside_loader_failure_kinds=("temporary_failure", "retryable_failure"),
        fail_session_immediately_on_terminal_loader_error=True,
        reconnect_owner="loader",
    )


def build_api_stream_failure_semantics() -> ApiStreamFailureSemantics:
    """Return the current contract for live failures and reconnect behavior."""
    return ApiStreamFailureSemantics(
        temporary_status="running",
        retryable_status="running",
        terminal_status="failed",
        max_reconnect_attempts=config.API_STREAM_MAX_RECONNECT_ATTEMPTS,
        duplicate_results_allowed=False,
        duplicate_alerts_allowed=False,
    )


def build_api_stream_source_contract(input_path: str) -> ApiStreamSourceContract:
    """Normalize one validated live-source input into the shared source contract."""
    return ApiStreamSourceContract(
        kind="api_stream",
        input_path=validate_api_stream_url(input_path),
    )


def build_api_stream_start_session_contract(
    *,
    input_path: str,
    selected_detectors: list[str],
) -> ApiStreamStartSessionContract:
    """Return the backend-side session-start contract for one live source."""
    return ApiStreamStartSessionContract(
        mode="api_stream",
        input_path=validate_api_stream_url(input_path),
        selected_detectors=list(selected_detectors),
    )


def build_api_stream_playback_contract(input_path: str) -> ApiStreamPlaybackContract:
    """Return the current playback contract for one live source."""
    return ApiStreamPlaybackContract(source=validate_api_stream_url(input_path))


def build_api_stream_temp_session_dir(session_id: str) -> Path:
    """Return the dedicated temp directory for one live session.

    Future HTTP/HLS loading should materialize fetched segments in a
    session-scoped subdirectory so cleanup can happen on completion, cancel,
    or failure without affecting neighboring sessions.
    """
    normalized_session_id = session_id.strip()
    if not normalized_session_id:
        raise ValueError("api_stream temp session directory requires a non-empty session_id")
    return build_api_stream_temp_file_policy().temp_root / normalized_session_id


def cleanup_api_stream_temp_session_dir(session_id: str) -> None:
    """Remove the temp directory for one live session when it exists."""
    session_dir = build_api_stream_temp_session_dir(session_id)
    if session_dir.exists():
        shutil.rmtree(session_dir, ignore_errors=True)


def _build_api_stream_request(url: str) -> Request:
    """Return the normalized outbound request for one upstream fetch.

    Keeping request creation in one helper makes it easier to evolve headers
    and request policy later without duplicating that logic across playlist and
    segment fetches.
    """
    return Request(url, headers={"User-Agent": _API_STREAM_USER_AGENT})


def _read_api_stream_response_bytes(
    response: object,
    *,
    max_fetch_bytes: int,
    on_chunk_read: Callable[[], None],
) -> bytes:
    """Read one upstream response body while enforcing byte and cancel budgets.

    The loader intentionally performs chunked reads rather than ``read()``
    once so long-running or stalled upstream responses still respect explicit
    cancel requests and the configured maximum fetch size.
    """
    chunks: list[bytes] = []
    total_bytes = 0
    while True:
        on_chunk_read()
        chunk = response.read(_API_STREAM_FETCH_READ_CHUNK_BYTES)
        if not chunk:
            break
        total_bytes += len(chunk)
        if total_bytes > max_fetch_bytes:
            raise ApiStreamLoaderError(
                ApiStreamFailure(
                    kind="terminal_failure",
                    message="api_stream fetch exceeded max byte budget",
                )
            )
        chunks.append(chunk)
    return b"".join(chunks)


def _classify_api_stream_fetch_exception(
    error: TimeoutError | HTTPError | URLError,
) -> ApiStreamFailure:
    """Map low-level transport exceptions into loader-facing failure semantics.

    This keeps the policy boundary explicit: transport specifics stay local to
    the loader, while the higher-level session iterator consumes only named
    ``ApiStreamFailure`` values.
    """
    if isinstance(error, TimeoutError):
        return ApiStreamFailure(
            kind="retryable_failure",
            message="api_stream fetch timed out",
        )
    if isinstance(error, HTTPError):
        failure_kind: ApiStreamFailureKind = (
            "retryable_failure" if error.code in {408, 429, 500, 502, 503, 504}
            else "terminal_failure"
        )
        return ApiStreamFailure(
            kind=failure_kind,
            message=f"api_stream upstream returned HTTP {error.code}",
        )
    return ApiStreamFailure(
        kind="retryable_failure",
        message=f"api_stream upstream connection failed: {error.reason}",
    )


def _write_api_stream_temp_file(temp_path: Path, payload: bytes) -> None:
    """Atomically materialize one fetched segment into the session temp directory.

    Temporary ``.part`` files make cancellation and crashes less likely to
    leave half-written media that could later be mistaken for a valid segment.
    """
    partial_path = temp_path.with_suffix(f"{temp_path.suffix}.part")
    try:
        if partial_path.exists():
            partial_path.unlink()
        if temp_path.exists():
            temp_path.unlink()
        partial_path.write_bytes(payload)
        partial_path.replace(temp_path)
    except OSError:
        partial_path.unlink(missing_ok=True)
        temp_path.unlink(missing_ok=True)
        raise


def _count_file_bytes_in_directory(directory: Path) -> int:
    """Return the current byte footprint of regular files in one temp directory."""
    return sum(candidate.stat().st_size for candidate in directory.glob("*") if candidate.is_file())


def _classify_api_stream_source_url(url: str) -> str:
    """Return one coarse source classification for transport observability."""
    lowered = url.lower()
    if lowered.endswith(".m3u8"):
        return "hls_playlist_url"
    if lowered.endswith(".mp4"):
        return "direct_media_file_url"
    return "remote_source_url"


def build_api_stream_source_group(source: ApiStreamSourceContract) -> str:
    """Return the stable source-group identity for one live source.

    Today this is simply the validated remote URL. Future loaders may derive a
    different stable identifier, but it should remain constant for the whole
    session so rolling rule state and de-duplication stay consistent.
    """
    return source.input_path


def build_api_stream_chunk_identity(
    *,
    source: ApiStreamSourceContract,
    chunk_index: int,
    current_item: str | None = None,
) -> ApiStreamChunkIdentity:
    """Return one normalized live-chunk identity.

    The current-item label is intentionally readable and deterministic. If the
    loader cannot provide a richer upstream name yet, the fallback naming keeps
    progress snapshots and result rows stable.
    """
    if chunk_index < 0:
        raise ValueError("api_stream chunk_index must be non-negative")

    normalized_current_item = (
        current_item.strip() if isinstance(current_item, str) and current_item.strip() else None
    )
    if normalized_current_item is None:
        normalized_current_item = f"live-chunk-{chunk_index:06d}"

    return ApiStreamChunkIdentity(
        source_group=build_api_stream_source_group(source),
        chunk_index=chunk_index,
        current_item=normalized_current_item,
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


def iter_api_stream_slices(
    loader: ApiStreamLoader,
    source: ApiStreamSourceContract,
) -> Iterator[AnalysisSlice]:
    """Yield validated live slices while applying current failure semantics.

    This helper keeps ingestion-specific concerns in one place:

    - temporary failures are skipped
    - retryable failures consume reconnect budget and are skipped while budget remains
    - terminal failures stop collection and surface as errors
    - malformed or replayed chunks are skipped instead of entering persistence

    The rest of the backend still sees normal `AnalysisSlice` objects, so
    session snapshots, results, and alerts keep the same meaning as other
    input modes while `api_stream` can now be consumed incrementally.
    """
    semantics = build_api_stream_failure_semantics()
    _ = build_api_stream_dedup_policy()
    reconnect_attempts = 0
    previous_slice: AnalysisSlice | None = None
    seen_identity_keys: set[tuple[str, int, str]] = set()
    session_id = getattr(loader, "_session_id", None)

    logger.info(
        "Collecting api_stream slices [%s]",
        format_log_context(
            session_id=session_id,
            source_url=source.input_path,
            allowed_schemes=",".join(build_api_stream_runtime_policy().allowed_schemes),
        ),
    )
    try:
        loader.connect(source)
    except ApiStreamLoaderError as error:
        failure = error.failure
        logger.error(
            "Terminal api_stream failure [%s]",
            format_log_context(
                session_id=session_id,
                source_url=source.input_path,
                current_item=failure.source_name,
                failure_kind=failure.kind,
            ),
        )
        raise ValueError(failure.message) from error
    seen_identity_keys = loader.load_persisted_identity_keys()
    try:
        iterator = loader.iter_slices()
        while True:
            try:
                next_slice = next(iterator)
            except StopIteration:
                break
            except ApiStreamLoaderError as error:
                failure = error.failure
                if failure.kind == "temporary_failure":
                    logger.warning(
                        "Skipping temporary api_stream failure [%s]",
                        format_log_context(
                            session_id=session_id,
                            source_url=source.input_path,
                            current_item=failure.source_name,
                            failure_kind=failure.kind,
                        ),
                    )
                    continue
                if failure.kind == "retryable_failure":
                    reconnect_attempts += 1
                    telemetry = loader.telemetry_snapshot()
                    logger.warning(
                        "Retryable api_stream failure [%s]",
                        format_log_context(
                            session_id=session_id,
                            source_url=source.input_path,
                            source_url_class=telemetry.source_url_class,
                            current_item=failure.source_name,
                            failure_kind=failure.kind,
                            reconnect_attempt=reconnect_attempts,
                            reconnect_budget=semantics.max_reconnect_attempts,
                        ),
                    )
                    if reconnect_attempts <= semantics.max_reconnect_attempts:
                        continue
                    logger.error(
                        "api_stream reconnect budget exhausted [%s]",
                        format_log_context(
                            session_id=session_id,
                            source_url=source.input_path,
                            source_url_class=telemetry.source_url_class,
                            current_item=failure.source_name,
                            reconnect_attempt=reconnect_attempts,
                            reconnect_budget=semantics.max_reconnect_attempts,
                            reconnect_budget_exhaustion_count=
                                telemetry.reconnect_budget_exhaustion_count or 1,
                            failure_reason=failure.message,
                        ),
                    )
                    raise ValueError(
                        f"api_stream reconnect budget exhausted: {failure.message}"
                    ) from error
                logger.error(
                    "Terminal api_stream failure [%s]",
                    format_log_context(
                        session_id=session_id,
                        source_url=source.input_path,
                        source_url_class=loader.telemetry_snapshot().source_url_class,
                        current_item=failure.source_name,
                        failure_kind=failure.kind,
                        failure_reason=failure.message,
                    ),
                )
                raise ValueError(failure.message) from error

            try:
                validate_api_stream_chunk_sequence(previous_slice, next_slice)
                identity_key = build_api_stream_slice_identity_key(next_slice)
            except ValueError as validation_error:
                _cleanup_rejected_api_stream_slice(next_slice)
                logger.warning(
                    "Skipping invalid api_stream slice [%s]",
                    format_log_context(
                        session_id=session_id,
                        source_group=next_slice.source_group,
                        current_item=next_slice.source_name,
                        chunk_index=next_slice.window_index,
                        details=str(validation_error),
                    ),
                )
                continue

            if identity_key in seen_identity_keys:
                _cleanup_rejected_api_stream_slice(next_slice)
                logger.warning(
                    "Skipping replayed api_stream slice [%s]",
                    format_log_context(
                        session_id=session_id,
                        source_group=next_slice.source_group,
                        current_item=next_slice.source_name,
                        chunk_index=next_slice.window_index,
                    ),
                )
                continue

            logger.info(
                "Accepted api_stream slice [%s]",
                format_log_context(
                    session_id=session_id,
                    source_group=next_slice.source_group,
                    current_item=next_slice.source_name,
                    chunk_index=next_slice.window_index,
                    window_start_sec=next_slice.window_start_sec,
                    processed_chunk_count=len(seen_identity_keys) + 1,
                ),
            )
            loader.persist_identity_key(identity_key)
            seen_identity_keys.add(identity_key)
            previous_slice = next_slice
            yield next_slice
    finally:
        loader.close()


def collect_api_stream_slices(
    loader: ApiStreamLoader,
    source: ApiStreamSourceContract,
) -> list[AnalysisSlice]:
    """Compatibility helper that materializes the live slice iterator into a list."""
    return list(iter_api_stream_slices(loader, source))


def _cleanup_rejected_api_stream_slice(slice_: AnalysisSlice) -> None:
    """Delete temp media for slices discarded before they reach session processing."""
    try:
        if slice_.file_path.exists():
            slice_.file_path.unlink()
    except OSError as error:
        logger.warning(
            "Failed to delete rejected api_stream temp file [%s]",
            format_log_context(
                source_group=slice_.source_group,
                current_item=slice_.source_name,
                chunk_index=slice_.window_index,
                error=str(error),
            ),
        )


def validate_api_stream_chunk_sequence(
    previous_slice: AnalysisSlice | None,
    next_slice: AnalysisSlice,
) -> None:
    """Raise when a live slice sequence violates current identity rules.

    This protects the expected loader contract before real reconnect logic is
    implemented: source-group identity must stay stable and chunk indexes must
    move forward monotonically.
    """
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
    """Return the de-duplication key for one live slice.

    Future reconnect logic should use this key to avoid persisting duplicate
    results or alerts when the upstream replays already-seen chunks.
    """
    if slice_.window_index is None:
        raise ValueError("api_stream slice identity requires window_index")
    return (slice_.source_group, slice_.window_index, slice_.source_name)


def select_api_stream_master_playlist_variant(variant_urls: list[str]) -> str:
    """Return the deterministic v1 choice for a master-playlist variant.

    The first version of the real HTTP/HLS loader should stay simple and
    predictable: if a validated source resolves to a master playlist, the
    loader selects the first listed variant instead of applying a bitrate or
    resolution heuristic.
    """
    normalized_variants = [url.strip() for url in variant_urls if isinstance(url, str) and url.strip()]
    if not normalized_variants:
        raise ValueError("api_stream master playlist requires at least one variant URL")
    return normalized_variants[0]


def create_api_stream_loader(session_id: str | None = None) -> ApiStreamLoader:
    """Return the current default live-stream loader implementation."""
    if session_id:
        return HttpHlsApiStreamLoader(session_id=session_id)
    return PlaceholderApiStreamLoader()


def _detect_hls_playlist_kind(playlist_text: str) -> Literal["master", "media", "unknown"]:
    if "#EXTM3U" not in playlist_text:
        return "unknown"
    if "#EXT-X-STREAM-INF" in playlist_text:
        return "master"
    if "#EXTINF" in playlist_text or "#EXT-X-TARGETDURATION" in playlist_text:
        return "media"
    return "unknown"


def _parse_master_playlist_variants(playlist_text: str, base_url: str) -> list[str]:
    variants: list[str] = []
    expect_uri = False
    for raw_line in playlist_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("#EXT-X-STREAM-INF"):
            expect_uri = True
            continue
        if line.startswith("#"):
            continue
        if expect_uri:
            variants.append(urljoin(base_url, line))
            expect_uri = False
    return variants


def _parse_media_playlist(
    playlist_text: str,
    base_url: str,
) -> ApiStreamMediaPlaylistSnapshot:
    if "#EXTM3U" not in playlist_text:
        raise ValueError("api_stream media playlist is missing EXTM3U header")

    media_sequence = 0
    target_duration_sec: float | None = None
    current_duration: float | None = None
    next_sequence_offset = 0
    is_endlist = False
    segments: list[ApiStreamPlaylistSegment] = []

    for raw_line in playlist_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("#EXT-X-MEDIA-SEQUENCE:"):
            value = line.split(":", 1)[1].strip()
            try:
                media_sequence = int(value or 0)
            except ValueError as error:
                raise ValueError("api_stream media playlist has invalid MEDIA-SEQUENCE") from error
            next_sequence_offset = 0
            continue
        if line.startswith("#EXT-X-TARGETDURATION:"):
            value = line.split(":", 1)[1].strip()
            try:
                target_duration_sec = float(value or 0.0)
            except ValueError as error:
                raise ValueError("api_stream media playlist has invalid TARGETDURATION") from error
            continue
        if line.startswith("#EXTINF:"):
            value = line.split(":", 1)[1].split(",", 1)[0].strip()
            try:
                current_duration = float(value or 0.0)
            except ValueError as error:
                raise ValueError("api_stream media playlist has invalid EXTINF duration") from error
            continue
        if line == "#EXT-X-ENDLIST":
            is_endlist = True
            continue
        if line.startswith("#"):
            continue

        duration_sec = current_duration if current_duration is not None else 1.0
        segments.append(
            ApiStreamPlaylistSegment(
                sequence=media_sequence + next_sequence_offset,
                uri=urljoin(base_url, line),
                duration_sec=max(duration_sec, 0.1),
            )
        )
        next_sequence_offset += 1
        current_duration = None

    return ApiStreamMediaPlaylistSnapshot(
        segments=segments,
        is_endlist=is_endlist,
        target_duration_sec=target_duration_sec if target_duration_sec and target_duration_sec > 0 else None,
    )


def _build_playlist_segment_key(segment: ApiStreamPlaylistSegment) -> tuple[int, str]:
    return (segment.sequence, Path(urlparse(segment.uri).path).name)


def _derive_api_stream_poll_interval(
    *,
    configured_poll_interval_sec: float,
    target_duration_sec: float | None,
) -> float:
    """Return the next playlist-poll delay while tolerating target-duration drift.

    The current local-first live runtime treats the configured poll interval as
    an upper bound. When the playlist advertises a shorter target duration, the
    loader follows that shorter cadence so shorter live segments are discovered
    promptly. Longer target durations do not slow polling beyond the configured
    ceiling.
    """
    configured = max(configured_poll_interval_sec, 0.0)
    if target_duration_sec is None:
        return configured
    safe_target_duration = max(target_duration_sec, 0.1)
    return min(configured, safe_target_duration)


def _map_fake_event_to_failure_kind(
    kind: Literal["temporary_failure", "retryable_failure", "terminal_failure"],
) -> ApiStreamFailureKind:
    return kind


class _FakeApiStreamIterator:
    """Iterator that can raise on one step and continue on the next.

    A plain generator would terminate permanently after raising an exception.
    The scripted fake loader needs resumable failures so tests can model
    temporary outages and retryable reconnect attempts more realistically.
    """

    def __init__(
        self,
        source: ApiStreamSourceContract,
        events: list[FakeApiStreamEvent],
    ) -> None:
        self._source = source
        self._events = list(events)
        self._index = 0

    def __iter__(self) -> "_FakeApiStreamIterator":
        return self

    def __next__(self) -> AnalysisSlice:
        if self._index >= len(self._events):
            raise StopIteration

        event = self._events[self._index]
        self._index += 1

        if event.kind == "chunk":
            return _build_fake_chunk_slice(self._source, event)
        if event.kind == "malformed_chunk":
            return _build_fake_malformed_slice(self._source, event)

        failure_kind = _map_fake_event_to_failure_kind(event.kind)
        raise ApiStreamLoaderError(
            ApiStreamFailure(
                kind=failure_kind,
                message=event.message or failure_kind.replace("_", " "),
                source_name=event.current_item,
            )
        )


class _HttpHlsApiStreamIterator:
    """Iterator wrapper that lets the concrete HTTP/HLS loader resumably fail."""

    def __init__(self, loader: HttpHlsApiStreamLoader) -> None:
        self._loader = loader

    def __iter__(self) -> "_HttpHlsApiStreamIterator":
        return self

    def __next__(self) -> AnalysisSlice:
        return self._loader.next_slice()


def _build_fake_chunk_slice(
    source: ApiStreamSourceContract,
    event: FakeApiStreamEvent,
) -> AnalysisSlice:
    if event.chunk_index is None:
        raise ValueError("Fake chunk event requires chunk_index")
    file_path = event.file_path or Path(f"/tmp/live-chunk-{event.chunk_index:06d}.ts")
    return build_api_stream_analysis_slice(
        source=source,
        file_path=file_path,
        chunk_index=event.chunk_index,
        current_item=event.current_item,
        window_start_sec=event.window_start_sec,
        window_duration_sec=event.window_duration_sec,
    )


def _build_fake_malformed_slice(
    source: ApiStreamSourceContract,
    event: FakeApiStreamEvent,
) -> AnalysisSlice:
    """Return one intentionally invalid slice for malformed-loader tests."""
    if event.chunk_index is None:
        raise ValueError("Fake malformed chunk event requires chunk_index")
    file_path = event.file_path or Path(f"/tmp/live-chunk-{event.chunk_index:06d}.ts")
    return AnalysisSlice(
        file_path=file_path,
        source_group="malformed-source-group",
        source_name=event.current_item or f"malformed-{event.chunk_index}",
        window_index=event.chunk_index - 1,
        window_start_sec=event.window_start_sec,
        window_duration_sec=event.window_duration_sec,
    )
