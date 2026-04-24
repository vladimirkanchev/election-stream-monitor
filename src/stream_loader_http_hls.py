"""Concrete HTTP/HLS api_stream loader implementation.

The loader keeps one persistent shell object per session and resets the mutable
live-run state on each connect/close cycle. Grouping that state in one internal
dataclass makes the bounded live loop easier to follow than scattering many
peer attributes across the class.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import time
from typing import Iterator, Literal
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

from analyzer_contract import AnalysisSlice
import config
from logger import format_log_context, get_logger
from session_io import (
    append_api_stream_seen_chunk_key,
    is_session_cancel_requested,
    read_api_stream_seen_chunk_keys,
)
from stream_loader_contracts import (
    ApiStreamFailure,
    ApiStreamFailureKind,
    ApiStreamHttpLoaderContract,
    ApiStreamLoaderError,
    ApiStreamMediaPlaylistSnapshot,
    ApiStreamPlaylistSegment,
    ApiStreamSourceContract,
    ApiStreamTelemetrySnapshot,
    _api_stream_loader_error,
    _build_api_stream_failure,
    _classify_api_stream_source_url,
    build_api_stream_analysis_slice,
    build_api_stream_http_loader_contract,
    build_api_stream_runtime_policy,
    build_api_stream_temp_file_policy,
    build_api_stream_temp_session_dir,
    cleanup_api_stream_temp_session_dir,
    select_api_stream_master_playlist_variant,
)
from source_validation import validate_api_stream_url


logger = get_logger(__name__)
_API_STREAM_FETCH_READ_CHUNK_BYTES = 64 * 1024
_API_STREAM_USER_AGENT = "election-stream-monitor/1.0"
_API_STREAM_MASTER_PLAYLIST_MAX_DEPTH = 3
_API_STREAM_TEMPORARY_MALFORMED_PLAYLIST_MESSAGE = (
    "api_stream playlist refresh was temporarily malformed"
)
_API_STREAM_UNSUPPORTED_PLAYLIST_MESSAGE = "Unsupported api_stream playlist/source"


@dataclass
class _HttpHlsRuntimeState:
    """Mutable live-run state for one connected HTTP/HLS loader session."""

    pending_segments: list[ApiStreamPlaylistSegment] = field(default_factory=list)
    queued_segment_keys: set[tuple[int, str]] = field(default_factory=set)
    emitted_segment_keys: set[tuple[int, str]] = field(default_factory=set)
    segment_start_offsets: dict[tuple[int, str], float] = field(default_factory=dict)
    next_window_start_sec: float = 0.0
    saw_endlist: bool = False
    idle_playlist_polls: int = 0
    current_poll_interval_sec: float = 0.0
    playlist_refresh_count: int = 0
    skipped_replay_count: int = 0
    reconnect_attempt_count: int = 0
    reconnect_budget_exhaustion_count: int = 0
    terminal_failure_reason: str | None = None
    stop_reason: str | None = None
    source_url_class: str | None = None
    session_started_monotonic: float | None = None
    last_seen_max_sequence: int | None = None


def _build_http_hls_runtime_state(
    *,
    poll_interval_sec: float,
) -> _HttpHlsRuntimeState:
    """Return a clean mutable state container for one live loader run."""
    return _HttpHlsRuntimeState(current_poll_interval_sec=poll_interval_sec)


class HttpHlsApiStreamLoader:
    """Concrete HTTP/HLS loader for bounded local-first live-stream runs."""

    def __init__(self, session_id: str) -> None:
        self._session_id = session_id
        self._runtime_policy = build_api_stream_runtime_policy()
        self._http_loader_contract: ApiStreamHttpLoaderContract = (
            build_api_stream_http_loader_contract()
        )
        self._source: ApiStreamSourceContract | None = None
        self._media_playlist_url: str | None = None
        self._connected = False
        self._temp_dir = build_api_stream_temp_session_dir(session_id)
        self._persisted_identity_keys: set[tuple[str, int, str]] = set()
        self._closed = False
        self._last_telemetry_snapshot = ApiStreamTelemetrySnapshot()
        self._state = _build_http_hls_runtime_state(
            poll_interval_sec=self._http_loader_contract.playlist_poll_interval_sec,
        )
        self._reset_runtime_state()

    def connect(self, source: ApiStreamSourceContract) -> None:
        validate_api_stream_url(source.input_path)
        cleanup_api_stream_temp_session_dir(self._session_id)
        self._reset_runtime_state()
        self._closed = False
        self._source = source
        self._temp_dir.mkdir(parents=True, exist_ok=True)
        self._persisted_identity_keys = read_api_stream_seen_chunk_keys(self._session_id)
        self._state.source_url_class = _classify_api_stream_source_url(source.input_path)
        self._state.session_started_monotonic = time.monotonic()
        media_playlist_url, playlist_text = self._resolve_media_playlist_url(
            source.input_path,
            allow_temporary_malformed=False,
            log_direct_media=True,
        )
        self._media_playlist_url = media_playlist_url
        self._refresh_playlist_from_text_or_raise(
            playlist_text,
            self._media_playlist_url,
            malformed_failure_kind="terminal_failure",
        )
        self._connected = True
        logger.info(
            "Connected api_stream source [%s]",
            self._log_context(
                source_url=source.input_path,
                source_url_class=self._state.source_url_class,
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
            source_url_class=self._state.source_url_class,
            playlist_refresh_count=self._state.playlist_refresh_count,
            accepted_slice_count=len(self._persisted_identity_keys),
            skipped_replay_count=self._state.skipped_replay_count,
            reconnect_attempt_count=self._state.reconnect_attempt_count,
            reconnect_budget_exhaustion_count=self._state.reconnect_budget_exhaustion_count,
            terminal_failure_reason=self._state.terminal_failure_reason,
            stop_reason=self._state.stop_reason,
        )

    def next_slice(self) -> AnalysisSlice:
        """Return the next available segment slice or stop when the stream ends."""
        if self._closed or self._source is None or self._media_playlist_url is None:
            raise StopIteration

        # One iteration step either materializes the next queued segment or
        # advances the live playlist until new work appears or the bounded run ends.
        while True:
            self._enforce_session_runtime_limit()
            self._raise_if_cancel_requested()
            if self._state.pending_segments:
                segment = self._state.pending_segments[0]
                segment_key = _build_playlist_segment_key(segment)
                try:
                    slice_ = self._materialize_segment_slice(segment)
                except ApiStreamLoaderError as error:
                    if error.failure.kind == "temporary_failure":
                        self._finalize_pending_segment(segment_key, mark_emitted=True)
                    raise
                self._finalize_pending_segment(segment_key, mark_emitted=True)
                return slice_

            if self._state.saw_endlist:
                self._stop_iteration(
                    reason="endlist_reached",
                    message="Stopping api_stream after ENDLIST [%s]",
                    source_url=self._source.input_path,
                    source_url_class=self._state.source_url_class,
                    playlist_refresh_count=self._state.playlist_refresh_count,
                    current_item=None,
                )

            if (
                self._state.idle_playlist_polls
                >= self._http_loader_contract.max_idle_playlist_polls
            ):
                self._stop_iteration(
                    reason="idle_poll_budget_exhausted",
                    message="Stopping idle api_stream polling [%s]",
                    source_url=self._source.input_path,
                    source_url_class=self._state.source_url_class,
                    idle_polls=self._state.idle_playlist_polls,
                    current_item=None,
                )

            time.sleep(self._state.current_poll_interval_sec)
            self._raise_if_cancel_requested()
            self._refresh_playlist_from_remote()

    def _refresh_playlist_from_text(self, playlist_text: str, playlist_url: str) -> None:
        """Merge one parsed playlist refresh into the loader's live state."""
        parsed = _parse_media_playlist(playlist_text, playlist_url)
        self._state.playlist_refresh_count += 1
        self._state.saw_endlist = parsed.is_endlist
        self._state.current_poll_interval_sec = _derive_api_stream_poll_interval(
            configured_poll_interval_sec=self._http_loader_contract.playlist_poll_interval_sec,
            target_duration_sec=parsed.target_duration_sec,
        )
        new_segments_discovered = 0
        skipped_replays_this_refresh = 0
        if parsed.segments:
            first_visible_sequence = min(segment.sequence for segment in parsed.segments)
            self._prune_replay_cache(first_visible_sequence)
            if (
                self._state.last_seen_max_sequence is not None
                and first_visible_sequence > self._state.last_seen_max_sequence + 1
            ):
                logger.info(
                    "api_stream playlist window advanced [%s]",
                    self._log_context(
                        source_url=self._source.input_path if self._source else playlist_url,
                        playlist_refresh_count=self._state.playlist_refresh_count,
                        missed_segment_count=
                            first_visible_sequence - self._state.last_seen_max_sequence - 1,
                        resume_from_sequence=first_visible_sequence,
                    ),
                )

        for segment in parsed.segments:
            segment_key = _build_playlist_segment_key(segment)
            if (
                segment_key in self._state.queued_segment_keys
                or segment_key in self._state.emitted_segment_keys
            ):
                skipped_replays_this_refresh += 1
                continue
            self._state.segment_start_offsets[segment_key] = self._state.next_window_start_sec
            self._state.next_window_start_sec += max(segment.duration_sec, 0.1)
            self._state.pending_segments.append(segment)
            self._state.queued_segment_keys.add(segment_key)
            new_segments_discovered += 1

        self._state.skipped_replay_count += skipped_replays_this_refresh
        if parsed.segments:
            parsed_max_sequence = max(segment.sequence for segment in parsed.segments)
            if self._state.last_seen_max_sequence is None:
                self._state.last_seen_max_sequence = parsed_max_sequence
            else:
                self._state.last_seen_max_sequence = max(
                    self._state.last_seen_max_sequence,
                    parsed_max_sequence,
                )

        if new_segments_discovered > 0:
            self._state.idle_playlist_polls = 0
        elif not self._state.saw_endlist:
            self._state.idle_playlist_polls += 1

        logger.info(
            "Refreshed api_stream playlist [%s]",
            self._log_context(
                source_url=self._source.input_path if self._source else playlist_url,
                source_url_class=self._state.source_url_class,
                playlist_refresh_count=self._state.playlist_refresh_count,
                new_segment_count=new_segments_discovered,
                skipped_replay_count=skipped_replays_this_refresh,
                skipped_replay_total=self._state.skipped_replay_count,
                target_duration_sec=parsed.target_duration_sec,
                idle_polls=self._state.idle_playlist_polls,
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
            window_start_sec=round(self._state.segment_start_offsets.get(segment_key, 0.0), 3),
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
                self._state.reconnect_attempt_count = attempts
                if attempts > self._runtime_policy.max_reconnect_attempts:
                    self._state.reconnect_budget_exhaustion_count += 1
                    self._state.terminal_failure_reason = (
                        f"reconnect_budget_exhausted:{error.failure.message}"
                    )
                    raise _api_stream_loader_error(
                        "terminal_failure",
                        f"api_stream reconnect budget exhausted: {error.failure.message}",
                        source_name=error.failure.source_name,
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
        self._refresh_playlist_from_text_or_raise(
            playlist_text,
            refreshed_media_url,
            malformed_failure_kind="retryable_failure",
            malformed_message_prefix=_API_STREAM_TEMPORARY_MALFORMED_PLAYLIST_MESSAGE,
        )
        self._media_playlist_url = refreshed_media_url

    def _refresh_playlist_from_text_or_raise(
        self,
        playlist_text: str,
        playlist_url: str,
        *,
        malformed_failure_kind: ApiStreamFailureKind,
        malformed_message_prefix: str | None = None,
    ) -> None:
        """Refresh loader state or raise one normalized malformed-playlist error."""
        try:
            self._refresh_playlist_from_text(playlist_text, playlist_url)
        except ValueError as error:
            message = str(error)
            if malformed_message_prefix is not None:
                message = f"{malformed_message_prefix}: {error}"
            raise _api_stream_loader_error(
                malformed_failure_kind,
                message,
            ) from error

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
                self._log_direct_media_playlist_selection(
                    resolved_url,
                    followed_master_depth=followed_master_depth,
                    log_direct_media=log_direct_media,
                )
                return resolved_url, playlist_text

            if playlist_kind == "master":
                followed_master_depth += 1
                current_url = self._select_master_playlist_variant_url(
                    playlist_text,
                    resolved_url,
                    master_depth=followed_master_depth,
                )
                continue

            raise _api_stream_loader_error(
                "retryable_failure" if allow_temporary_malformed else "terminal_failure",
                _API_STREAM_TEMPORARY_MALFORMED_PLAYLIST_MESSAGE
                if allow_temporary_malformed
                else _API_STREAM_UNSUPPORTED_PLAYLIST_MESSAGE,
            )

    def _log_direct_media_playlist_selection(
        self,
        resolved_url: str,
        *,
        followed_master_depth: int,
        log_direct_media: bool,
    ) -> None:
        if followed_master_depth != 0 or not log_direct_media:
            return
        self._state.source_url_class = "media_playlist_url"
        logger.info(
            "Using direct api_stream media playlist [%s]",
            self._log_context(
                source_url=resolved_url,
                source_url_class=self._state.source_url_class,
            ),
        )

    def _select_master_playlist_variant_url(
        self,
        playlist_text: str,
        resolved_url: str,
        *,
        master_depth: int,
    ) -> str:
        self._state.source_url_class = "master_playlist_url"
        if master_depth > _API_STREAM_MASTER_PLAYLIST_MAX_DEPTH:
            raise _api_stream_loader_error(
                "terminal_failure",
                "api_stream master playlist nesting exceeded supported depth",
            )
        variant_urls = _parse_master_playlist_variants(playlist_text, resolved_url)
        selected_variant = select_api_stream_master_playlist_variant(variant_urls)
        logger.info(
            "Selected api_stream variant [%s]",
            self._log_context(
                source_url=resolved_url,
                source_url_class=self._state.source_url_class,
                selected_variant=selected_variant,
                master_depth=master_depth,
            ),
        )
        return selected_variant

    def _fetch_segment_bytes(self, url: str, segment_name: str) -> bytes:
        try:
            return self._fetch_url_bytes(url)
        except ApiStreamLoaderError as error:
            failure_kind = error.failure.kind
            if failure_kind == "retryable_failure":
                failure_kind = "temporary_failure"
            raise _api_stream_loader_error(
                failure_kind,
                error.failure.message,
                source_name=segment_name,
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
                self._state.terminal_failure_reason = failure.message
            raise ApiStreamLoaderError(failure) from error

    def _enforce_temp_storage_budget(self, next_file_bytes: int) -> None:
        current_bytes = _count_file_bytes_in_directory(self._temp_dir)
        if current_bytes + next_file_bytes > build_api_stream_temp_file_policy().max_bytes:
            raise _api_stream_loader_error(
                "terminal_failure",
                "api_stream temp storage exceeded max byte budget",
            )

    def _finalize_pending_segment(
        self,
        segment_key: tuple[int, str],
        *,
        mark_emitted: bool,
    ) -> None:
        """Remove the current pending segment from queue state after one attempt."""
        self._state.pending_segments.pop(0)
        self._state.queued_segment_keys.discard(segment_key)
        if mark_emitted:
            self._state.emitted_segment_keys.add(segment_key)
        self._state.segment_start_offsets.pop(segment_key, None)

    def _reset_runtime_state(self) -> None:
        self._state = _build_http_hls_runtime_state(
            poll_interval_sec=self._http_loader_contract.playlist_poll_interval_sec,
        )

    def _prune_replay_cache(self, first_visible_sequence: int) -> None:
        self._state.emitted_segment_keys = {
            key
            for key in self._state.emitted_segment_keys
            if key[0] >= first_visible_sequence
        }

    def _raise_if_cancel_requested(self) -> None:
        if is_session_cancel_requested(self._session_id):
            self._stop_iteration(
                reason="explicit_cancel",
                message="Stopping api_stream after explicit cancel [%s]",
                source_url=self._source.input_path if self._source else self._media_playlist_url,
                source_url_class=self._state.source_url_class,
                current_item=None,
            )

    def _enforce_session_runtime_limit(self) -> None:
        started_at = self._state.session_started_monotonic
        if started_at is None:
            return
        if time.monotonic() - started_at <= self._runtime_policy.max_session_runtime_sec:
            return
        self._state.terminal_failure_reason = "api_stream session runtime exceeded max duration"
        raise _api_stream_loader_error(
            "terminal_failure",
            "api_stream session runtime exceeded max duration",
        )

    def _enforce_playlist_refresh_limit(self) -> None:
        if self._state.playlist_refresh_count < self._runtime_policy.max_playlist_refreshes:
            return
        self._state.terminal_failure_reason = "api_stream playlist refresh limit exceeded"
        raise _api_stream_loader_error(
            "terminal_failure",
            "api_stream playlist refresh limit exceeded",
        )

    def _stop_iteration(
        self,
        *,
        reason: str,
        message: str,
        **context: object,
    ) -> None:
        """Log one bounded-stop reason and end the live iterator."""
        self._state.stop_reason = reason
        logger.info(message, self._log_context(**context))
        raise StopIteration

    def _log_context(self, **kwargs: object) -> str:
        return format_log_context(session_id=self._session_id, **kwargs)


def _build_api_stream_request(url: str) -> Request:
    """Return the normalized outbound request for one upstream fetch."""
    return Request(url, headers={"User-Agent": _API_STREAM_USER_AGENT})


def _read_api_stream_response_bytes(
    response: object,
    *,
    max_fetch_bytes: int,
    on_chunk_read,
) -> bytes:
    """Read one upstream response body while enforcing byte and cancel budgets."""
    chunks: list[bytes] = []
    total_bytes = 0
    while True:
        on_chunk_read()
        chunk = response.read(_API_STREAM_FETCH_READ_CHUNK_BYTES)
        if not chunk:
            break
        total_bytes += len(chunk)
        if total_bytes > max_fetch_bytes:
            raise _api_stream_loader_error(
                "terminal_failure",
                "api_stream fetch exceeded max byte budget",
            )
        chunks.append(chunk)
    return b"".join(chunks)


def _classify_api_stream_fetch_exception(
    error: TimeoutError | HTTPError | URLError,
) -> ApiStreamFailure:
    """Map low-level transport exceptions into loader-facing failure semantics."""
    if isinstance(error, TimeoutError):
        return _build_api_stream_failure(
            "retryable_failure",
            "api_stream fetch timed out",
        )
    if isinstance(error, HTTPError):
        failure_kind: ApiStreamFailureKind = (
            "retryable_failure" if error.code in {408, 429, 500, 502, 503, 504}
            else "terminal_failure"
        )
        return _build_api_stream_failure(
            failure_kind,
            f"api_stream upstream returned HTTP {error.code}",
        )
    return _build_api_stream_failure(
        "retryable_failure",
        f"api_stream upstream connection failed: {error.reason}",
    )


def _write_api_stream_temp_file(temp_path: Path, payload: bytes) -> None:
    """Atomically materialize one fetched segment into the session temp directory."""
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
    """Return the next playlist-poll delay while tolerating target-duration drift."""
    configured = max(configured_poll_interval_sec, 0.0)
    if target_duration_sec is None:
        return configured
    safe_target_duration = max(target_duration_sec, 0.1)
    return min(configured, safe_target_duration)


class _HttpHlsApiStreamIterator:
    """Iterator wrapper that lets the concrete HTTP/HLS loader resumably fail."""

    def __init__(self, loader: HttpHlsApiStreamLoader) -> None:
        self._loader = loader

    def __iter__(self) -> "_HttpHlsApiStreamIterator":
        return self

    def __next__(self) -> AnalysisSlice:
        return self._loader.next_slice()
