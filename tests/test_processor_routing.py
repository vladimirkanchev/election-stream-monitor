"""Focused processor tests for routing, filtering, and basic execution selection."""

from pathlib import Path

import processor
from tests.processor_test_support import (
    DummyStore,
    patch_registrations,
    patch_single_registration,
    patch_store_registry,
    registration,
    video_blur_row,
    video_metrics_row,
    write_video_file,
)


def test_run_enabled_analyzers_routes_result_to_matching_store(
    monkeypatch, tmp_path: Path
) -> None:
    """Processor should route one valid detector row into the matching store."""
    file_path = write_video_file(tmp_path)

    def fake_analyzer(file_path: Path, prefix: str | None = None) -> dict:
        _ = prefix
        return video_metrics_row(source_name=file_path.name)

    patch_single_registration(
        monkeypatch,
        name="video_metrics",
        analyzer=fake_analyzer,
        store_name="video_metrics",
    )

    dummy_store = DummyStore()
    patch_store_registry(monkeypatch, video_metrics=dummy_store)

    results = processor.run_enabled_analyzers(
        file_path=file_path,
        prefix="segments",
        mode="video_segments",
    )

    assert len(results) == 1
    assert dummy_store.rows == results


def test_run_enabled_analyzers_skips_unmatched_suffix(monkeypatch, tmp_path: Path) -> None:
    """Processor should skip detectors whose suffix contract does not match the file."""
    file_path = write_video_file(tmp_path, "sample.mp4")

    def fake_analyzer(file_path: Path, prefix: str | None = None) -> dict:
        _ = (file_path, prefix)
        return {"unexpected": True}

    patch_single_registration(
        monkeypatch,
        name="video_metrics",
        analyzer=fake_analyzer,
        store_name="video_metrics",
    )

    results = processor.run_enabled_analyzers(
        file_path=file_path,
        prefix="segments",
        mode="video_segments",
    )

    assert results == []


def test_run_enabled_analyzers_bundle_filters_to_selected_analyzers(
    monkeypatch, tmp_path: Path
) -> None:
    """Selected analyzer filtering should run only the explicitly requested detectors."""
    file_path = write_video_file(tmp_path)

    def metrics_analyzer(file_path: Path, prefix: str | None = None) -> dict:
        _ = prefix
        return video_metrics_row(source_name=file_path.name)

    def blur_analyzer(file_path: Path, prefix: str | None = None) -> dict:
        _ = prefix
        return video_blur_row(
            source_name=file_path.name,
            timestamp_utc="2026-03-30 10:00:01",
        )

    patch_registrations(
        monkeypatch,
        registration(
            name="video_metrics",
            analyzer=metrics_analyzer,
            store_name="video_metrics",
            display_name="Video Metrics",
            description="Metrics detector",
        ),
        registration(
            name="video_blur",
            analyzer=blur_analyzer,
            store_name="blur_metrics",
            display_name="Video Blur",
            description="Blur detector",
        ),
    )

    metrics_store = DummyStore()
    blur_store = DummyStore()
    patch_store_registry(
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


def test_run_enabled_analyzers_bundle_runs_analyzer_without_optional_prefix_parameter(
    monkeypatch, tmp_path: Path
) -> None:
    """Analyzer kwargs should be filtered so detectors without optional prefix parameters still run."""
    file_path = write_video_file(tmp_path)
    observed_file_paths: list[Path] = []

    def analyzer(file_path: Path) -> dict:
        observed_file_paths.append(file_path)
        return video_metrics_row(source_name=file_path.name)

    patch_registrations(
        monkeypatch,
        registration(
            name="video_metrics",
            analyzer=analyzer,
            store_name="video_metrics",
            display_name="Video Metrics",
            description="No-prefix detector",
        ),
    )
    dummy_store = DummyStore()
    patch_store_registry(monkeypatch, video_metrics=dummy_store)

    bundle = processor.run_enabled_analyzers_bundle(
        file_path=file_path,
        prefix="segments",
        mode="video_segments",
        session_id="session-no-prefix",
    )

    assert observed_file_paths == [file_path]
    assert [result["detector_id"] for result in bundle["results"]] == ["video_metrics"]
