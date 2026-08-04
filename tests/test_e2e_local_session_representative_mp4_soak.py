"""Representative MP4 confidence lanes for the real `video_files` seam.

This module separates two kinds of checks:
- capped reviewed subsets that are still reasonable in ordinary slow runs
- broader full-file soak lanes reserved for manual or scheduled validation

The goal is runtime confidence, not detector-by-detector exact truth for every
long media file.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

import session_runner
from tests.e2e_session_test_support import (
    assert_completed_session,
    configure_session_output,
    install_isolated_csv_stores,
    run_and_read_local_session,
)
from tests.representative_hls_test_support import (
    representative_expected_case,
    representative_local_file_path,
    representative_video_file_subset,
    require_representative_local_files,
    run_video_files_subset_session,
)

pytestmark = [pytest.mark.e2e, pytest.mark.slow]

DEFAULT_SOAK_DETECTORS = ["video_metrics"]
BASELINE_FALSE_POSITIVE_DETECTORS = ["video_metrics", "video_blur"]
SOAK_FIXTURE_IDS = (
    "wide_observer__black_strong_start_12s",
    "messy_activity__compression_strong_mid_45s",
    "stable_docs",
)
CAPPED_SOAK_WINDOW_COUNT = 15 * 60
REPEATABILITY_FIXTURE_ID = "stable_docs"
REPEATABILITY_SELECTED_DETECTORS = ["video_metrics", "black_screen"]
MAX_REPEATABILITY_ALERT_DELTA = 1
INTERRUPTION_FIXTURE_ID = "stable_docs"
INTERRUPTION_SELECTED_DETECTORS = ["video_metrics"]
INTERRUPTION_CANCEL_AFTER_RESULT_COUNT = 5
INTERRUPTION_RECOVERY_RERUN_WINDOW_COUNT = 30
BASELINE_FALSE_POSITIVE_FIXTURE_ID = "stable_docs"
BASELINE_FALSE_POSITIVE_EXPECTATION_ID = "stable_docs__source_baseline"
MAX_BASELINE_BLUR_ALERTS = 1


Snapshot = dict[str, Any]


@dataclass(frozen=True)
class SoakRun:
    """Normalized session result shared by representative MP4 assertions."""

    fixture_path: Path
    metadata: Any
    snapshot: Snapshot

    @property
    def processed_count(self) -> int:
        """Return the number of processed windows recorded for the run."""
        return self.snapshot["progress"]["processed_count"]


@dataclass(frozen=True)
class RepresentativeMp4SubsetScenario:
    """Reviewed MP4 subset used by a capped confidence test."""

    fixture_id: str
    subset_name: str
    window_indices: tuple[int, ...]
    selected_detectors: tuple[str, ...]
    expectation_case_id: str | None = None

    @property
    def detector_list(self) -> list[str]:
        """Return the selected detectors in runner-friendly form."""
        return list(self.selected_detectors)

    @property
    def expected_window_count(self) -> int:
        """Return the reviewed window count for the scenario."""
        return len(self.window_indices)


CAPPED_OUTPUT_SHAPE_SCENARIO = RepresentativeMp4SubsetScenario(
    fixture_id="stable_docs",
    subset_name="stable_docs_first_15min_soak_subset",
    window_indices=tuple(range(CAPPED_SOAK_WINDOW_COUNT)),
    selected_detectors=tuple(DEFAULT_SOAK_DETECTORS),
)
CAPPED_FALSE_POSITIVE_GUARD_SCENARIO = RepresentativeMp4SubsetScenario(
    fixture_id=BASELINE_FALSE_POSITIVE_FIXTURE_ID,
    subset_name="stable_docs_first_15min_false_positive_guard_subset",
    window_indices=tuple(range(CAPPED_SOAK_WINDOW_COUNT)),
    selected_detectors=tuple(BASELINE_FALSE_POSITIVE_DETECTORS),
    expectation_case_id=BASELINE_FALSE_POSITIVE_EXPECTATION_ID,
)
CAPPED_POSITIVE_GUARD_SCENARIO = RepresentativeMp4SubsetScenario(
    fixture_id="crowded_ballot__gblur_strong_mid_20s",
    subset_name="crowded_ballot_blur_strong_positive_guard_subset",
    window_indices=tuple(range(20)),
    selected_detectors=tuple(BASELINE_FALSE_POSITIVE_DETECTORS),
    expectation_case_id="crowded_ballot__gblur_strong_mid_20s",
)


def _run_full_representative_mp4_session(
    monkeypatch,
    tmp_path: Path,
    *,
    fixture_id: str,
    selected_detectors: list[str] | None = None,
    session_suffix: str = "default",
) -> SoakRun:
    """Run one full representative MP4 through the production-facing file seam."""
    detectors = selected_detectors or DEFAULT_SOAK_DETECTORS
    configure_session_output(monkeypatch, tmp_path)
    install_isolated_csv_stores(monkeypatch, tmp_path)
    require_representative_local_files(fixture_id)
    input_path = representative_local_file_path(fixture_id)
    metadata, snapshot = run_and_read_local_session(
        mode="video_files",
        input_path=input_path,
        selected_detectors=detectors,
        session_id=f"representative-mp4-soak-{fixture_id}-{session_suffix}",
    )
    return SoakRun(
        fixture_path=input_path,
        metadata=metadata,
        snapshot=snapshot,
    )


def _run_representative_mp4_subset_session(
    monkeypatch,
    tmp_path: Path,
    *,
    fixture_id: str,
    subset_name: str,
    window_indices: list[int],
    selected_detectors: list[str] | None = None,
) -> SoakRun:
    """Run a reviewed MP4 subset through `video_files` without fake transport."""
    detectors = selected_detectors or DEFAULT_SOAK_DETECTORS
    require_representative_local_files(fixture_id)
    fixture_path = representative_local_file_path(fixture_id)
    subset = representative_video_file_subset(
        fixture_id=fixture_id,
        subset_name=subset_name,
        window_indices=window_indices,
    )
    metadata, snapshot = run_video_files_subset_session(
        monkeypatch,
        tmp_path,
        subset=subset,
        selected_detectors=detectors,
    )
    return SoakRun(
        fixture_path=fixture_path,
        metadata=metadata,
        snapshot=snapshot,
    )


def _run_subset_scenario(
    monkeypatch,
    tmp_path: Path,
    *,
    scenario: RepresentativeMp4SubsetScenario,
) -> SoakRun:
    """Run one reviewed subset scenario through the real MP4 session path."""
    return _run_representative_mp4_subset_session(
        monkeypatch,
        tmp_path,
        fixture_id=scenario.fixture_id,
        subset_name=scenario.subset_name,
        window_indices=list(scenario.window_indices),
        selected_detectors=scenario.detector_list,
    )


def _read_metrics_csv_lines(tmp_path: Path) -> list[str]:
    """Return persisted `video_metrics` CSV rows for the current test run."""
    metrics_path = tmp_path / "metrics" / "video_metrics.csv"
    return metrics_path.read_text(encoding="utf-8").strip().splitlines()


def _assert_session_output_contract(tmp_path: Path, run: SoakRun) -> None:
    """Assert the shared persisted-output contract for one representative run."""
    streams_dir = tmp_path / "streams"
    expected_source_groups = {
        run.fixture_path.name,
        run.fixture_path.parent.name,
    }
    csv_lines = _read_metrics_csv_lines(tmp_path)
    latest_payload = run.snapshot["latest_result"]["payload"]
    progress = run.snapshot["progress"]

    assert (tmp_path / "sessions").exists()
    assert len(csv_lines) >= 2
    assert progress["processed_count"] >= 1
    assert len(run.snapshot["results"]) >= progress["processed_count"]
    assert latest_payload["source_group"] in expected_source_groups
    assert progress["current_item"].startswith(latest_payload["source_name"])
    assert len(run.snapshot["alerts"]) <= progress["processed_count"]
    if streams_dir.exists():
        assert not any(streams_dir.iterdir())


def _assert_capped_soak_output_shape(
    tmp_path: Path,
    run: SoakRun,
    *,
    expected_window_count: int,
) -> None:
    """Assert the capped subset output shape used by long-run confidence checks."""
    csv_lines = _read_metrics_csv_lines(tmp_path)

    _assert_session_output_contract(tmp_path, run)
    assert run.processed_count == expected_window_count
    assert run.processed_count >= 10 * 60
    assert len(run.snapshot["results"]) == expected_window_count
    assert len(csv_lines) == expected_window_count + 1
    assert run.snapshot["latest_result"]["payload"]["window_index"] == (
        expected_window_count - 1
    )


def _assert_selected_detector_contract(
    run: SoakRun,
    *,
    selected_detectors: list[str],
) -> None:
    """Assert that session metadata records the detector set honestly."""
    assert run.metadata.selected_detectors == selected_detectors


def _assert_completed_soak_run(
    tmp_path: Path,
    run: SoakRun,
    *,
    selected_detectors: list[str] | None = None,
) -> None:
    """Assert the shared completion contract for successful representative runs."""
    assert_completed_session(run.metadata, run.snapshot)
    assert run.snapshot["progress"]["status"] == "completed"
    if selected_detectors is not None:
        _assert_selected_detector_contract(
            run,
            selected_detectors=selected_detectors,
        )
    _assert_session_output_contract(tmp_path, run)


def _assert_repeatability_smoke_contract(
    first_run: SoakRun,
    second_run: SoakRun,
    *,
    selected_detectors: list[str],
) -> None:
    """Assert that two long runs stay within the same broad runtime envelope."""
    _assert_selected_detector_contract(
        first_run,
        selected_detectors=selected_detectors,
    )
    _assert_selected_detector_contract(
        second_run,
        selected_detectors=selected_detectors,
    )
    assert first_run.snapshot["progress"]["status"] == (
        second_run.snapshot["progress"]["status"]
    )
    assert first_run.snapshot["progress"]["status"] == "completed"
    assert first_run.processed_count == second_run.processed_count
    assert first_run.snapshot["latest_result"]["payload"]["source_group"] == (
        first_run.fixture_path.name
    )
    assert second_run.snapshot["latest_result"]["payload"]["source_group"] == (
        second_run.fixture_path.name
    )
    assert (
        abs(len(first_run.snapshot["alerts"]) - len(second_run.snapshot["alerts"]))
        <= MAX_REPEATABILITY_ALERT_DELTA
    )


def _assert_partial_cancelled_soak_contract(
    tmp_path: Path,
    run: SoakRun,
) -> None:
    """Assert that a cancelled run leaves honest and readable partial output."""
    csv_lines = _read_metrics_csv_lines(tmp_path)

    _assert_session_output_contract(tmp_path, run)
    assert run.snapshot["session"]["status"] == "cancelled"
    assert run.snapshot["progress"]["status"] == "cancelled"
    assert run.snapshot["progress"]["status_reason"] == "cancel_requested"
    assert run.processed_count >= INTERRUPTION_CANCEL_AFTER_RESULT_COUNT
    assert len(run.snapshot["results"]) == run.processed_count
    assert len(csv_lines) == run.processed_count + 1


def _count_alerts_by_detector(snapshot: Snapshot, detector_id: str) -> int:
    """Count persisted alerts for one detector inside a session snapshot."""
    return sum(1 for alert in snapshot["alerts"] if alert["detector_id"] == detector_id)


def _assert_long_baseline_false_positive_guard(
    run: SoakRun,
    *,
    expectation_case_id: str,
) -> None:
    """Assert the current false-positive posture for a long clean baseline.

    The representative catalog still records the source baseline as ideally
    blur-negative. The broader full-file soak run currently allows one blur
    alert so we can detect regressions before tuning without pretending the
    detector is already perfectly calibrated on the long clean source.
    """
    expected_case = representative_expected_case(expectation_case_id)
    expected = expected_case["expected"]
    black_alert_count = _count_alerts_by_detector(run.snapshot, "black_screen")
    blur_alert_count = _count_alerts_by_detector(run.snapshot, "video_blur")

    assert expected["black_screen_alert"] == "not_expected"
    assert black_alert_count == 0

    assert expected["blur_alert"] == "not_expected"
    assert blur_alert_count <= MAX_BASELINE_BLUR_ALERTS


def _assert_expected_positive_alert_present(
    run: SoakRun,
    *,
    expectation_case_id: str,
) -> None:
    """Assert that a reviewed strong-positive window emits its expected alert."""
    expected_case = representative_expected_case(expectation_case_id)
    expected = expected_case["expected"]

    if expected["black_screen_alert"] == "expected":
        assert _count_alerts_by_detector(run.snapshot, "black_screen") >= 1
    if expected["blur_alert"] == "expected":
        assert _count_alerts_by_detector(run.snapshot, "video_blur") >= 1


def _install_cancel_after_n_bundle_calls(
    monkeypatch,
    *,
    target_session_id: str,
    cancel_after_call_count: int,
) -> None:
    """Install a test-only cancellation hook after a chosen analyzer-bundle call."""
    real_bundle_runner = session_runner.run_enabled_analyzers_bundle
    observed_calls = {"count": 0}

    def cancelling_bundle_runner(
        file_path: Path,
        prefix: str,
        mode: str,
        session_id: str,
        selected_analyzers: set[str] | None = None,
        persist_to_store: bool = True,
    ) -> dict[str, list[dict[str, object]]]:
        bundle = real_bundle_runner(
            file_path=file_path,
            prefix=prefix,
            mode=mode,
            session_id=session_id,
            selected_analyzers=selected_analyzers,
            persist_to_store=persist_to_store,
        )
        if session_id != target_session_id:
            return bundle

        observed_calls["count"] += 1
        if observed_calls["count"] == cancel_after_call_count:
            from session_io import request_session_cancel

            request_session_cancel(session_id)
        return bundle

    monkeypatch.setattr(
        session_runner,
        "run_enabled_analyzers_bundle",
        cancelling_bundle_runner,
    )


@pytest.mark.parametrize(
    "fixture_id",
    SOAK_FIXTURE_IDS,
    ids=lambda fixture_id: fixture_id,
)
@pytest.mark.soak
def test_representative_full_mp4_soak_smoke_completes_with_readable_outputs(
    fixture_id: str,
    monkeypatch,
    tmp_path: Path,
    ffmpeg_available,
) -> None:
    """Selected representative MP4s should satisfy broad full-file runtime contracts."""
    _ = ffmpeg_available
    run = _run_full_representative_mp4_session(
        monkeypatch,
        tmp_path,
        fixture_id=fixture_id,
    )

    _assert_completed_soak_run(tmp_path, run)


def test_representative_capped_mp4_soak_keeps_emitting_results_with_sane_output_shape(
    monkeypatch,
    tmp_path: Path,
    ffmpeg_available,
) -> None:
    """The first 15 minutes of a long representative MP4 should stay output-stable.

    This lane is cheaper than the dedicated full-file soak run, but still long
    enough to prove that the real `video_files` seam keeps making progress,
    keeps emitting detector results, and does not drift into an unhealthy
    persisted output shape.
    """
    _ = ffmpeg_available
    run = _run_subset_scenario(
        monkeypatch,
        tmp_path,
        scenario=CAPPED_OUTPUT_SHAPE_SCENARIO,
    )

    _assert_completed_soak_run(
        tmp_path,
        run,
        selected_detectors=CAPPED_OUTPUT_SHAPE_SCENARIO.detector_list,
    )
    _assert_capped_soak_output_shape(
        tmp_path,
        run,
        expected_window_count=CAPPED_OUTPUT_SHAPE_SCENARIO.expected_window_count,
    )


def test_representative_capped_mp4_false_positive_guard_stays_within_tolerance(
    monkeypatch,
    tmp_path: Path,
    ffmpeg_available,
) -> None:
    """A capped clean representative MP4 window should stay within alert tolerance."""
    _ = ffmpeg_available
    run = _run_subset_scenario(
        monkeypatch,
        tmp_path,
        scenario=CAPPED_FALSE_POSITIVE_GUARD_SCENARIO,
    )

    _assert_completed_soak_run(
        tmp_path,
        run,
        selected_detectors=CAPPED_FALSE_POSITIVE_GUARD_SCENARIO.detector_list,
    )
    _assert_long_baseline_false_positive_guard(
        run,
        expectation_case_id=CAPPED_FALSE_POSITIVE_GUARD_SCENARIO.expectation_case_id,
    )


def test_representative_capped_mp4_positive_guard_emits_expected_alert(
    monkeypatch,
    tmp_path: Path,
    ffmpeg_available,
) -> None:
    """A strong reviewed representative MP4 window should emit its expected alert."""
    _ = ffmpeg_available
    run = _run_subset_scenario(
        monkeypatch,
        tmp_path,
        scenario=CAPPED_POSITIVE_GUARD_SCENARIO,
    )

    _assert_completed_soak_run(
        tmp_path,
        run,
        selected_detectors=CAPPED_POSITIVE_GUARD_SCENARIO.detector_list,
    )
    _assert_expected_positive_alert_present(
        run,
        expectation_case_id=CAPPED_POSITIVE_GUARD_SCENARIO.expectation_case_id,
    )


@pytest.mark.soak
def test_representative_full_mp4_repeatability_smoke_keeps_broad_runtime_contract(
    monkeypatch,
    tmp_path: Path,
    ffmpeg_available,
) -> None:
    """One long representative MP4 should stay broadly repeatable across runs."""
    _ = ffmpeg_available
    first_tmp_path = tmp_path / "first"
    second_tmp_path = tmp_path / "second"

    first_run = _run_full_representative_mp4_session(
        monkeypatch,
        first_tmp_path,
        fixture_id=REPEATABILITY_FIXTURE_ID,
        selected_detectors=REPEATABILITY_SELECTED_DETECTORS,
        session_suffix="repeatability-first",
    )
    second_run = _run_full_representative_mp4_session(
        monkeypatch,
        second_tmp_path,
        fixture_id=REPEATABILITY_FIXTURE_ID,
        selected_detectors=REPEATABILITY_SELECTED_DETECTORS,
        session_suffix="repeatability-second",
    )

    _assert_completed_soak_run(
        first_tmp_path,
        first_run,
        selected_detectors=REPEATABILITY_SELECTED_DETECTORS,
    )
    _assert_completed_soak_run(
        second_tmp_path,
        second_run,
        selected_detectors=REPEATABILITY_SELECTED_DETECTORS,
    )
    _assert_repeatability_smoke_contract(
        first_run,
        second_run,
        selected_detectors=REPEATABILITY_SELECTED_DETECTORS,
    )


@pytest.mark.soak
def test_representative_full_mp4_interruption_recovery_smoke_keeps_partial_state_honest(
    monkeypatch,
    tmp_path: Path,
    ffmpeg_available,
) -> None:
    """A long representative MP4 should cancel honestly and still rerun cleanly."""
    _ = ffmpeg_available
    cancelled_tmp_path = tmp_path / "cancelled"
    rerun_tmp_path = tmp_path / "rerun"
    cancel_session_id = "representative-mp4-soak-stable_docs-interrupted"

    _install_cancel_after_n_bundle_calls(
        monkeypatch,
        target_session_id=cancel_session_id,
        cancel_after_call_count=INTERRUPTION_CANCEL_AFTER_RESULT_COUNT,
    )

    cancelled_run = _run_full_representative_mp4_session(
        monkeypatch,
        cancelled_tmp_path,
        fixture_id=INTERRUPTION_FIXTURE_ID,
        selected_detectors=INTERRUPTION_SELECTED_DETECTORS,
        session_suffix="interrupted",
    )

    assert cancelled_run.metadata.session_id == cancel_session_id
    _assert_selected_detector_contract(
        cancelled_run,
        selected_detectors=INTERRUPTION_SELECTED_DETECTORS,
    )
    assert cancelled_run.metadata.status == "cancelled"
    _assert_partial_cancelled_soak_contract(
        cancelled_tmp_path,
        cancelled_run,
    )

    rerun_run = _run_representative_mp4_subset_session(
        monkeypatch,
        rerun_tmp_path,
        fixture_id=INTERRUPTION_FIXTURE_ID,
        subset_name="stable_docs_interruption_recovery_rerun_subset",
        window_indices=list(range(INTERRUPTION_RECOVERY_RERUN_WINDOW_COUNT)),
        selected_detectors=INTERRUPTION_SELECTED_DETECTORS,
    )

    _assert_completed_soak_run(
        rerun_tmp_path,
        rerun_run,
        selected_detectors=INTERRUPTION_SELECTED_DETECTORS,
    )
    assert rerun_run.processed_count == INTERRUPTION_RECOVERY_RERUN_WINDOW_COUNT
    assert rerun_run.processed_count > cancelled_run.processed_count


@pytest.mark.soak
def test_representative_long_baseline_false_positive_guard_stays_negative(
    monkeypatch,
    tmp_path: Path,
    ffmpeg_available,
) -> None:
    """A long clean representative source should stay negative for current alerting."""
    _ = ffmpeg_available
    run = _run_full_representative_mp4_session(
        monkeypatch,
        tmp_path,
        fixture_id=BASELINE_FALSE_POSITIVE_FIXTURE_ID,
        selected_detectors=BASELINE_FALSE_POSITIVE_DETECTORS,
        session_suffix="baseline-false-positive-guard",
    )

    _assert_completed_soak_run(
        tmp_path,
        run,
        selected_detectors=BASELINE_FALSE_POSITIVE_DETECTORS,
    )
    _assert_long_baseline_false_positive_guard(
        run,
        expectation_case_id=BASELINE_FALSE_POSITIVE_EXPECTATION_ID,
    )
