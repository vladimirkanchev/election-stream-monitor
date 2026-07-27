"""Processor malformed-result and persistence-failure boundary tests."""

from pathlib import Path

import processor
import pytest
from analyzer_contract import AnalysisSlice
from tests.processor_test_support import (
    DummyStore,
    FailingStore,
    patch_registrations,
    patch_store_registry,
    registration,
    run_bundle,
    video_blur_row,
    video_metrics_row,
    write_video_file,
)


def test_run_enabled_analyzers_bundle_isolates_detector_failures(
    monkeypatch, tmp_path: Path
) -> None:
    """One crashing detector should not prevent later healthy detectors from running."""
    file_path = write_video_file(tmp_path)

    def failing_analyzer(file_path: Path, prefix: str | None = None) -> dict:
        _ = (file_path, prefix)
        raise RuntimeError("ffmpeg failed")

    def healthy_analyzer(file_path: Path, prefix: str | None = None) -> dict:
        _ = prefix
        return video_metrics_row(
            source_name=file_path.name,
            processing_sec=0.02,
        )

    patch_registrations(
        monkeypatch,
        registration(
            name="broken_detector",
            analyzer=failing_analyzer,
            store_name="video_metrics",
            display_name="Broken Detector",
            description="Fails on purpose",
        ),
        registration(
            name="video_metrics",
            analyzer=healthy_analyzer,
            store_name="video_metrics",
            display_name="Video Metrics",
            description="Works after a failure",
        ),
    )

    dummy_store = DummyStore()
    patch_store_registry(monkeypatch, video_metrics=dummy_store)

    bundle = run_bundle(file_path)

    assert [result["detector_id"] for result in bundle["results"]] == ["video_metrics"]
    assert bundle["alerts"] == []
    assert len(dummy_store.rows) == 1


def test_run_enabled_analyzers_bundle_logs_failure_context(
    monkeypatch, tmp_path: Path
) -> None:
    """Detector failure logs should keep enough context to debug one broken slice."""
    file_path = write_video_file(tmp_path)
    logged: list[tuple[str, tuple[object, ...]]] = []

    def failing_analyzer(file_path: Path, prefix: str | None = None) -> dict:
        _ = (file_path, prefix)
        raise RuntimeError("ffmpeg failed")

    patch_registrations(
        monkeypatch,
        registration(
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

    run_bundle(file_path, session_id="session-log-ctx")

    assert logged
    message, args = logged[0]
    assert message == "Detector %s failed for %s [%s]"
    assert args[0] == "broken_detector"
    assert args[2] == (
        "session_id='session-log-ctx' "
        "source_kind='video_segments' "
        "current_item='sample.ts' "
        "detector_id='broken_detector'"
    )


def test_run_enabled_analyzers_bundle_logs_analysis_slice_failure_context(
    monkeypatch, tmp_path: Path
) -> None:
    """Failure logs should prefer the supplied slice identity over the file name."""
    file_path = write_video_file(tmp_path)
    logged: list[tuple[str, tuple[object, ...]]] = []

    def failing_analyzer(file_path: Path, prefix: str | None = None) -> dict:
        _ = (file_path, prefix)
        raise RuntimeError("ffmpeg failed")

    patch_registrations(
        monkeypatch,
        registration(
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

    run_bundle(
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
    assert logged[0][0] == "Detector %s failed for %s [%s]"
    assert logged[0][1][2] == (
        "session_id='session-log-ctx' "
        "source_kind='video_segments' "
        "current_item='segment_0001.ts' "
        "detector_id='broken_detector'"
    )


def test_run_enabled_analyzers_bundle_keeps_healthy_results_when_other_detectors_fail_or_malformed(
    monkeypatch, tmp_path: Path
) -> None:
    """Healthy detectors should still contribute results when neighbors misbehave."""
    file_path = write_video_file(tmp_path)

    def failing_analyzer(file_path: Path, prefix: str | None = None) -> dict:
        _ = (file_path, prefix)
        raise RuntimeError("decoder crashed")

    def malformed_analyzer(file_path: Path, prefix: str | None = None) -> list[str]:
        _ = (file_path, prefix)
        return ["not", "a", "row"]

    def healthy_analyzer(file_path: Path, prefix: str | None = None) -> dict:
        _ = prefix
        return video_blur_row(source_name=file_path.name)

    patch_registrations(
        monkeypatch,
        registration(
            name="broken_detector",
            analyzer=failing_analyzer,
            store_name="video_metrics",
            display_name="Broken Detector",
            description="Fails on purpose",
        ),
        registration(
            name="malformed_detector",
            analyzer=malformed_analyzer,
            store_name="video_metrics",
            display_name="Malformed Detector",
            description="Returns a non-dict payload",
        ),
        registration(
            name="video_blur",
            analyzer=healthy_analyzer,
            store_name="blur_metrics",
            display_name="Video Blur",
            description="Healthy detector after failures",
        ),
    )

    blur_store = DummyStore()
    patch_store_registry(monkeypatch, blur_metrics=blur_store)

    bundle = run_bundle(file_path)

    assert [result["detector_id"] for result in bundle["results"]] == ["video_blur"]
    assert blur_store.rows == [bundle["results"][0]["payload"]]


def test_run_enabled_analyzers_bundle_skips_malformed_rows(
    monkeypatch, tmp_path: Path
) -> None:
    """Rows missing the shared analyzer fields should be ignored safely."""
    file_path = write_video_file(tmp_path)

    def malformed_analyzer(file_path: Path, prefix: str | None = None) -> dict:
        _ = (file_path, prefix)
        return {
            "source_name": file_path.name,
            "black_detected": True,
        }

    patch_registrations(
        monkeypatch,
        registration(
            name="video_metrics",
            analyzer=malformed_analyzer,
            store_name="video_metrics",
            display_name="Video Metrics",
            description="Malformed result detector",
        ),
    )

    dummy_store = DummyStore()
    patch_store_registry(monkeypatch, video_metrics=dummy_store)

    bundle = run_bundle(file_path)

    assert bundle["results"] == []
    assert bundle["alerts"] == []
    assert dummy_store.rows == []


def test_run_enabled_analyzers_bundle_skips_unexpected_payload_types(
    monkeypatch, tmp_path: Path
) -> None:
    """Non-dict payloads such as None or strings should be ignored safely."""
    file_path = write_video_file(tmp_path)

    payloads = iter([None, "bad-payload"])

    def invalid_payload_analyzer(file_path: Path, prefix: str | None = None):  # type: ignore[no-untyped-def]
        _ = (file_path, prefix)
        return next(payloads)

    patch_registrations(
        monkeypatch,
        registration(
            name="invalid_a",
            analyzer=invalid_payload_analyzer,
            store_name="video_metrics",
            display_name="Invalid A",
            description="Returns None",
        ),
        registration(
            name="invalid_b",
            analyzer=invalid_payload_analyzer,
            store_name="video_metrics",
            display_name="Invalid B",
            description="Returns string",
        ),
    )

    dummy_store = DummyStore()
    patch_store_registry(monkeypatch, video_metrics=dummy_store)

    bundle = run_bundle(file_path)

    assert bundle["results"] == []
    assert bundle["alerts"] == []
    assert dummy_store.rows == []


def test_run_enabled_analyzers_bundle_propagates_store_write_failures(
    monkeypatch, tmp_path: Path
) -> None:
    """Store write failures should fail fast because persistence is part of the contract."""
    file_path = write_video_file(tmp_path)

    def healthy_analyzer(file_path: Path, prefix: str | None = None) -> dict:
        _ = prefix
        return video_metrics_row(source_name=file_path.name)

    patch_registrations(
        monkeypatch,
        registration(
            name="video_metrics",
            analyzer=healthy_analyzer,
            store_name="video_metrics",
            display_name="Video Metrics",
            description="Healthy detector",
        ),
    )
    patch_store_registry(monkeypatch, video_metrics=FailingStore())

    with pytest.raises(processor.ProcessorPersistenceError) as exc_info:
        run_bundle(file_path)

    error = exc_info.value
    assert error.detector_id == "video_metrics"
    assert error.store_name == "video_metrics"
    assert error.file_path == file_path
    assert "disk full" in str(error)


def test_run_enabled_analyzers_bundle_logs_store_failure_context(
    monkeypatch, tmp_path: Path
) -> None:
    """Store write failures should log the same structured detector context."""
    file_path = write_video_file(tmp_path)
    logged: list[tuple[str, tuple[object, ...]]] = []

    def healthy_analyzer(file_path: Path, prefix: str | None = None) -> dict:
        _ = prefix
        return video_metrics_row(source_name=file_path.name)

    patch_registrations(
        monkeypatch,
        registration(
            name="video_metrics",
            analyzer=healthy_analyzer,
            store_name="video_metrics",
            display_name="Video Metrics",
            description="Healthy detector",
        ),
    )
    patch_store_registry(monkeypatch, video_metrics=FailingStore())
    monkeypatch.setattr(
        processor.logger,
        "exception",
        lambda message, *args: logged.append((message, args)),
    )

    with pytest.raises(processor.ProcessorPersistenceError):
        processor.run_enabled_analyzers_bundle(
            file_path=file_path,
            prefix="segments",
            mode="video_segments",
            session_id="session-store-log",
        )

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


def test_run_enabled_analyzers_bundle_raises_when_store_registry_entry_is_missing(
    monkeypatch, tmp_path: Path
) -> None:
    """Missing store registry entries should fail as persistence errors, not be ignored."""
    file_path = write_video_file(tmp_path)

    def analyzer(file_path: Path, prefix: str | None = None) -> dict:
        _ = prefix
        return video_metrics_row(source_name=file_path.name)

    patch_registrations(
        monkeypatch,
        registration(
            name="video_metrics",
            analyzer=analyzer,
            store_name="missing_store",
            display_name="Video Metrics",
            description="Missing store detector",
        ),
    )
    patch_store_registry(monkeypatch)
    monkeypatch.setattr(
        processor,
        "STORE_REGISTRY",
        {"blur_metrics": DummyStore()},
    )

    with pytest.raises(processor.ProcessorPersistenceError) as exc_info:
        processor.run_enabled_analyzers_bundle(
            file_path=file_path,
            prefix="segments",
            mode="video_segments",
            session_id="session-missing-store",
        )

    error = exc_info.value
    assert error.detector_id == "video_metrics"
    assert error.store_name == "missing_store"
    assert error.file_path == file_path
    assert "missing_store" in str(error)


def test_run_enabled_analyzers_bundle_logs_file_name_when_analysis_slice_is_missing(
    monkeypatch, tmp_path: Path
) -> None:
    """Failure logs should fall back to the file name when no analysis slice context exists."""
    file_path = write_video_file(tmp_path, "fallback-name.ts")
    logged: list[tuple[str, tuple[object, ...]]] = []

    def failing_analyzer(file_path: Path, prefix: str | None = None) -> dict:
        _ = (file_path, prefix)
        raise RuntimeError("ffmpeg failed")

    patch_registrations(
        monkeypatch,
        registration(
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
    assert message == "Detector %s failed for %s [%s]"
    assert args[2] == (
        "session_id='session-fallback-current-item' "
        "source_kind='video_segments' "
        "current_item='fallback-name.ts' "
        "detector_id='broken_detector'"
    )
