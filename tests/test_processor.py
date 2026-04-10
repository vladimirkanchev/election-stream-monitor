"""Tests for processor-level detector execution, routing, and failure policy.

This suite documents the current behavior of the processor as an execution
boundary:

- matching detectors are selected by mode and suffix
- result rows are routed to the expected metric store
- detector failures are isolated where possible
- malformed rows are skipped instead of poisoning healthy detector output
- persistence failures remain session-fatal
"""

from pathlib import Path

import processor
from analyzer_contract import AnalysisSlice, AnalyzerRegistration
from session_models import AlertEvent


class DummyStore:
    """Minimal in-memory store used to observe processor write behavior."""

    def __init__(self) -> None:
        self.rows: list[dict] = []

    def add_row(self, row: dict) -> None:
        """Record the added row."""
        self.rows.append(row)


def test_run_enabled_analyzers_routes_result_to_matching_store(
    monkeypatch, tmp_path: Path
) -> None:
    """Processor should route one valid detector row into the matching store."""
    file_path = tmp_path / "sample.ts"
    file_path.write_bytes(b"video-bytes")

    def fake_analyzer(file_path: Path, prefix: str | None = None) -> dict:
        _ = prefix
        return {
            "analyzer": "video_metrics",
            "source_type": "video",
            "source_name": file_path.name,
            "timestamp_utc": "2026-03-30 10:00:00",
            "processing_sec": 0.01,
            "duration_sec": 2.0,
            "black_detected": False,
            "black_segment_count": 0,
            "total_black_sec": 0.0,
            "longest_black_sec": 0.0,
            "black_ratio": 0.0,
            "picture_threshold_used": 0.98,
            "pixel_threshold_used": 0.1,
            "min_duration_sec": 0.5,
        }

    monkeypatch.setattr(
        processor,
        "get_enabled_analyzers",
        lambda mode: [
            AnalyzerRegistration(
                name="video_metrics",
                analyzer=fake_analyzer,
                store_name="video_metrics",
                supported_modes=("video_segments",),
                supported_suffixes=(".ts",),
                display_name="Video Metrics",
                description="Test detector",
            )
        ],
    )

    dummy_store = DummyStore()
    monkeypatch.setattr(
        processor,
        "STORE_REGISTRY",
        {"video_metrics": dummy_store, "blur_metrics": DummyStore()},
    )

    results = processor.run_enabled_analyzers(
        file_path=file_path,
        prefix="segments",
        mode="video_segments",
    )

    assert len(results) == 1
    assert dummy_store.rows == results


def test_run_enabled_analyzers_skips_unmatched_suffix(monkeypatch, tmp_path: Path) -> None:
    """Processor should skip detectors whose suffix contract does not match the file."""
    file_path = tmp_path / "sample.mp4"
    file_path.write_bytes(b"video-bytes")

    def fake_analyzer(file_path: Path, prefix: str | None = None) -> dict:
        _ = (file_path, prefix)
        return {"unexpected": True}

    monkeypatch.setattr(
        processor,
        "get_enabled_analyzers",
        lambda mode: [
            AnalyzerRegistration(
                name="video_metrics",
                analyzer=fake_analyzer,
                store_name="video_metrics",
                supported_modes=("video_segments",),
                supported_suffixes=(".ts",),
                display_name="Video Metrics",
                description="Test detector",
            )
        ],
    )

    results = processor.run_enabled_analyzers(
        file_path=file_path,
        prefix="segments",
        mode="video_segments",
    )

    assert results == []


def test_run_enabled_analyzers_bundle_isolates_detector_failures(
    monkeypatch, tmp_path: Path
) -> None:
    """One crashing detector should not prevent later healthy detectors from running."""
    file_path = tmp_path / "sample.ts"
    file_path.write_bytes(b"video-bytes")

    def failing_analyzer(file_path: Path, prefix: str | None = None) -> dict:
        _ = (file_path, prefix)
        raise RuntimeError("ffmpeg failed")

    def healthy_analyzer(file_path: Path, prefix: str | None = None) -> dict:
        _ = prefix
        return {
            "analyzer": "video_metrics",
            "source_type": "video",
            "source_name": file_path.name,
            "timestamp_utc": "2026-03-30 10:00:00",
            "processing_sec": 0.02,
            "duration_sec": 2.0,
            "black_detected": False,
            "black_segment_count": 0,
            "total_black_sec": 0.0,
            "longest_black_sec": 0.0,
            "black_ratio": 0.0,
            "picture_threshold_used": 0.98,
            "pixel_threshold_used": 0.1,
            "min_duration_sec": 0.5,
        }

    monkeypatch.setattr(
        processor,
        "get_enabled_analyzers",
        lambda mode: [
            AnalyzerRegistration(
                name="broken_detector",
                analyzer=failing_analyzer,
                store_name="video_metrics",
                supported_modes=("video_segments",),
                supported_suffixes=(".ts",),
                display_name="Broken Detector",
                description="Fails on purpose",
            ),
            AnalyzerRegistration(
                name="video_metrics",
                analyzer=healthy_analyzer,
                store_name="video_metrics",
                supported_modes=("video_segments",),
                supported_suffixes=(".ts",),
                display_name="Video Metrics",
                description="Works after a failure",
            ),
        ],
    )

    dummy_store = DummyStore()
    monkeypatch.setattr(
        processor,
        "STORE_REGISTRY",
        {
            "video_metrics": dummy_store,
            "blur_metrics": DummyStore(),
        },
    )

    bundle = processor.run_enabled_analyzers_bundle(
        file_path=file_path,
        prefix="segments",
        mode="video_segments",
        session_id="session-1",
    )

    assert [result["detector_id"] for result in bundle["results"]] == ["video_metrics"]
    assert bundle["alerts"] == []
    assert len(dummy_store.rows) == 1


def test_run_enabled_analyzers_bundle_logs_failure_context(
    monkeypatch, tmp_path: Path
) -> None:
    """Detector failure logs should keep enough context to debug one broken slice."""
    file_path = tmp_path / "sample.ts"
    file_path.write_bytes(b"video-bytes")
    logged: list[tuple[str, tuple[object, ...]]] = []

    def failing_analyzer(file_path: Path, prefix: str | None = None) -> dict:
        _ = (file_path, prefix)
        raise RuntimeError("ffmpeg failed")

    monkeypatch.setattr(
        processor,
        "get_enabled_analyzers",
        lambda mode: [
            AnalyzerRegistration(
                name="broken_detector",
                analyzer=failing_analyzer,
                store_name="video_metrics",
                supported_modes=("video_segments",),
                supported_suffixes=(".ts",),
                display_name="Broken Detector",
                description="Fails on purpose",
            )
        ],
    )
    monkeypatch.setattr(
        processor.logger,
        "exception",
        lambda message, *args: logged.append((message, args)),
    )

    processor.run_enabled_analyzers_bundle(
        file_path=file_path,
        prefix="segments",
        mode="video_segments",
        session_id="session-log-ctx",
        analysis_slice=AnalysisSlice(
            file_path=file_path,
            source_group="playlist-a",
            source_name="segment_0001.ts",
            window_index=0,
            window_start_sec=0.0,
            window_duration_sec=1.0,
        ),
    )

    assert logged
    message, args = logged[0]
    assert message == "Analyzer %s failed for %s [%s]"
    assert args[0] == "broken_detector"
    assert args[2] == (
        "session_id='session-log-ctx' "
        "source_kind='video_segments' "
        "current_item='segment_0001.ts' "
        "detector_id='broken_detector'"
    )


def test_run_enabled_analyzers_bundle_keeps_healthy_results_when_other_detectors_fail_or_malformed(
    monkeypatch, tmp_path: Path
) -> None:
    """Healthy detectors should still contribute results when neighbors misbehave."""
    file_path = tmp_path / "sample.ts"
    file_path.write_bytes(b"video-bytes")

    def failing_analyzer(file_path: Path, prefix: str | None = None) -> dict:
        _ = (file_path, prefix)
        raise RuntimeError("decoder crashed")

    def malformed_analyzer(file_path: Path, prefix: str | None = None) -> list[str]:
        _ = (file_path, prefix)
        return ["not", "a", "row"]

    def healthy_analyzer(file_path: Path, prefix: str | None = None) -> dict:
        _ = prefix
        return {
            "analyzer": "video_blur",
            "source_type": "video",
            "source_name": file_path.name,
            "timestamp_utc": "2026-03-30 10:00:00",
            "processing_sec": 0.02,
            "blur_detected": False,
            "blur_score": 0.15,
            "threshold_used": 0.72,
        }

    monkeypatch.setattr(
        processor,
        "get_enabled_analyzers",
        lambda mode: [
            AnalyzerRegistration(
                name="broken_detector",
                analyzer=failing_analyzer,
                store_name="video_metrics",
                supported_modes=("video_segments",),
                supported_suffixes=(".ts",),
                display_name="Broken Detector",
                description="Fails on purpose",
            ),
            AnalyzerRegistration(
                name="malformed_detector",
                analyzer=malformed_analyzer,
                store_name="video_metrics",
                supported_modes=("video_segments",),
                supported_suffixes=(".ts",),
                display_name="Malformed Detector",
                description="Returns a non-dict payload",
            ),
            AnalyzerRegistration(
                name="video_blur",
                analyzer=healthy_analyzer,
                store_name="blur_metrics",
                supported_modes=("video_segments",),
                supported_suffixes=(".ts",),
                display_name="Video Blur",
                description="Healthy detector after failures",
            ),
        ],
    )

    blur_store = DummyStore()
    monkeypatch.setattr(
        processor,
        "STORE_REGISTRY",
        {
            "video_metrics": DummyStore(),
            "blur_metrics": blur_store,
        },
    )

    bundle = processor.run_enabled_analyzers_bundle(
        file_path=file_path,
        prefix="segments",
        mode="video_segments",
        session_id="session-1",
    )

    assert [result["detector_id"] for result in bundle["results"]] == ["video_blur"]
    assert blur_store.rows == [bundle["results"][0]["payload"]]


def test_run_enabled_analyzers_bundle_skips_malformed_rows(
    monkeypatch, tmp_path: Path
) -> None:
    """Rows missing the shared analyzer fields should be ignored safely."""
    file_path = tmp_path / "sample.ts"
    file_path.write_bytes(b"video-bytes")

    def malformed_analyzer(file_path: Path, prefix: str | None = None) -> dict:
        _ = (file_path, prefix)
        return {
            "source_name": file_path.name,
            "black_detected": True,
        }

    monkeypatch.setattr(
        processor,
        "get_enabled_analyzers",
        lambda mode: [
            AnalyzerRegistration(
                name="video_metrics",
                analyzer=malformed_analyzer,
                store_name="video_metrics",
                supported_modes=("video_segments",),
                supported_suffixes=(".ts",),
                display_name="Video Metrics",
                description="Malformed result detector",
            )
        ],
    )

    dummy_store = DummyStore()
    monkeypatch.setattr(
        processor,
        "STORE_REGISTRY",
        {
            "video_metrics": dummy_store,
            "blur_metrics": DummyStore(),
        },
    )

    bundle = processor.run_enabled_analyzers_bundle(
        file_path=file_path,
        prefix="segments",
        mode="video_segments",
        session_id="session-1",
    )

    assert bundle == {"results": [], "alerts": []}
    assert dummy_store.rows == []


def test_run_enabled_analyzers_bundle_skips_unexpected_payload_types(
    monkeypatch, tmp_path: Path
) -> None:
    """Non-dict payloads such as None or strings should be ignored safely."""
    file_path = tmp_path / "sample.ts"
    file_path.write_bytes(b"video-bytes")

    payloads = iter([None, "bad-payload"])

    def invalid_payload_analyzer(file_path: Path, prefix: str | None = None):  # type: ignore[no-untyped-def]
        _ = (file_path, prefix)
        return next(payloads)

    monkeypatch.setattr(
        processor,
        "get_enabled_analyzers",
        lambda mode: [
            AnalyzerRegistration(
                name="invalid_a",
                analyzer=invalid_payload_analyzer,
                store_name="video_metrics",
                supported_modes=("video_segments",),
                supported_suffixes=(".ts",),
                display_name="Invalid A",
                description="Returns None",
            ),
            AnalyzerRegistration(
                name="invalid_b",
                analyzer=invalid_payload_analyzer,
                store_name="video_metrics",
                supported_modes=("video_segments",),
                supported_suffixes=(".ts",),
                display_name="Invalid B",
                description="Returns string",
            ),
        ],
    )

    dummy_store = DummyStore()
    monkeypatch.setattr(
        processor,
        "STORE_REGISTRY",
        {
            "video_metrics": dummy_store,
            "blur_metrics": DummyStore(),
        },
    )

    bundle = processor.run_enabled_analyzers_bundle(
        file_path=file_path,
        prefix="segments",
        mode="video_segments",
        session_id="session-1",
    )

    assert bundle == {"results": [], "alerts": []}
    assert dummy_store.rows == []


def test_run_enabled_analyzers_bundle_propagates_store_write_failures(
    monkeypatch, tmp_path: Path
) -> None:
    """Store write failures should fail fast because persistence is part of the contract."""
    file_path = tmp_path / "sample.ts"
    file_path.write_bytes(b"video-bytes")

    def healthy_analyzer(file_path: Path, prefix: str | None = None) -> dict:
        _ = prefix
        return {
            "analyzer": "video_metrics",
            "source_type": "video",
            "source_name": file_path.name,
            "timestamp_utc": "2026-03-30 10:00:00",
            "processing_sec": 0.01,
            "duration_sec": 2.0,
            "black_detected": False,
            "black_segment_count": 0,
            "total_black_sec": 0.0,
            "longest_black_sec": 0.0,
            "black_ratio": 0.0,
            "picture_threshold_used": 0.98,
            "pixel_threshold_used": 0.1,
            "min_duration_sec": 0.5,
        }

    class FailingStore:
        def add_row(self, row: dict) -> None:
            _ = row
            raise OSError("disk full")

    monkeypatch.setattr(
        processor,
        "get_enabled_analyzers",
        lambda mode: [
            AnalyzerRegistration(
                name="video_metrics",
                analyzer=healthy_analyzer,
                store_name="video_metrics",
                supported_modes=("video_segments",),
                supported_suffixes=(".ts",),
                display_name="Video Metrics",
                description="Healthy detector",
            )
        ],
    )
    monkeypatch.setattr(
        processor,
        "STORE_REGISTRY",
        {
            "video_metrics": FailingStore(),
            "blur_metrics": DummyStore(),
        },
    )

    try:
        processor.run_enabled_analyzers_bundle(
            file_path=file_path,
            prefix="segments",
            mode="video_segments",
            session_id="session-1",
        )
    except processor.ProcessorPersistenceError as error:
        assert error.detector_id == "video_metrics"
        assert error.store_name == "video_metrics"
        assert error.file_path == file_path
        assert "disk full" in str(error)
    else:
        raise AssertionError("Expected store write failures to propagate")


def test_run_enabled_analyzers_bundle_logs_store_failure_context(
    monkeypatch, tmp_path: Path
) -> None:
    """Store write failures should log the same structured detector context."""
    file_path = tmp_path / "sample.ts"
    file_path.write_bytes(b"video-bytes")
    logged: list[tuple[str, tuple[object, ...]]] = []

    def healthy_analyzer(file_path: Path, prefix: str | None = None) -> dict:
        _ = prefix
        return {
            "analyzer": "video_metrics",
            "source_type": "video",
            "source_name": file_path.name,
            "timestamp_utc": "2026-03-30 10:00:00",
            "processing_sec": 0.01,
            "duration_sec": 2.0,
            "black_detected": False,
            "black_segment_count": 0,
            "total_black_sec": 0.0,
            "longest_black_sec": 0.0,
            "black_ratio": 0.0,
            "picture_threshold_used": 0.98,
            "pixel_threshold_used": 0.1,
            "min_duration_sec": 0.5,
        }

    class FailingStore:
        def add_row(self, row: dict) -> None:
            _ = row
            raise OSError("disk full")

    monkeypatch.setattr(
        processor,
        "get_enabled_analyzers",
        lambda mode: [
            AnalyzerRegistration(
                name="video_metrics",
                analyzer=healthy_analyzer,
                store_name="video_metrics",
                supported_modes=("video_segments",),
                supported_suffixes=(".ts",),
                display_name="Video Metrics",
                description="Healthy detector",
            )
        ],
    )
    monkeypatch.setattr(
        processor,
        "STORE_REGISTRY",
        {
            "video_metrics": FailingStore(),
            "blur_metrics": DummyStore(),
        },
    )
    monkeypatch.setattr(
        processor.logger,
        "exception",
        lambda message, *args: logged.append((message, args)),
    )

    try:
        processor.run_enabled_analyzers_bundle(
            file_path=file_path,
            prefix="segments",
            mode="video_segments",
            session_id="session-store-log",
        )
    except processor.ProcessorPersistenceError:
        pass
    else:
        raise AssertionError("Expected store write failures to propagate")

    assert logged
    message, args = logged[0]
    assert message == "Store write failed for analyzer %s (%s) while processing %s [%s]"
    assert args[0] == "video_metrics"
    assert args[1] == "video_metrics"
    assert args[3] == (
        "session_id='session-store-log' "
        "source_kind='video_segments' "
        "current_item='sample.ts' "
        "detector_id='video_metrics'"
    )


def test_run_enabled_analyzers_bundle_passes_analysis_slice_context(
    monkeypatch, tmp_path: Path
) -> None:
    """Temporal slice metadata should reach analyzers and survive into events."""
    file_path = tmp_path / "segment_001.ts"
    file_path.write_bytes(b"video-bytes")
    observed_kwargs: dict[str, object] = {}

    def sliced_analyzer(
        file_path: Path,
        prefix: str | None = None,
        source_group: str | None = None,
        source_name: str | None = None,
        window_index: int | None = None,
        window_start_sec: float | None = None,
        window_duration_sec: float | None = None,
    ) -> dict:
        observed_kwargs.update(
            {
                "file_path": file_path,
                "prefix": prefix,
                "source_group": source_group,
                "source_name": source_name,
                "window_index": window_index,
                "window_start_sec": window_start_sec,
                "window_duration_sec": window_duration_sec,
            }
        )
        return {
            "analyzer": "video_metrics",
            "source_type": "video",
            "source_name": str(source_name),
            "source_group": str(source_group),
            "timestamp_utc": "2026-03-30 10:00:00",
            "processing_sec": 0.01,
            "duration_sec": 2.0,
            "black_detected": True,
            "black_segment_count": 1,
            "total_black_sec": 2.0,
            "longest_black_sec": 2.0,
            "black_ratio": 1.0,
            "picture_threshold_used": 0.98,
            "pixel_threshold_used": 0.1,
            "min_duration_sec": 0.5,
            "window_index": window_index,
            "window_start_sec": window_start_sec,
            "window_duration_sec": window_duration_sec,
        }

    monkeypatch.setattr(
        processor,
        "get_enabled_analyzers",
        lambda mode: [
            AnalyzerRegistration(
                name="video_metrics",
                analyzer=sliced_analyzer,
                store_name="video_metrics",
                supported_modes=("video_segments", "api_stream"),
                supported_suffixes=(".ts",),
                display_name="Video Metrics",
                description="Slice-aware detector",
                produces_alerts=True,
            )
        ],
    )
    monkeypatch.setattr(
        processor,
        "evaluate_alerts",
        lambda session_id, detector_id, row: [
            AlertEvent(
                session_id=session_id,
                timestamp_utc=str(row["timestamp_utc"]),
                detector_id=detector_id,
                title="Black screen detected",
                message="slice alert",
                severity="warning",
                source_name=str(row["source_name"]),
                window_index=int(row["window_index"]),
                window_start_sec=float(row["window_start_sec"]),
            )
        ],
    )

    dummy_store = DummyStore()
    monkeypatch.setattr(
        processor,
        "STORE_REGISTRY",
        {
            "video_metrics": dummy_store,
            "blur_metrics": DummyStore(),
        },
    )

    bundle = processor.run_enabled_analyzers_bundle(
        file_path=file_path,
        prefix="api",
        mode="api_stream",
        session_id="session-42",
        analysis_slice=AnalysisSlice(
            file_path=file_path,
            source_group="stream-a",
            source_name="segment_001.ts",
            window_index=7,
            window_start_sec=14.0,
            window_duration_sec=2.0,
        ),
    )

    assert observed_kwargs == {
        "file_path": file_path,
        "prefix": "api",
        "source_group": "stream-a",
        "source_name": "segment_001.ts",
        "window_index": 7,
        "window_start_sec": 14.0,
        "window_duration_sec": 2.0,
    }
    assert bundle["results"][0]["payload"]["window_index"] == 7
    assert bundle["results"][0]["payload"]["window_start_sec"] == 14.0
    assert bundle["alerts"][0]["window_index"] == 7
    assert bundle["alerts"][0]["window_start_sec"] == 14.0
