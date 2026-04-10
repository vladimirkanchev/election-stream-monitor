"""Ground-truth session tests for real media and synthetic api-stream contracts."""

import json
from pathlib import Path

import pytest

import config
import processor
import session_runner
from analyzer_contract import AnalysisSlice, AnalyzerRegistration
from session_io import read_session_snapshot
from session_runner import run_local_session
from stores import BufferedCsvStore
from stream_loader import FakeApiStreamEvent, FakeApiStreamLoader


GROUND_TRUTH_PATH = Path(__file__).parent / "fixtures" / "media" / "ground_truth.json"
GROUND_TRUTH = json.loads(GROUND_TRUTH_PATH.read_text(encoding="utf-8"))
LOCAL_SESSION_CASES = GROUND_TRUTH["local_session_cases"]
SIMULATED_API_STREAM_CASES = GROUND_TRUTH["simulated_api_stream_cases"]


class DummyStore:
    """Minimal in-memory store for synthetic api-stream contract tests."""

    def __init__(self) -> None:
        self.rows: list[dict[str, object]] = []

    def add_row(self, row: dict[str, object]) -> None:
        self.rows.append(row)


def _install_isolated_csv_stores(monkeypatch, tmp_path: Path) -> None:
    """Redirect real-media detector output into per-test CSV stores."""
    video_store = BufferedCsvStore(
        columns=config.VIDEO_METRICS_COLUMNS,
        file_path=tmp_path / "metrics" / "video_metrics.csv",
        buffer_size=1,
    )
    blur_store = BufferedCsvStore(
        columns=config.BLUR_METRICS_COLUMNS,
        file_path=tmp_path / "metrics" / "blur_metrics.csv",
        buffer_size=1,
    )

    monkeypatch.setattr(
        processor,
        "STORE_REGISTRY",
        {
            "video_metrics": video_store,
            "blur_metrics": blur_store,
        },
    )
    monkeypatch.setattr(session_runner, "black_frame_store", video_store)
    monkeypatch.setattr(session_runner, "blur_metrics_store", blur_store)


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
    monkeypatch.setattr("session_runner.black_frame_store.flush", lambda: None)
    monkeypatch.setattr("session_runner.blur_metrics_store.flush", lambda: None)


def _resolve_fixture_path(
    case: dict[str, object],
    *,
    media_fixture_dir: Path,
    media_factory: dict[str, object],
) -> Path:
    fixture = case["fixture"]
    if fixture["kind"] == "checked_in":
        return media_fixture_dir / fixture["path"]

    if fixture["kind"] == "generated":
        factory = media_factory[fixture["factory"]]
        return factory(**fixture.get("params", {}))

    raise ValueError(f"Unsupported fixture kind: {fixture['kind']}")


def _project_alerts(snapshot: dict[str, object]) -> list[dict[str, object]]:
    return [
        {
            "detector_id": alert["detector_id"],
            "source_name": alert["source_name"],
            "window_index": alert["window_index"],
            "window_start_sec": alert["window_start_sec"],
        }
        for alert in snapshot["alerts"]
    ]


def _truth_field(detector_id: str) -> str:
    if detector_id == "video_metrics":
        return "black_detected"
    if detector_id == "video_blur":
        return "blur_detected"
    raise ValueError(f"Unsupported detector for truth counting: {detector_id}")


def _count_detector_truths(
    snapshot: dict[str, object],
    expected_counts: dict[str, int],
) -> dict[str, int]:
    actual: dict[str, int] = {}
    for detector_id in expected_counts:
        field_name = _truth_field(detector_id)
        actual[detector_id] = sum(
            1
            for event in snapshot["results"]
            if event["detector_id"] == detector_id
            and bool(event["payload"].get(field_name))
        )
    return actual


def _assert_expected_alerts_present(
    actual_alerts: list[dict[str, object]],
    expected_alerts: list[dict[str, object]],
) -> None:
    """Assert each expected alert appears in order, allowing extras in between."""
    next_index = 0
    for expected_alert in expected_alerts:
        while next_index < len(actual_alerts) and actual_alerts[next_index] != expected_alert:
            next_index += 1

        assert next_index < len(actual_alerts), (
            f"Missing expected alert sequence entry: {expected_alert!r}"
        )
        next_index += 1


def _assert_detector_truth_counts(
    snapshot: dict[str, object],
    expected_counts: dict[str, int],
    *,
    tolerate_checked_in_mp4_black_variance: bool,
) -> None:
    """Assert detector truth counts, allowing known mp4 blackdetect drift in CI.

    The checked-in `.mp4` fixtures are derived from real source material and can
    shift by one black-positive window on different GitHub-hosted runners even
    when ffmpeg versions are aligned. The `.ts` segment fixtures remain stable,
    so we keep exact matching there.
    """
    actual_counts = _count_detector_truths(snapshot, expected_counts)
    for detector_id, expected_count in expected_counts.items():
        actual_count = actual_counts[detector_id]
        if (
            tolerate_checked_in_mp4_black_variance
            and detector_id == "video_metrics"
        ):
            assert abs(actual_count - expected_count) <= 1, (
                f"Expected {detector_id} truth count within +/-1 of "
                f"{expected_count}, got {actual_count}"
            )
            continue

        assert actual_count == expected_count, (
            f"Expected {detector_id} truth count {expected_count}, got {actual_count}"
        )


def _assert_key_results(
    snapshot: dict[str, object],
    expected_key_results: list[dict[str, object]],
) -> None:
    for expected in expected_key_results:
        matches = [
            event
            for event in snapshot["results"]
            if event["detector_id"] == expected["detector_id"]
            and event["payload"]["source_name"] == expected["source_name"]
        ]
        assert matches, (
            f"Missing result for detector={expected['detector_id']} "
            f"source_name={expected['source_name']}"
        )
        payload = matches[0]["payload"]
        for key, value in expected["payload"].items():
            assert payload.get(key) == value


def _assert_snapshot_matches_ground_truth(
    snapshot: dict[str, object],
    expected: dict[str, object],
    *,
    tolerate_checked_in_mp4_black_variance: bool = False,
) -> None:
    assert snapshot["session"]["status"] == expected["session_status"]
    assert snapshot["progress"]["status"] == expected["progress_status"]
    assert snapshot["progress"]["processed_count"] == expected["processed_count"]
    assert len(snapshot["results"]) == expected["result_count"]
    if tolerate_checked_in_mp4_black_variance:
        assert expected["alert_count"] <= len(snapshot["alerts"]) <= expected["alert_count"] + 1
    else:
        assert len(snapshot["alerts"]) == expected["alert_count"]
    assert snapshot["progress"]["current_item"] == expected["current_item"]
    assert snapshot["progress"]["latest_result_detectors"] == expected["latest_result_detectors"]

    detector_true_counts = expected.get("detector_true_counts", {})
    _assert_detector_truth_counts(
        snapshot,
        detector_true_counts,
        tolerate_checked_in_mp4_black_variance=tolerate_checked_in_mp4_black_variance,
    )

    expected_alerts = expected.get("alerts")
    if expected_alerts is not None:
        projected_alerts = _project_alerts(snapshot)
        if tolerate_checked_in_mp4_black_variance:
            _assert_expected_alerts_present(projected_alerts, expected_alerts)
        else:
            assert projected_alerts == expected_alerts

    _assert_key_results(snapshot, expected.get("key_results", []))


def _make_live_slices(
    tmp_path: Path,
    *,
    source_group: str,
    names: list[str],
) -> list[AnalysisSlice]:
    live_dir = tmp_path / source_group
    live_dir.mkdir(parents=True, exist_ok=True)
    slices: list[AnalysisSlice] = []
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


def _make_live_loader_events(slices: list[AnalysisSlice]) -> list[FakeApiStreamEvent]:
    """Translate synthetic slices into fake-loader chunk events."""
    return [
        FakeApiStreamEvent(
            kind="chunk",
            chunk_index=analysis_slice.window_index,
            current_item=analysis_slice.source_name,
            file_path=analysis_slice.file_path,
            window_start_sec=analysis_slice.window_start_sec,
            window_duration_sec=analysis_slice.window_duration_sec,
        )
        for analysis_slice in slices
    ]


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


@pytest.mark.parametrize("case", LOCAL_SESSION_CASES, ids=lambda case: case["id"])
def test_local_session_ground_truth_with_real_fixtures(
    case: dict[str, object],
    monkeypatch,
    tmp_path: Path,
    media_factory,
    media_fixture_dir: Path,
) -> None:
    """Real checked-in and generated media fixtures should match stored session truth."""
    monkeypatch.setattr(config, "SESSION_OUTPUT_FOLDER", tmp_path / "sessions")
    _install_isolated_csv_stores(monkeypatch, tmp_path)

    input_path = _resolve_fixture_path(
        case,
        media_fixture_dir=media_fixture_dir,
        media_factory=media_factory,
    )

    metadata = run_local_session(
        mode=case["mode"],
        input_path=input_path,
        selected_detectors=case["selected_detectors"],
        session_id=f"ground-truth-{case['id']}",
    )

    snapshot = read_session_snapshot(metadata.session_id)
    tolerate_checked_in_mp4_black_variance = (
        case["mode"] == "video_files"
        and case["fixture"]["kind"] == "checked_in"
    )

    assert metadata.status == case["ground_truth"]["session_status"]
    _assert_snapshot_matches_ground_truth(
        snapshot,
        case["ground_truth"],
        tolerate_checked_in_mp4_black_variance=tolerate_checked_in_mp4_black_variance,
    )


@pytest.mark.parametrize("case", SIMULATED_API_STREAM_CASES, ids=lambda case: case["id"])
def test_synthetic_api_stream_session_contract_matches_ground_truth(
    case: dict[str, object],
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Synthetic api-stream cases should match persisted contract expectations."""
    monkeypatch.setattr(config, "SESSION_OUTPUT_FOLDER", tmp_path / "sessions")
    _install_dummy_stores(monkeypatch)
    _patch_api_stream_detectors(monkeypatch, case["detectors"])

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

    original_bundle = session_runner.run_enabled_analyzers_bundle
    failure_window = case.get("bundle_failure_at_window")
    if failure_window is not None:
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

    session_id = f"ground-truth-{case['id']}"
    expected_exception = case.get("expected_exception")
    if expected_exception is None:
        metadata = run_local_session(
            mode="api_stream",
            input_path=case["input_path"],
            selected_detectors=case["selected_detectors"],
            session_id=session_id,
        )
        assert metadata.status == case["ground_truth"]["session_status"]
    else:
        with pytest.raises(ValueError, match=expected_exception["message"]):
            run_local_session(
                mode="api_stream",
                input_path=case["input_path"],
                selected_detectors=case["selected_detectors"],
                session_id=session_id,
            )

    snapshot = read_session_snapshot(session_id)
    _assert_snapshot_matches_ground_truth(snapshot, case["ground_truth"])
