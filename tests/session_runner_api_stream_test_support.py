"""Shared helpers for api_stream session-runner tests.

This module keeps runner-specific analyzer and slice helpers local to the
api_stream session-runner family, while reusing the shared local HLS server.
"""

from pathlib import Path

import processor
from analyzer_contract import AnalysisSlice, AnalyzerRegistration
from tests.local_hls_test_support import _serve_local_hls


class DummyStore:
    """Minimal in-memory store used by session-runner integration tests."""

    def __init__(self) -> None:
        self.rows: list[dict] = []

    def add_row(self, row: dict) -> None:
        self.rows.append(row)


def _make_live_slices(
    tmp_path: Path,
    *,
    source_group: str,
    names: list[str],
) -> list[AnalysisSlice]:
    slices: list[AnalysisSlice] = []
    live_dir = tmp_path / source_group
    live_dir.mkdir(exist_ok=True)
    for index, name in enumerate(names):
        file_path = live_dir / name
        file_path.write_bytes(b"chunk")
        slices.append(
            AnalysisSlice(
                file_path=file_path,
                source_group=source_group,
                source_name=name,
                window_index=index,
                window_start_sec=float(index),
                window_duration_sec=1.0,
            )
        )
    return slices


def _build_blur_analyzer(score_by_name: dict[str, float]):
    def analyzer(
        file_path: Path,
        prefix: str | None = None,
        source_group: str | None = None,
        source_name: str | None = None,
        window_index: int | None = None,
        window_start_sec: float | None = None,
        window_duration_sec: float | None = None,
    ) -> dict:
        _ = (file_path, prefix)
        return {
            "analyzer": "video_blur",
            "source_type": "video",
            "source_name": str(source_name),
            "source_group": str(source_group),
            "timestamp_utc": f"2026-04-04 10:00:{int(window_index or 0):02d}",
            "processing_sec": 0.01,
            "blur_detected": True,
            "blur_score": score_by_name[str(source_name)],
            "threshold_used": 0.72,
            "window_index": window_index,
            "window_start_sec": window_start_sec,
            "window_duration_sec": window_duration_sec,
        }

    return analyzer


def _patch_processor_with_analyzer(
    monkeypatch,
    *,
    analyzer_name: str,
    store_name: str,
    analyzer,
    supported_modes: tuple[str, ...],
) -> None:
    monkeypatch.setattr(
        processor,
        "get_enabled_analyzers",
        lambda mode: [
            AnalyzerRegistration(
                name=analyzer_name,
                analyzer=analyzer,
                store_name=store_name,
                supported_modes=supported_modes,
                supported_suffixes=(".ts",),
                display_name="Test Analyzer",
                description="Live-like session test detector",
                produces_alerts=True,
            )
        ],
    )
    monkeypatch.setattr(
        processor,
        "STORE_REGISTRY",
        {
            "video_metrics": DummyStore(),
            "blur_metrics": DummyStore(),
        },
    )
    monkeypatch.setattr("session_runner.black_frame_store.flush", lambda: None)
    monkeypatch.setattr("session_runner.blur_metrics_store.flush", lambda: None)
