"""Shared builders for focused processor boundary tests."""

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

import config
import processor
from analyzer_contract import AnalysisSlice, AnalyzerRegistration, InputMode, StoreName

ResultRow = dict[str, object]
AnalyzerFn = Callable[..., Any]


@dataclass(slots=True)
class DummyStore:
    """In-memory store double that records every persisted analyzer row."""

    rows: list[ResultRow] = field(default_factory=list)

    def add_row(self, row: ResultRow) -> None:
        """Record one persisted row without transformation."""
        self.rows.append(row)


class FailingStore:
    """Store double that always fails to exercise persistence error handling."""

    def add_row(self, row: ResultRow) -> None:
        """Raise a stable write error after accepting the row shape."""
        _ = row
        raise OSError("disk full")


def write_video_file(tmp_path: Path, name: str = "sample.ts") -> Path:
    """Create a tiny on-disk media stub with the requested filename."""
    file_path = tmp_path / name
    file_path.write_bytes(b"video-bytes")
    return file_path


def video_metrics_row(
    *,
    source_name: str,
    timestamp_utc: str = "2026-03-30 10:00:00",
    processing_sec: float = 0.01,
    duration_sec: float = 2.0,
    black_detected: bool = False,
    black_segment_count: int = 0,
    total_black_sec: float = 0.0,
    longest_black_sec: float = 0.0,
    black_ratio: float = 0.0,
    picture_threshold_used: float = 0.98,
    pixel_threshold_used: float = 0.1,
    min_duration_sec: float = 0.5,
    **extra: object,
) -> dict[str, object]:
    """Build a representative `video_metrics` detector payload for tests."""
    return {
        "analyzer": "video_metrics",
        "source_type": "video",
        "source_name": source_name,
        "timestamp_utc": timestamp_utc,
        "processing_sec": processing_sec,
        "duration_sec": duration_sec,
        "black_detected": black_detected,
        "black_segment_count": black_segment_count,
        "total_black_sec": total_black_sec,
        "longest_black_sec": longest_black_sec,
        "black_ratio": black_ratio,
        "picture_threshold_used": picture_threshold_used,
        "pixel_threshold_used": pixel_threshold_used,
        "min_duration_sec": min_duration_sec,
        **extra,
    }


def video_blur_row(
    *,
    source_name: str,
    timestamp_utc: str = "2026-03-30 10:00:00",
    processing_sec: float = 0.02,
    blur_detected: bool = False,
    blur_score: float = 0.15,
    threshold_used: float = config.VIDEO_BLUR_ALERT_THRESHOLD,
    **extra: object,
) -> dict[str, object]:
    """Build a representative `video_blur` detector payload for tests."""
    return {
        "analyzer": "video_blur",
        "source_type": "video",
        "source_name": source_name,
        "timestamp_utc": timestamp_utc,
        "processing_sec": processing_sec,
        "blur_detected": blur_detected,
        "blur_score": blur_score,
        "threshold_used": threshold_used,
        **extra,
    }


def registration(
    *,
    name: str,
    analyzer: AnalyzerFn,
    store_name: StoreName | str,
    supported_modes: tuple[InputMode, ...] = ("video_segments",),
    supported_suffixes: tuple[str, ...] = (".ts",),
    display_name: str | None = None,
    description: str = "Test detector",
    produces_alerts: bool = False,
) -> AnalyzerRegistration:
    """Create one explicit analyzer registration with sensible test defaults."""
    return AnalyzerRegistration(
        name=name,
        analyzer=analyzer,
        store_name=cast(StoreName, store_name),
        supported_modes=supported_modes,
        supported_suffixes=supported_suffixes,
        display_name=display_name or name.replace("_", " ").title(),
        description=description,
        produces_alerts=produces_alerts,
    )


def patch_registrations(
    monkeypatch,
    *registrations: AnalyzerRegistration,
) -> None:
    """Replace the enabled analyzer registry with the provided registrations."""
    monkeypatch.setattr(
        processor,
        "get_enabled_analyzers",
        lambda mode: list(registrations),
    )


def patch_single_registration(
    monkeypatch,
    *,
    name: str,
    analyzer: AnalyzerFn,
    store_name: StoreName | str,
    supported_modes: tuple[InputMode, ...] = ("video_segments",),
    supported_suffixes: tuple[str, ...] = (".ts",),
    display_name: str | None = None,
    description: str = "Test detector",
    produces_alerts: bool = False,
) -> AnalyzerRegistration:
    """Install one analyzer registration directly and return the created object."""
    analyzer_registration = registration(
        name=name,
        analyzer=analyzer,
        store_name=store_name,
        supported_modes=supported_modes,
        supported_suffixes=supported_suffixes,
        display_name=display_name,
        description=description,
        produces_alerts=produces_alerts,
    )
    patch_registrations(monkeypatch, analyzer_registration)
    return analyzer_registration


def patch_store_registry(
    monkeypatch,
    *,
    video_metrics=None,
    blur_metrics=None,
) -> None:
    """Replace the processor store registry with simple in-memory doubles."""
    monkeypatch.setattr(
        processor,
        "STORE_REGISTRY",
        {
            "video_metrics": video_metrics if video_metrics is not None else DummyStore(),
            "blur_metrics": blur_metrics if blur_metrics is not None else DummyStore(),
        },
    )


def run_bundle(
    file_path: Path,
    *,
    session_id: str = "session-1",
    prefix: str = "segments",
    mode: InputMode = "video_segments",
    analysis_slice: AnalysisSlice | None = None,
) -> dict[str, list[dict[str, object]]]:
    """Run the bundle API with standard focused-processor defaults."""
    return processor.run_enabled_analyzers_bundle(
        file_path=file_path,
        prefix=prefix,
        mode=mode,
        session_id=session_id,
        analysis_slice=analysis_slice,
    )


__all__ = [
    "AnalyzerFn",
    "DummyStore",
    "FailingStore",
    "ResultRow",
    "patch_registrations",
    "patch_single_registration",
    "patch_store_registry",
    "registration",
    "run_bundle",
    "video_blur_row",
    "video_metrics_row",
    "write_video_file",
]
