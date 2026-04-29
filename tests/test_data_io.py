"""Tests for local input discovery and replay helpers."""

from dataclasses import dataclass, field
from pathlib import Path

import config
from data_io import stream_local_prefix
import processor


@dataclass(slots=True)
class DummyStore:
    rows: list[dict] = field(default_factory=list)

    def add_row(self, row: dict) -> None:
        self.rows.append(row)


def _build_prefix_dir(tmp_path: Path, prefix: str = "segments") -> Path:
    base_dir = tmp_path / prefix
    base_dir.mkdir(parents=True)
    return base_dir


def test_stream_local_prefix_filters_video_segments(
    monkeypatch, tmp_path: Path
) -> None:
    """Video segment mode should only dispatch `.ts` files."""
    prefix = "segments"
    base_dir = _build_prefix_dir(tmp_path, prefix)
    (base_dir / "segment_0001.ts").write_bytes(b"ts")
    (base_dir / "video.mp4").write_bytes(b"mp4")

    monkeypatch.setattr(config, "DATA_SOURCE", "video_segments")
    monkeypatch.setattr(config, "VIDEO_INPUT_FOLDER", tmp_path)

    seen: list[str] = []

    def on_segment(file_path: Path, incoming_prefix: str) -> None:
        assert incoming_prefix == prefix
        seen.append(file_path.name)

    stream_local_prefix(prefix=prefix, on_segment=on_segment, poll_interval=0.0)

    assert seen == ["segment_0001.ts"]


def test_stream_local_prefix_filters_video_files(
    monkeypatch, tmp_path: Path
) -> None:
    """Video file mode should only dispatch `.mp4` files."""
    prefix = "segments"
    base_dir = _build_prefix_dir(tmp_path, prefix)
    (base_dir / "segment_0001.ts").write_bytes(b"ts")
    (base_dir / "video.mp4").write_bytes(b"mp4")

    monkeypatch.setattr(config, "DATA_SOURCE", "video_files")
    monkeypatch.setattr(config, "VIDEO_INPUT_FOLDER", tmp_path)

    seen: list[str] = []

    def on_segment(file_path: Path, incoming_prefix: str) -> None:
        assert incoming_prefix == prefix
        seen.append(file_path.name)

    stream_local_prefix(prefix=prefix, on_segment=on_segment, poll_interval=0.0)

    assert seen == ["video.mp4"]

def test_stream_local_prefix_integrates_with_processor_and_store(
    monkeypatch, tmp_path: Path
) -> None:
    """One discovered segment should flow through processor into the configured store."""
    prefix = "segments"
    base_dir = _build_prefix_dir(tmp_path, prefix)
    file_path = base_dir / "segment_0001.ts"
    file_path.write_bytes(b"ts")

    monkeypatch.setattr(config, "DATA_SOURCE", "video_segments")
    monkeypatch.setattr(config, "VIDEO_INPUT_FOLDER", tmp_path)

    recorded_store = DummyStore()

    def fake_get_enabled_analyzers(mode: str):
        _ = mode

        def fake_analyzer(file_path: Path, prefix: str | None = None) -> dict:
            _ = prefix
            return {
                "analyzer": "video_metrics",
                "source_type": "video",
                "source_name": file_path.name,
                "timestamp_utc": "2026-03-30 10:00:00",
                "processing_sec": 0.01,
                "size_bytes": 2,
                "bitrate_nominal_kbps": 16.0,
                "duration_sec": 1.0,
            }

        from analyzer_contract import AnalyzerRegistration

        return [
            AnalyzerRegistration(
                name="video_metrics",
                analyzer=fake_analyzer,
                store_name="video_metrics",
                supported_modes=("video_segments",),
                supported_suffixes=(".ts",),
                display_name="Video Metrics",
                description="Test detector",
            )
        ]

    monkeypatch.setattr(processor, "get_enabled_analyzers", fake_get_enabled_analyzers)
    monkeypatch.setattr(
        processor,
        "STORE_REGISTRY",
        {"video_metrics": recorded_store, "blur_metrics": DummyStore()},
    )

    stream_local_prefix(
        prefix=prefix,
        on_segment=lambda path, incoming_prefix: processor.process_video_file(
            path, incoming_prefix, mode="video_segments"
        ),
        poll_interval=0.0,
    )

    assert len(recorded_store.rows) == 1
    assert recorded_store.rows[0]["source_name"] == "segment_0001.ts"


def test_stream_local_prefix_returns_cleanly_for_missing_folder(
    monkeypatch, tmp_path: Path
) -> None:
    """Missing input folders should not call the callback or raise."""
    monkeypatch.setattr(config, "DATA_SOURCE", "video_segments")
    monkeypatch.setattr(config, "VIDEO_INPUT_FOLDER", tmp_path)

    seen: list[str] = []

    def on_segment(file_path: Path, incoming_prefix: str) -> None:
        _ = incoming_prefix
        seen.append(file_path.name)

    stream_local_prefix(
        prefix="missing-segments",
        on_segment=on_segment,
        poll_interval=0.0,
    )

    assert seen == []
