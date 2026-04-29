"""Tests for processor-level detector execution, routing, and failure policy.

This suite documents the current behavior of the processor as an execution
boundary:

- matching detectors are selected by mode and suffix
- result rows are routed to the expected metric store
- detector failures are isolated where possible
- malformed rows are skipped instead of poisoning healthy detector output
- persistence failures remain session-fatal
"""

from dataclasses import dataclass, field
from pathlib import Path

import processor
from analyzer_contract import AnalysisSlice, AnalyzerRegistration
from session_models import AlertEvent


@dataclass(slots=True)
class DummyStore:
    """Minimal in-memory store used to observe processor write behavior."""

    rows: list[dict] = field(default_factory=list)

    def add_row(self, row: dict) -> None:
        """Record the added row."""
        self.rows.append(row)


class FailingStore:
    """Store double that fails on every write."""

    def add_row(self, row: dict) -> None:
        _ = row
        raise OSError("disk full")


def _write_video_file(tmp_path: Path, name: str = "sample.ts") -> Path:
    file_path = tmp_path / name
    file_path.write_bytes(b"video-bytes")
    return file_path


def _video_metrics_row(
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


def _video_blur_row(
    *,
    source_name: str,
    timestamp_utc: str = "2026-03-30 10:00:00",
    processing_sec: float = 0.02,
    blur_detected: bool = False,
    blur_score: float = 0.15,
    threshold_used: float = 0.72,
    **extra: object,
) -> dict[str, object]:
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


def _registration(
    *,
    name: str,
    analyzer,
    store_name: str,
    supported_modes: tuple[str, ...] = ("video_segments",),
    supported_suffixes: tuple[str, ...] = (".ts",),
    display_name: str | None = None,
    description: str = "Test detector",
    produces_alerts: bool = False,
) -> AnalyzerRegistration:
    return AnalyzerRegistration(
        name=name,
        analyzer=analyzer,
        store_name=store_name,
        supported_modes=supported_modes,
        supported_suffixes=supported_suffixes,
        display_name=display_name or name.replace("_", " ").title(),
        description=description,
        produces_alerts=produces_alerts,
    )


def _patch_registrations(
    monkeypatch,
    *registrations: AnalyzerRegistration,
) -> None:
    monkeypatch.setattr(
        processor,
        "get_enabled_analyzers",
        lambda mode: list(registrations),
    )


def _patch_store_registry(
    monkeypatch,
    *,
    video_metrics=None,
    blur_metrics=None,
) -> None:
    monkeypatch.setattr(
        processor,
        "STORE_REGISTRY",
        {
            "video_metrics": video_metrics if video_metrics is not None else DummyStore(),
            "blur_metrics": blur_metrics if blur_metrics is not None else DummyStore(),
        },
    )


def _run_bundle(
    file_path: Path,
    *,
    session_id: str = "session-1",
    prefix: str = "segments",
    mode: str = "video_segments",
    analysis_slice: AnalysisSlice | None = None,
) -> dict[str, list[dict[str, object]]]:
    return processor.run_enabled_analyzers_bundle(
        file_path=file_path,
        prefix=prefix,
        mode=mode,
        session_id=session_id,
        analysis_slice=analysis_slice,
    )


def test_run_enabled_analyzers_routes_result_to_matching_store(
    monkeypatch, tmp_path: Path
) -> None:
    """Processor should route one valid detector row into the matching store."""
    file_path = _write_video_file(tmp_path)

    def fake_analyzer(file_path: Path, prefix: str | None = None) -> dict:
        _ = prefix
        return _video_metrics_row(source_name=file_path.name)

    _patch_registrations(
        monkeypatch,
        _registration(
            name="video_metrics",
            analyzer=fake_analyzer,
            store_name="video_metrics",
        ),
    )

    dummy_store = DummyStore()
    _patch_store_registry(monkeypatch, video_metrics=dummy_store)

    results = processor.run_enabled_analyzers(
        file_path=file_path,
        prefix="segments",
        mode="video_segments",
    )

    assert len(results) == 1
    assert dummy_store.rows == results


def test_run_enabled_analyzers_skips_unmatched_suffix(monkeypatch, tmp_path: Path) -> None:
    """Processor should skip detectors whose suffix contract does not match the file."""
    file_path = _write_video_file(tmp_path, "sample.mp4")

    def fake_analyzer(file_path: Path, prefix: str | None = None) -> dict:
        _ = (file_path, prefix)
        return {"unexpected": True}

    _patch_registrations(
        monkeypatch,
        _registration(
            name="video_metrics",
            analyzer=fake_analyzer,
            store_name="video_metrics",
        ),
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
    file_path = _write_video_file(tmp_path)

    def failing_analyzer(file_path: Path, prefix: str | None = None) -> dict:
        _ = (file_path, prefix)
        raise RuntimeError("ffmpeg failed")

    def healthy_analyzer(file_path: Path, prefix: str | None = None) -> dict:
        _ = prefix
        return _video_metrics_row(
            source_name=file_path.name,
            processing_sec=0.02,
        )

    _patch_registrations(
        monkeypatch,
        _registration(
            name="broken_detector",
            analyzer=failing_analyzer,
            store_name="video_metrics",
            display_name="Broken Detector",
            description="Fails on purpose",
        ),
        _registration(
            name="video_metrics",
            analyzer=healthy_analyzer,
            store_name="video_metrics",
            display_name="Video Metrics",
            description="Works after a failure",
        ),
    )

    dummy_store = DummyStore()
    _patch_store_registry(monkeypatch, video_metrics=dummy_store)

    bundle = _run_bundle(file_path)

    assert [result["detector_id"] for result in bundle["results"]] == ["video_metrics"]
    assert bundle["alerts"] == []
    assert len(dummy_store.rows) == 1


def test_run_enabled_analyzers_bundle_logs_failure_context(
    monkeypatch, tmp_path: Path
) -> None:
    """Detector failure logs should keep enough context to debug one broken slice."""
    file_path = _write_video_file(tmp_path)
    logged: list[tuple[str, tuple[object, ...]]] = []

    def failing_analyzer(file_path: Path, prefix: str | None = None) -> dict:
        _ = (file_path, prefix)
        raise RuntimeError("ffmpeg failed")

    _patch_registrations(
        monkeypatch,
        _registration(
            name="broken_detector",
            analyzer=failing_analyzer,
            store_name="video_metrics",
            display_name="Broken Detector",
            description="Fails on purpose",
        ),
    )
    monkeypatch.setattr(
        processor.logger,
        "exception",
        lambda message, *args: logged.append((message, args)),
    )

    _run_bundle(
        file_path,
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
    file_path = _write_video_file(tmp_path)

    def failing_analyzer(file_path: Path, prefix: str | None = None) -> dict:
        _ = (file_path, prefix)
        raise RuntimeError("decoder crashed")

    def malformed_analyzer(file_path: Path, prefix: str | None = None) -> list[str]:
        _ = (file_path, prefix)
        return ["not", "a", "row"]

    def healthy_analyzer(file_path: Path, prefix: str | None = None) -> dict:
        _ = prefix
        return _video_blur_row(source_name=file_path.name)

    _patch_registrations(
        monkeypatch,
        _registration(
            name="broken_detector",
            analyzer=failing_analyzer,
            store_name="video_metrics",
            display_name="Broken Detector",
            description="Fails on purpose",
        ),
        _registration(
            name="malformed_detector",
            analyzer=malformed_analyzer,
            store_name="video_metrics",
            display_name="Malformed Detector",
            description="Returns a non-dict payload",
        ),
        _registration(
            name="video_blur",
            analyzer=healthy_analyzer,
            store_name="blur_metrics",
            display_name="Video Blur",
            description="Healthy detector after failures",
        ),
    )

    blur_store = DummyStore()
    _patch_store_registry(monkeypatch, blur_metrics=blur_store)

    bundle = _run_bundle(file_path)

    assert [result["detector_id"] for result in bundle["results"]] == ["video_blur"]
    assert blur_store.rows == [bundle["results"][0]["payload"]]


def test_run_enabled_analyzers_bundle_skips_malformed_rows(
    monkeypatch, tmp_path: Path
) -> None:
    """Rows missing the shared analyzer fields should be ignored safely."""
    file_path = _write_video_file(tmp_path)

    def malformed_analyzer(file_path: Path, prefix: str | None = None) -> dict:
        _ = (file_path, prefix)
        return {
            "source_name": file_path.name,
            "black_detected": True,
        }

    _patch_registrations(
        monkeypatch,
        _registration(
            name="video_metrics",
            analyzer=malformed_analyzer,
            store_name="video_metrics",
            display_name="Video Metrics",
            description="Malformed result detector",
        ),
    )

    dummy_store = DummyStore()
    _patch_store_registry(monkeypatch, video_metrics=dummy_store)

    bundle = _run_bundle(file_path)

    assert bundle == {"results": [], "alerts": []}
    assert dummy_store.rows == []


def test_run_enabled_analyzers_bundle_skips_unexpected_payload_types(
    monkeypatch, tmp_path: Path
) -> None:
    """Non-dict payloads such as None or strings should be ignored safely."""
    file_path = _write_video_file(tmp_path)

    payloads = iter([None, "bad-payload"])

    def invalid_payload_analyzer(file_path: Path, prefix: str | None = None):  # type: ignore[no-untyped-def]
        _ = (file_path, prefix)
        return next(payloads)

    _patch_registrations(
        monkeypatch,
        _registration(
            name="invalid_a",
            analyzer=invalid_payload_analyzer,
            store_name="video_metrics",
            display_name="Invalid A",
            description="Returns None",
        ),
        _registration(
            name="invalid_b",
            analyzer=invalid_payload_analyzer,
            store_name="video_metrics",
            display_name="Invalid B",
            description="Returns string",
        ),
    )

    dummy_store = DummyStore()
    _patch_store_registry(monkeypatch, video_metrics=dummy_store)

    bundle = _run_bundle(file_path)

    assert bundle == {"results": [], "alerts": []}
    assert dummy_store.rows == []


def test_run_enabled_analyzers_bundle_propagates_store_write_failures(
    monkeypatch, tmp_path: Path
) -> None:
    """Store write failures should fail fast because persistence is part of the contract."""
    file_path = _write_video_file(tmp_path)

    def healthy_analyzer(file_path: Path, prefix: str | None = None) -> dict:
        _ = prefix
        return _video_metrics_row(source_name=file_path.name)

    _patch_registrations(
        monkeypatch,
        _registration(
            name="video_metrics",
            analyzer=healthy_analyzer,
            store_name="video_metrics",
            display_name="Video Metrics",
            description="Healthy detector",
        ),
    )
    _patch_store_registry(monkeypatch, video_metrics=FailingStore())

    try:
        _run_bundle(file_path)
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
    file_path = _write_video_file(tmp_path)
    logged: list[tuple[str, tuple[object, ...]]] = []

    def healthy_analyzer(file_path: Path, prefix: str | None = None) -> dict:
        _ = prefix
        return _video_metrics_row(source_name=file_path.name)

    _patch_registrations(
        monkeypatch,
        _registration(
            name="video_metrics",
            analyzer=healthy_analyzer,
            store_name="video_metrics",
            display_name="Video Metrics",
            description="Healthy detector",
        ),
    )
    _patch_store_registry(monkeypatch, video_metrics=FailingStore())
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
    file_path = _write_video_file(tmp_path, "segment_001.ts")
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
        return _video_metrics_row(
            source_name=str(source_name),
            source_group=str(source_group),
            black_detected=True,
            black_segment_count=1,
            total_black_sec=2.0,
            longest_black_sec=2.0,
            black_ratio=1.0,
            window_index=window_index,
            window_start_sec=window_start_sec,
            window_duration_sec=window_duration_sec,
        )

    _patch_registrations(
        monkeypatch,
        _registration(
            name="video_metrics",
            analyzer=sliced_analyzer,
            store_name="video_metrics",
            supported_modes=("video_segments", "api_stream"),
            display_name="Video Metrics",
            description="Slice-aware detector",
            produces_alerts=True,
        ),
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
    _patch_store_registry(monkeypatch, video_metrics=dummy_store)

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


def test_run_enabled_analyzers_bundle_filters_to_selected_analyzers(
    monkeypatch, tmp_path: Path
) -> None:
    """Selected analyzer filtering should run only the explicitly requested detectors."""
    file_path = _write_video_file(tmp_path)

    def metrics_analyzer(file_path: Path, prefix: str | None = None) -> dict:
        _ = prefix
        return _video_metrics_row(source_name=file_path.name)

    def blur_analyzer(file_path: Path, prefix: str | None = None) -> dict:
        _ = prefix
        return _video_blur_row(
            source_name=file_path.name,
            timestamp_utc="2026-03-30 10:00:01",
        )

    _patch_registrations(
        monkeypatch,
        _registration(
            name="video_metrics",
            analyzer=metrics_analyzer,
            store_name="video_metrics",
            display_name="Video Metrics",
            description="Metrics detector",
        ),
        _registration(
            name="video_blur",
            analyzer=blur_analyzer,
            store_name="blur_metrics",
            display_name="Video Blur",
            description="Blur detector",
        ),
    )

    metrics_store = DummyStore()
    blur_store = DummyStore()
    _patch_store_registry(
        monkeypatch,
        video_metrics=metrics_store,
        blur_metrics=blur_store,
    )

    bundle = processor.run_enabled_analyzers_bundle(
        file_path=file_path,
        prefix="segments",
        mode="video_segments",
        session_id="session-selected",
        selected_analyzers={"video_blur"},
    )

    assert [result["detector_id"] for result in bundle["results"]] == ["video_blur"]
    assert metrics_store.rows == []
    assert blur_store.rows == [bundle["results"][0]["payload"]]


def test_run_enabled_analyzers_bundle_returns_results_and_alerts_without_persisting(
    monkeypatch, tmp_path: Path
) -> None:
    """Bundle mode should still produce results and alerts when store persistence is disabled."""
    file_path = _write_video_file(tmp_path)

    def analyzer(file_path: Path, prefix: str | None = None) -> dict:
        _ = prefix
        return _video_metrics_row(
            source_name=file_path.name,
            black_detected=True,
            black_segment_count=1,
            total_black_sec=2.0,
            longest_black_sec=2.0,
            black_ratio=1.0,
        )

    _patch_registrations(
        monkeypatch,
        _registration(
            name="video_metrics",
            analyzer=analyzer,
            store_name="video_metrics",
            display_name="Video Metrics",
            description="Alerting detector",
            produces_alerts=True,
        ),
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
                message="alert without store persistence",
                severity="warning",
                source_name=str(row["source_name"]),
                window_index=None,
                window_start_sec=None,
            )
        ],
    )

    dummy_store = DummyStore()
    _patch_store_registry(monkeypatch, video_metrics=dummy_store)

    bundle = processor.run_enabled_analyzers_bundle(
        file_path=file_path,
        prefix="segments",
        mode="video_segments",
        session_id="session-no-persist",
        persist_to_store=False,
    )

    assert [result["detector_id"] for result in bundle["results"]] == ["video_metrics"]
    assert [alert["detector_id"] for alert in bundle["alerts"]] == ["video_metrics"]
    assert dummy_store.rows == []


def test_run_enabled_analyzers_bundle_routes_generated_alerts(
    monkeypatch, tmp_path: Path
) -> None:
    """Alert-rule output should be returned alongside the detector result bundle."""
    file_path = _write_video_file(tmp_path)

    def analyzer(file_path: Path, prefix: str | None = None) -> dict:
        _ = prefix
        return _video_metrics_row(
            source_name=file_path.name,
            black_detected=True,
            black_segment_count=1,
            total_black_sec=2.0,
            longest_black_sec=2.0,
            black_ratio=1.0,
        )

    observed_alert_args: list[tuple[str, str, dict[str, object]]] = []

    _patch_registrations(
        monkeypatch,
        _registration(
            name="video_metrics",
            analyzer=analyzer,
            store_name="video_metrics",
            display_name="Video Metrics",
            description="Alerting detector",
            produces_alerts=True,
        ),
    )
    monkeypatch.setattr(
        processor,
        "evaluate_alerts",
        lambda session_id, detector_id, row: (
            observed_alert_args.append((session_id, detector_id, row.copy())) or [
                AlertEvent(
                    session_id=session_id,
                    timestamp_utc=str(row["timestamp_utc"]),
                    detector_id=detector_id,
                    title="Black screen detected",
                    message="alert routing check",
                    severity="warning",
                    source_name=str(row["source_name"]),
                    window_index=None,
                    window_start_sec=None,
                )
            ]
        ),
    )

    dummy_store = DummyStore()
    _patch_store_registry(monkeypatch, video_metrics=dummy_store)

    bundle = processor.run_enabled_analyzers_bundle(
        file_path=file_path,
        prefix="segments",
        mode="video_segments",
        session_id="session-alert-routing",
    )

    assert observed_alert_args == [
        (
            "session-alert-routing",
            "video_metrics",
            bundle["results"][0]["payload"],
        )
    ]
    assert [alert["title"] for alert in bundle["alerts"]] == ["Black screen detected"]


def test_run_enabled_analyzers_bundle_raises_when_store_registry_entry_is_missing(
    monkeypatch, tmp_path: Path
) -> None:
    """Missing store registry entries should fail as persistence errors, not be ignored."""
    file_path = _write_video_file(tmp_path)

    def analyzer(file_path: Path, prefix: str | None = None) -> dict:
        _ = prefix
        return _video_metrics_row(source_name=file_path.name)

    _patch_registrations(
        monkeypatch,
        _registration(
            name="video_metrics",
            analyzer=analyzer,
            store_name="missing_store",
            display_name="Video Metrics",
            description="Missing store detector",
        ),
    )
    _patch_store_registry(monkeypatch)
    monkeypatch.setattr(
        processor,
        "STORE_REGISTRY",
        {"blur_metrics": DummyStore()},
    )

    try:
        processor.run_enabled_analyzers_bundle(
            file_path=file_path,
            prefix="segments",
            mode="video_segments",
            session_id="session-missing-store",
        )
    except processor.ProcessorPersistenceError as error:
        assert error.detector_id == "video_metrics"
        assert error.store_name == "missing_store"
        assert error.file_path == file_path
        assert "missing_store" in str(error)
    else:
        raise AssertionError("Expected missing store entries to raise ProcessorPersistenceError")


def test_run_enabled_analyzers_bundle_runs_analyzer_without_optional_prefix_parameter(
    monkeypatch, tmp_path: Path
) -> None:
    """Analyzer kwargs should be filtered so detectors without optional prefix parameters still run."""
    file_path = _write_video_file(tmp_path)
    observed_file_paths: list[Path] = []

    def analyzer(file_path: Path) -> dict:
        observed_file_paths.append(file_path)
        return _video_metrics_row(source_name=file_path.name)

    _patch_registrations(
        monkeypatch,
        _registration(
            name="video_metrics",
            analyzer=analyzer,
            store_name="video_metrics",
            display_name="Video Metrics",
            description="No-prefix detector",
        ),
    )
    dummy_store = DummyStore()
    _patch_store_registry(monkeypatch, video_metrics=dummy_store)

    bundle = processor.run_enabled_analyzers_bundle(
        file_path=file_path,
        prefix="segments",
        mode="video_segments",
        session_id="session-no-prefix",
    )

    assert observed_file_paths == [file_path]
    assert [result["detector_id"] for result in bundle["results"]] == ["video_metrics"]


def test_run_enabled_analyzers_bundle_logs_file_name_when_analysis_slice_is_missing(
    monkeypatch, tmp_path: Path
) -> None:
    """Failure logs should fall back to the file name when no analysis slice context exists."""
    file_path = _write_video_file(tmp_path, "fallback-name.ts")
    logged: list[tuple[str, tuple[object, ...]]] = []

    def failing_analyzer(file_path: Path, prefix: str | None = None) -> dict:
        _ = (file_path, prefix)
        raise RuntimeError("ffmpeg failed")

    _patch_registrations(
        monkeypatch,
        _registration(
            name="broken_detector",
            analyzer=failing_analyzer,
            store_name="video_metrics",
            display_name="Broken Detector",
            description="Fails on purpose",
        ),
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
        session_id="session-fallback-current-item",
    )

    assert logged
    message, args = logged[0]
    assert message == "Analyzer %s failed for %s [%s]"
    assert args[2] == (
        "session_id='session-fallback-current-item' "
        "source_kind='video_segments' "
        "current_item='fallback-name.ts' "
        "detector_id='broken_detector'"
    )
