"""Ground-truth validation for synthetic `api_stream` session contracts.

This suite stays separate from the real-media matrix so contract cases can be
run quickly when the live-session transport or analyzer behavior changes.
"""

from pathlib import Path

import pytest

import config
import processor
import session_runner
from analyzer_contract import AnalysisSlice, AnalyzerRegistration
from session_io import read_session_snapshot
from stream_loader import FakeApiStreamLoader
from tests.e2e_session_test_support import (
    assert_snapshot_matches_ground_truth,
    configure_session_output,
    load_ground_truth_cases,
    run_and_read_local_session,
)
from tests.session_runner_api_stream_test_support import (
    DummyStore,
    _make_live_loader_events,
    _make_live_slices,
    _patch_runner_store_flushes,
)


pytestmark = pytest.mark.e2e

SIMULATED_API_STREAM_CASES = load_ground_truth_cases("simulated_api_stream_cases")


def _build_api_stream_row(
    detector_id: str,
    spec: dict[str, object],
    *,
    source_group: str,
    source_name: str,
    window_index: int | None,
    window_start_sec: float | None,
    window_duration_sec: float | None,
) -> dict[str, object]:
    """Construct one synthetic analyzer row for a ground-truth case."""
    base = {
        "analyzer": detector_id,
        "source_type": "video",
        "source_name": source_name,
        "source_group": source_group,
        "timestamp_utc": f"2026-04-04 10:00:{int(window_index or 0):02d}",
        "processing_sec": 0.01,
        "window_index": window_index,
        "window_start_sec": window_start_sec,
        "window_duration_sec": window_duration_sec,
    }

    if detector_id == "video_metrics":
        base.update(
            {
                "duration_sec": 1.0,
                "black_detected": False,
                "black_ratio": 0.0,
                "longest_black_sec": 0.0,
                "total_black_sec": 0.0,
            }
        )
    elif detector_id == "video_blur":
        base.update(
            {
                "blur_detected": False,
                "blur_score": 0.2,
                "threshold_used": config.VIDEO_BLUR_ALERT_THRESHOLD,
                "sample_count": 8,
            }
        )
    else:
        raise ValueError(f"Unsupported detector id: {detector_id}")

    base.update(spec)
    return base


def _build_case_analyzer(
    detector_id: str,
    events_by_source: dict[str, dict[str, object]],
):
    def analyzer(
        file_path: Path,
        prefix: str | None = None,
        source_group: str | None = None,
        source_name: str | None = None,
        window_index: int | None = None,
        window_start_sec: float | None = None,
        window_duration_sec: float | None = None,
    ) -> dict[str, object]:
        _ = (file_path, prefix)
        event_spec = events_by_source[str(source_name)]
        action = event_spec.get("action")
        if action == "raise":
            raise ValueError(str(event_spec.get("message", "simulated detector failure")))
        if action == "malformed":
            return {"source_name": str(source_name)}

        return _build_api_stream_row(
            detector_id,
            event_spec,
            source_group=str(source_group),
            source_name=str(source_name),
            window_index=window_index,
            window_start_sec=window_start_sec,
            window_duration_sec=window_duration_sec,
        )

    return analyzer


def _patch_api_stream_detectors(
    monkeypatch,
    detector_specs: dict[str, dict[str, object]],
) -> None:
    registrations: list[AnalyzerRegistration] = []
    for detector_id, spec in detector_specs.items():
        registrations.append(
            AnalyzerRegistration(
                name=detector_id,
                analyzer=_build_case_analyzer(detector_id, spec["events"]),
                store_name=spec["store_name"],
                supported_modes=("api_stream",),
                supported_suffixes=(".ts",),
                display_name=f"Ground Truth {detector_id}",
                description="Synthetic api-stream contract detector",
                produces_alerts=True,
            )
        )

    monkeypatch.setattr(
        processor,
        "get_enabled_analyzers",
        lambda mode: registrations if mode == "api_stream" else [],
    )


def _install_dummy_stores(monkeypatch) -> None:
    """Use in-memory stores for synthetic api-stream contract cases."""
    monkeypatch.setattr(
        processor,
        "STORE_REGISTRY",
        {
            "video_metrics": DummyStore(),
            "blur_metrics": DummyStore(),
        },
    )
    _patch_runner_store_flushes(monkeypatch)


def _install_case_loader(monkeypatch, tmp_path: Path, case: dict[str, object]) -> None:
    """Install the fake live loader for one ground-truth case."""
    slices = _make_live_slices(
        tmp_path,
        source_group="stream-a",
        names=case["slice_names"],
    )
    monkeypatch.setattr(
        session_runner,
        "get_api_stream_loader",
        lambda session_id=None: FakeApiStreamLoader(_make_live_loader_events(slices)),
    )


def _patch_optional_bundle_failure(monkeypatch, case: dict[str, object]) -> None:
    """Patch the bundle seam when a ground-truth case expects one terminal failure."""
    failure_window = case.get("bundle_failure_at_window")
    if failure_window is None:
        return

    original_bundle = session_runner.run_enabled_analyzers_bundle
    expected_message = case["expected_exception"]["message"]

    def maybe_fail_bundle(
        file_path: Path,
        prefix: str,
        mode: str,
        session_id: str,
        selected_analyzers: set[str] | None = None,
        persist_to_store: bool = True,
        analysis_slice: AnalysisSlice | None = None,
    ) -> dict[str, list[dict[str, object]]]:
        _ = (file_path, prefix, mode, session_id, selected_analyzers, persist_to_store)
        if analysis_slice is not None and analysis_slice.window_index == failure_window:
            raise ValueError(str(expected_message))
        return original_bundle(
            file_path=file_path,
            prefix=prefix,
            mode=mode,
            session_id=session_id,
            selected_analyzers=selected_analyzers,
            persist_to_store=persist_to_store,
            analysis_slice=analysis_slice,
        )

    monkeypatch.setattr(session_runner, "run_enabled_analyzers_bundle", maybe_fail_bundle)


@pytest.mark.parametrize("case", SIMULATED_API_STREAM_CASES, ids=lambda case: case["id"])
def test_synthetic_api_stream_session_contract_matches_ground_truth(
    case: dict[str, object],
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Synthetic api-stream cases should match persisted contract expectations."""
    configure_session_output(monkeypatch, tmp_path)
    _install_dummy_stores(monkeypatch)
    _patch_api_stream_detectors(monkeypatch, case["detectors"])
    _install_case_loader(monkeypatch, tmp_path, case)
    _patch_optional_bundle_failure(monkeypatch, case)

    session_id = f"ground-truth-{case['id']}"
    expected_exception = case.get("expected_exception")
    if expected_exception is None:
        metadata, snapshot = run_and_read_local_session(
            mode="api_stream",
            input_path=case["input_path"],
            selected_detectors=case["selected_detectors"],
            session_id=session_id,
        )
        assert metadata.status == case["ground_truth"]["session_status"]
    else:
        with pytest.raises(ValueError, match=expected_exception["message"]):
            session_runner.run_local_session(
                mode="api_stream",
                input_path=case["input_path"],
                selected_detectors=case["selected_detectors"],
                session_id=session_id,
            )
        snapshot = read_session_snapshot(session_id)

    assert_snapshot_matches_ground_truth(snapshot, case["ground_truth"])
