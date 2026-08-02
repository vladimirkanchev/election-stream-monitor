"""Shared helpers for end-to-end session tests.

These helpers keep the E2E files focused on scenario intent:
- lightweight local-session smoke coverage
- curated real-media integration checks
- broader ground-truth matrix verification

This module is intentionally practical. It owns repeated setup and snapshot
assertion helpers, but it does not try to hide scenario meaning behind a
test-specific framework. Ground-truth assertion failures can emit bounded,
sanitized diagnostics; fixture and lane policy remains in the validation docs.
"""

import json
import os
import re
import subprocess
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

import config
import processor
import session_runner
from session_io import read_session_snapshot
from stores import BufferedCsvStore

GROUND_TRUTH_PATH = Path(__file__).parent / "fixtures" / "media" / "ground_truth.json"
GROUND_TRUTH_ARTIFACT_DIR_ENV = "ESM_GROUND_TRUTH_ARTIFACT_DIR"
_MAX_DIAGNOSTIC_RESULTS = 24
_MAX_DIAGNOSTIC_ALERTS = 24
_MAX_DIAGNOSTIC_BYTES = 64 * 1024


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
    return json.loads(GROUND_TRUTH_PATH.read_text(encoding="utf-8"))[key]


def ground_truth_diagnostic_context(
    case: Mapping[str, object],
    *,
    fixture_id: str | None = None,
    subset_name: str | None = None,
    subset_indices: Sequence[int] = (),
) -> dict[str, object]:
    """Build safe case context for a failure report without retaining raw paths."""
    fixture = case.get("fixture")
    fixture_mapping = fixture if isinstance(fixture, Mapping) else {}
    fixture_kind = str(fixture_mapping.get("kind", "synthetic"))
    if fixture_id is None:
        reference = fixture_mapping.get("path") or fixture_mapping.get("factory")
        fixture_id = Path(str(reference)).name if reference else str(case["id"])

    return {
        "case_id": str(case["id"]),
        "mode": str(case.get("mode", "unknown")),
        "fixture_id": fixture_id,
        "fixture_kind": fixture_kind,
        "subset_name": subset_name or "full_fixture",
        "subset_indices": list(subset_indices),
        "selected_detectors": list(case.get("selected_detectors", ())),
    }


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


def _unexpected_alerts(
    actual_alerts: list[dict[str, object]],
    expected_alerts: list[dict[str, object]],
) -> list[dict[str, object]]:
    """Return alerts outside the ordered expected sequence."""
    expected_index = 0
    extras: list[dict[str, object]] = []
    for alert in actual_alerts:
        if (
            expected_index < len(expected_alerts)
            and alert == expected_alerts[expected_index]
        ):
            expected_index += 1
        else:
            extras.append(alert)

    if expected_index < len(expected_alerts):
        raise AssertionError(
            f"Missing expected alert sequence entry: {expected_alerts[expected_index]!r}"
        )
    return extras


def assert_expected_alerts_with_optional_video_metrics_extra(
    actual_alerts: list[dict[str, object]],
    expected_alerts: list[dict[str, object]],
) -> None:
    """Allow at most one extra `video_metrics` alert without reordering truth."""
    unmatched_alerts = _unexpected_alerts(actual_alerts, expected_alerts)
    assert len(unmatched_alerts) <= 1, (
        f"Expected at most one additional video_metrics alert, got {unmatched_alerts!r}"
    )
    assert all(
        alert["detector_id"] == "video_metrics" for alert in unmatched_alerts
    ), f"Unexpected alert variance: {unmatched_alerts!r}"


def assert_detector_truth_counts(
    snapshot: dict[str, object],
    expected_counts: dict[str, int],
    *,
    allow_video_metrics_count_variance: bool,
) -> None:
    """Assert truth counts with the reviewed MP4 black-detection allowance."""
    actual_counts = _count_detector_truths(snapshot, expected_counts)
    for detector_id, expected_count in expected_counts.items():
        actual_count = actual_counts[detector_id]
        if allow_video_metrics_count_variance and detector_id == "video_metrics":
            if expected_count == 0:
                assert actual_count == 0, (
                    f"Expected {detector_id} truth count {expected_count}, got {actual_count}"
                )
                continue

            assert expected_count <= actual_count <= expected_count + 1, (
                f"Expected {detector_id} truth count in [{expected_count}, {expected_count + 1}], "
                f"got {actual_count}"
            )
            continue

        assert actual_count == expected_count, (
            f"Expected {detector_id} truth count {expected_count}, got {actual_count}"
        )


def _command_version(command: str) -> str | None:
    """Return a command version line without exposing its executable path."""
    try:
        completed = subprocess.run(
            [command, "-version"],
            capture_output=True,
            check=False,
            text=True,
            timeout=2,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return completed.stdout.partition("\n")[0].strip() or None


def _environment_versions() -> dict[str, str | None]:
    """Return the small runtime-version set relevant to media decoding."""
    try:
        import cv2
    except ImportError:
        cv2_version = None
    else:
        cv2_version = str(cv2.__version__)

    return {
        "python": sys.version.split()[0],
        "ffmpeg": _command_version("ffmpeg"),
        "ffprobe": _command_version("ffprobe"),
        "opencv": cv2_version,
    }


def _compact_alerts(alerts: list[dict[str, object]]) -> list[dict[str, object]]:
    """Keep only stable, non-path alert fields in a failure diagnostic."""
    return [
        {
            "detector_id": alert.get("detector_id"),
            "window_index": alert.get("window_index"),
            "window_start_sec": alert.get("window_start_sec"),
        }
        for alert in alerts[:_MAX_DIAGNOSTIC_ALERTS]
    ]


def _compact_results(snapshot: dict[str, object]) -> list[dict[str, object]]:
    """Project result rows to detector facts that help diagnose truth drift."""
    compact_rows: list[dict[str, object]] = []
    for event in snapshot["results"][:_MAX_DIAGNOSTIC_RESULTS]:
        payload = event["payload"]
        compact_row = {"detector_id": event["detector_id"]}
        for field_name in (
            "window_index",
            "window_start_sec",
            "black_detected",
            "blur_detected",
        ):
            if field_name in payload:
                compact_row[field_name] = payload[field_name]
        compact_rows.append(compact_row)
    return compact_rows


def _ground_truth_failure_diagnostic(
    snapshot: dict[str, object],
    expected: dict[str, object],
    context: Mapping[str, object] | None,
) -> dict[str, object]:
    """Build a bounded failure report without full snapshots or raw paths."""
    raw_expected_counts = expected.get("detector_true_counts", {})
    expected_counts = (
        raw_expected_counts if isinstance(raw_expected_counts, dict) else {}
    )
    raw_selected_detectors = context.get("selected_detectors", ()) if context else ()
    selected_detectors = (
        raw_selected_detectors
        if isinstance(raw_selected_detectors, (list, tuple))
        else ()
    )
    detector_ids = {
        detector_id
        for detector_id in (*selected_detectors, *expected_counts)
        if isinstance(detector_id, str)
    }
    return {
        "case": dict(context or {}),
        "detector_ids": sorted(detector_ids),
        "environment": _environment_versions(),
        "expected": {
            "result_count": expected["result_count"],
            "alert_count": expected["alert_count"],
            "detector_true_counts": expected_counts,
            "alerts": _compact_alerts(expected.get("alerts", [])),
            "alerts_truncated": len(expected.get("alerts", []))
            > _MAX_DIAGNOSTIC_ALERTS,
        },
        "actual": {
            "result_count": len(snapshot["results"]),
            "alert_count": len(snapshot["alerts"]),
            "detector_true_counts": _count_detector_truths(snapshot, expected_counts),
            "alerts": _compact_alerts(project_alerts(snapshot)),
            "alerts_truncated": len(snapshot["alerts"]) > _MAX_DIAGNOSTIC_ALERTS,
            "results": _compact_results(snapshot),
            "results_truncated": len(snapshot["results"]) > _MAX_DIAGNOSTIC_RESULTS,
        },
    }


def _emit_ground_truth_failure_diagnostic(
    snapshot: dict[str, object],
    expected: dict[str, object],
    context: Mapping[str, object] | None,
) -> None:
    """Print and optionally persist one sanitized ground-truth failure report."""
    diagnostic = _ground_truth_failure_diagnostic(snapshot, expected, context)
    serialized = json.dumps(diagnostic, sort_keys=True)
    artifact_payload = f"{json.dumps(diagnostic, indent=2, sort_keys=True)}\n"
    if len(artifact_payload.encode()) > _MAX_DIAGNOSTIC_BYTES:
        print("[ground-truth] failure diagnostic omitted: size limit exceeded")
        return
    print(f"[ground-truth] failure diagnostics: {serialized}")

    artifact_dir = os.environ.get(GROUND_TRUTH_ARTIFACT_DIR_ENV, "").strip()
    if not artifact_dir:
        return

    case_id = str(diagnostic["case"].get("case_id", "unknown"))
    artifact_name = re.sub(r"[^A-Za-z0-9_.-]+", "-", case_id).strip("-")
    output_path = Path(artifact_dir) / f"{artifact_name or 'unknown'}.json"
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(artifact_payload, encoding="utf-8")
    except OSError:
        print("[ground-truth] failure artifact could not be persisted")
        return
    print(f"[ground-truth] failure artifact written for case={case_id}")


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
    allow_video_metrics_variance: bool = False,
    diagnostic_context: Mapping[str, object] | None = None,
) -> None:
    """Assert one persisted session snapshot against stored ground truth.

    Covers lifecycle, progress, normalized alerts, and selected payload facts.
    On assertion failure, `diagnostic_context` enables compact sanitized output.
    """
    try:
        assert snapshot["session"]["status"] == expected["session_status"]
        assert snapshot["progress"]["status"] == expected["progress_status"]
        assert snapshot["progress"]["processed_count"] == expected["processed_count"]
        assert len(snapshot["results"]) == expected["result_count"]
        actual_alert_count = len(snapshot["alerts"])
        if allow_video_metrics_variance:
            expected_alert_count = expected["alert_count"]
            assert expected_alert_count <= actual_alert_count <= expected_alert_count + 1, (
                f"Expected alert count in [{expected_alert_count}, "
                f"{expected_alert_count + 1}], got {actual_alert_count}"
            )
        else:
            assert actual_alert_count == expected["alert_count"]
        assert snapshot["progress"]["current_item"] == expected["current_item"]
        assert snapshot["progress"]["latest_result_detectors"] == expected["latest_result_detectors"]

        assert_detector_truth_counts(
            snapshot,
            expected.get("detector_true_counts", {}),
            allow_video_metrics_count_variance=allow_video_metrics_variance,
        )

        expected_alerts = expected.get("alerts")
        if expected_alerts is not None:
            projected_alerts = project_alerts(snapshot)
            if allow_video_metrics_variance:
                assert_expected_alerts_with_optional_video_metrics_extra(
                    projected_alerts,
                    expected_alerts,
                )
            else:
                assert projected_alerts == expected_alerts

        assert_key_results(snapshot, expected.get("key_results", []))
    except AssertionError:
        try:
            _emit_ground_truth_failure_diagnostic(snapshot, expected, diagnostic_context)
        except Exception:
            print("[ground-truth] failure diagnostic could not be generated")
        raise
