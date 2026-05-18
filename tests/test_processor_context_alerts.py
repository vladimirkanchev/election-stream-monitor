"""Focused processor tests for analysis-slice propagation and alert bundle behavior."""

from pathlib import Path
from typing import cast

import processor
from analyzer_contract import AnalysisSlice
from session_models import AlertEvent
from tests.processor_test_support import (
    DummyStore,
    patch_registrations,
    patch_single_registration,
    patch_store_registry,
    registration,
    video_metrics_row,
    write_video_file,
)


def test_run_enabled_analyzers_bundle_passes_analysis_slice_context(
    monkeypatch, tmp_path: Path
) -> None:
    """Temporal slice metadata should reach analyzers and survive into events."""
    file_path = write_video_file(tmp_path, "segment_001.ts")
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
        return video_metrics_row(
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

    patch_registrations(
        monkeypatch,
        registration(
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
    patch_store_registry(monkeypatch, video_metrics=dummy_store)

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
    first_payload = cast(dict[str, object], bundle["results"][0]["payload"])
    assert first_payload["window_index"] == 7
    assert first_payload["window_start_sec"] == 14.0
    assert bundle["alerts"][0]["window_index"] == 7
    assert bundle["alerts"][0]["window_start_sec"] == 14.0


def test_run_enabled_analyzers_bundle_returns_results_and_alerts_without_persisting(
    monkeypatch, tmp_path: Path
) -> None:
    """Bundle mode should still produce results and alerts when store persistence is disabled."""
    file_path = write_video_file(tmp_path)

    def analyzer(file_path: Path, prefix: str | None = None) -> dict:
        _ = prefix
        return video_metrics_row(
            source_name=file_path.name,
            black_detected=True,
            black_segment_count=1,
            total_black_sec=2.0,
            longest_black_sec=2.0,
            black_ratio=1.0,
        )

    patch_single_registration(
        monkeypatch,
        name="video_metrics",
        analyzer=analyzer,
        store_name="video_metrics",
        display_name="Video Metrics",
        description="Alerting detector",
        produces_alerts=True,
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
    patch_store_registry(monkeypatch, video_metrics=dummy_store)

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
    file_path = write_video_file(tmp_path)

    def analyzer(file_path: Path, prefix: str | None = None) -> dict:
        _ = prefix
        return video_metrics_row(
            source_name=file_path.name,
            black_detected=True,
            black_segment_count=1,
            total_black_sec=2.0,
            longest_black_sec=2.0,
            black_ratio=1.0,
        )

    observed_alert_args: list[tuple[str, str, dict[str, object]]] = []

    patch_single_registration(
        monkeypatch,
        name="video_metrics",
        analyzer=analyzer,
        store_name="video_metrics",
        display_name="Video Metrics",
        description="Alerting detector",
        produces_alerts=True,
    )
    def fake_evaluate_alerts(session_id, detector_id, row):
        observed_alert_args.append((session_id, detector_id, row.copy()))
        return [
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

    monkeypatch.setattr(processor, "evaluate_alerts", fake_evaluate_alerts)

    dummy_store = DummyStore()
    patch_store_registry(monkeypatch, video_metrics=dummy_store)

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
