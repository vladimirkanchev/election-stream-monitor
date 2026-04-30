"""Shared helpers for end-to-end session tests.

These helpers keep the E2E files focused on scenario intent:
- lightweight local-session smoke coverage
- curated real-media integration checks
- broader ground-truth matrix verification

This module is intentionally practical. It owns repeated setup and snapshot
assertion helpers, but it does not try to hide scenario meaning behind a
test-specific framework.
"""

from pathlib import Path

import config
import processor
import session_runner
from session_io import read_session_snapshot
from stores import BufferedCsvStore

GROUND_TRUTH_PATH = Path(__file__).parent / "fixtures" / "media" / "ground_truth.json"


def configure_session_output(monkeypatch, tmp_path: Path) -> None:
    """Redirect persisted session state into a test-local output folder.

    The E2E suites should never write into the real default session directory.
    """
    monkeypatch.setattr(config, "SESSION_OUTPUT_FOLDER", tmp_path / "sessions")


def install_isolated_csv_stores(monkeypatch, tmp_path: Path) -> None:
    """Redirect detector persistence into per-test CSV stores.

    Real-media E2E runs should keep detector output isolated so one test does
    not influence another test's persisted rows or flush timing.
    """
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


def run_and_read_local_session(
    *,
    mode: str,
    input_path: Path,
    selected_detectors: list[str],
    session_id: str | None = None,
):
    """Run one local session and return both metadata and the persisted snapshot."""
    metadata = session_runner.run_local_session(
        mode=mode,
        input_path=input_path,
        selected_detectors=selected_detectors,
        session_id=session_id,
    )
    snapshot = read_session_snapshot(metadata.session_id)
    return metadata, snapshot


def assert_completed_session(metadata, snapshot: dict[str, object]) -> None:
    """Assert the common completed-state contract for local session runs."""
    assert metadata.status == "completed"
    assert snapshot["session"]["status"] == "completed"


def load_ground_truth_cases(key: str) -> list[dict[str, object]]:
    """Load one named ground-truth case list from the checked-in fixture file.

    The ground-truth files are intentionally data-driven so the scenario matrix
    stays readable in test code while the stable expectations live in JSON.
    """
    import json

    return json.loads(GROUND_TRUTH_PATH.read_text(encoding="utf-8"))[key]


def resolve_fixture_path(
    case: dict[str, object],
    *,
    media_fixture_dir: Path,
    media_factory: dict[str, object],
) -> Path:
    """Resolve one checked-in or generated media fixture path from ground truth."""
    fixture = case["fixture"]
    if fixture["kind"] == "checked_in":
        return media_fixture_dir / fixture["path"]

    if fixture["kind"] == "generated":
        factory = media_factory[fixture["factory"]]
        return factory(**fixture.get("params", {}))

    raise ValueError(f"Unsupported fixture kind: {fixture['kind']}")


def project_alerts(snapshot: dict[str, object]) -> list[dict[str, object]]:
    """Project alerts down to the stable fields used by ground-truth cases."""
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


def assert_expected_alerts_present(
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


def assert_detector_truth_counts(
    snapshot: dict[str, object],
    expected_counts: dict[str, int],
    *,
    tolerate_checked_in_mp4_black_variance: bool,
) -> None:
    """Assert detector truth counts, allowing known mp4 blackdetect drift in CI."""
    actual_counts = _count_detector_truths(snapshot, expected_counts)
    for detector_id, expected_count in expected_counts.items():
        actual_count = actual_counts[detector_id]
        if tolerate_checked_in_mp4_black_variance and detector_id == "video_metrics":
            if expected_count == 0:
                assert actual_count == 0, (
                    f"Expected {detector_id} truth count {expected_count}, got {actual_count}"
                )
                continue

            assert 1 <= actual_count <= expected_count + 1, (
                f"Expected {detector_id} truth count in [1, {expected_count + 1}], "
                f"got {actual_count}"
            )
            continue

        assert actual_count == expected_count, (
            f"Expected {detector_id} truth count {expected_count}, got {actual_count}"
        )


def assert_key_results(
    snapshot: dict[str, object],
    expected_key_results: list[dict[str, object]],
) -> None:
    """Assert a compact set of detector/source payload expectations."""
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


def assert_snapshot_matches_ground_truth(
    snapshot: dict[str, object],
    expected: dict[str, object],
    *,
    tolerate_checked_in_mp4_black_variance: bool = False,
) -> None:
    """Assert one persisted session snapshot against a stored ground-truth case.

    The helper keeps the cross-file E2E suites aligned on the same contract:
    session lifecycle, progress shape, alert projection, and a few key payload
    fields that identify the important behavioral edges.
    """
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

    assert_detector_truth_counts(
        snapshot,
        expected.get("detector_true_counts", {}),
        tolerate_checked_in_mp4_black_variance=tolerate_checked_in_mp4_black_variance,
    )

    expected_alerts = expected.get("alerts")
    if expected_alerts is not None:
        projected_alerts = project_alerts(snapshot)
        if tolerate_checked_in_mp4_black_variance:
            assert_expected_alerts_present(projected_alerts, expected_alerts)
        else:
            assert projected_alerts == expected_alerts

    assert_key_results(snapshot, expected.get("key_results", []))
