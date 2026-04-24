"""Deterministic seam loaders and scripted fake events for `api_stream`.

This module supports two lightweight use cases:

- contract-only/no-session call paths through the public facade
- deterministic runner/loader tests that should not depend on real HTTP/HLS
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Literal

from analyzer_contract import AnalysisSlice
from stream_loader_contracts import (
    ApiStreamSourceContract,
    ApiStreamTelemetrySnapshot,
    _api_stream_loader_error,
    _classify_api_stream_source_url,
    build_api_stream_analysis_slice,
)
from source_validation import validate_api_stream_url


class StaticApiStreamLoader:
    """Small deterministic loader for tests and no-session seam calls."""

    def __init__(self, slices: list[AnalysisSlice] | None = None) -> None:
        self._slices = list(slices or [])
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
    """Small in-memory scripted loader for live-stream tests."""

    def __init__(self, events: list[FakeApiStreamEvent]) -> None:
        self._events = list(events)
        self._connected = False
        self._source: ApiStreamSourceContract | None = None
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
        return 0

    def telemetry_snapshot(self) -> ApiStreamTelemetrySnapshot:
        return ApiStreamTelemetrySnapshot(
            source_url_class=self._source_url_class,
            accepted_slice_count=0,
        )


class _FakeApiStreamIterator:
    """Iterator that can raise on one step and continue on the next."""

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

        raise _api_stream_loader_error(
            event.kind,
            event.message or event.kind.replace("_", " "),
            source_name=event.current_item,
        )


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
