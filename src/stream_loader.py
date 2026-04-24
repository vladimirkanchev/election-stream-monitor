"""Facade for `api_stream` contracts, loader selection, and slice orchestration.

The concrete transport logic now lives in focused modules:

- ``stream_loader_contracts`` for shared shapes and builders
- ``stream_loader_http_hls`` for the real HTTP/HLS implementation
- ``stream_loader_fakes`` for deterministic seam loaders used by tests

This facade intentionally stays thin so call sites can depend on one public
entry point without needing to know which implementation owns the details.
"""

from __future__ import annotations

from analyzer_contract import AnalysisSlice
from logger import format_log_context, get_logger
from stream_loader_contracts import (
    ApiStreamFailure,
    ApiStreamFailureKind,
    ApiStreamLoader,
    ApiStreamLoaderError,
    ApiStreamMediaPlaylistSnapshot,
    ApiStreamPlaylistSegment,
    ApiStreamPlaybackContract,
    ApiStreamSourceContract,
    ApiStreamStartSessionContract,
    ApiStreamTelemetrySnapshot,
    build_api_stream_analysis_slice,
    build_api_stream_playback_contract,
    build_api_stream_runtime_policy,
    build_api_stream_slice_identity_key,
    build_api_stream_source_contract,
    build_api_stream_start_session_contract,
    build_api_stream_temp_session_dir,
    cleanup_api_stream_temp_session_dir,
    select_api_stream_master_playlist_variant,
    validate_api_stream_chunk_sequence,
)
from stream_loader_fakes import (
    FakeApiStreamEvent,
    FakeApiStreamLoader,
    StaticApiStreamLoader,
)
from stream_loader_http_hls import HttpHlsApiStreamLoader


logger = get_logger(__name__)


def create_api_stream_loader(session_id: str | None = None) -> ApiStreamLoader:
    """Return the real loader for sessions or an empty deterministic seam loader."""
    if session_id:
        return HttpHlsApiStreamLoader(session_id=session_id)
    return StaticApiStreamLoader()


def iter_api_stream_slices(
    loader: ApiStreamLoader,
    source: ApiStreamSourceContract,
):
    """Yield validated live slices while applying current failure semantics."""
    runtime_policy = build_api_stream_runtime_policy()
    reconnect_budget = runtime_policy.max_reconnect_attempts
    reconnect_attempts = 0
    previous_slice: AnalysisSlice | None = None
    seen_identity_keys: set[tuple[str, int, str]] = set()
    session_id = getattr(loader, "_session_id", None)

    logger.info(
        "Collecting api_stream slices [%s]",
        format_log_context(
            session_id=session_id,
            source_url=source.input_path,
            allowed_schemes=",".join(runtime_policy.allowed_schemes),
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
                            reconnect_budget=reconnect_budget,
                        ),
                    )
                    if reconnect_attempts <= reconnect_budget:
                        continue
                    logger.error(
                        "api_stream reconnect budget exhausted [%s]",
                        format_log_context(
                            session_id=session_id,
                            source_url=source.input_path,
                            source_url_class=telemetry.source_url_class,
                            current_item=failure.source_name,
                            reconnect_attempt=reconnect_attempts,
                            reconnect_budget=reconnect_budget,
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


__all__ = [
    "ApiStreamFailure",
    "ApiStreamFailureKind",
    "ApiStreamLoader",
    "ApiStreamLoaderError",
    "ApiStreamMediaPlaylistSnapshot",
    "ApiStreamPlaybackContract",
    "ApiStreamPlaylistSegment",
    "ApiStreamSourceContract",
    "ApiStreamStartSessionContract",
    "ApiStreamTelemetrySnapshot",
    "FakeApiStreamEvent",
    "FakeApiStreamLoader",
    "HttpHlsApiStreamLoader",
    "StaticApiStreamLoader",
    "build_api_stream_analysis_slice",
    "build_api_stream_playback_contract",
    "build_api_stream_slice_identity_key",
    "build_api_stream_source_contract",
    "build_api_stream_start_session_contract",
    "build_api_stream_temp_session_dir",
    "cleanup_api_stream_temp_session_dir",
    "collect_api_stream_slices",
    "create_api_stream_loader",
    "iter_api_stream_slices",
    "select_api_stream_master_playlist_variant",
    "validate_api_stream_chunk_sequence",
]
