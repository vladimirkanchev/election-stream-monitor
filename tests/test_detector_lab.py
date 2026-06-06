"""Detector-lab tests for experiment families, practical alerts, and runner wiring.

The production runtime stays intentionally small, so this file carries most of
the comparison-oriented coverage for:

- blur-experiment variants and motion/flow exports
- practical lab-only alert policies
- detector-lab CLI, batch runner, and export contracts

The real-fixture motion/flow checks are intentionally slower and belong to the
confidence lane rather than the fast inner-loop detector/rule slice.
"""

from __future__ import annotations

import csv
from pathlib import Path
from types import SimpleNamespace

import pytest

from analyzer_contract import AnalysisSlice
from detector_lab.algorithms import DEFAULT_ALGORITHM_IDS, LabAlgorithmSpec
from detector_lab.blur_experiments import (
    BlurAnalysisContext,
    MotionCoherenceMetrics,
    OpticalFlowTrace,
    BlurWindowMeasurements,
    _compute_dense_farneback_flow_trace,
    _compute_sparse_lk_flow_trace,
    _empty_flow_trace,
    _optical_flow_export_metrics,
    _optical_flow_motion_blur_score,
    agreement_soft_blend,
    analyze_video_blur_dense_farneback_motion,
    analyze_video_blur_motion_coherent_v1,
    analyze_video_blur_sparse_lk_motion,
    consensus_core_blend,
    compression_robust_blend,
    geometric_core_blend,
    rms_soft_blend,
    structure_relief_blend,
    weighted_soft_blend,
)
from detector_lab.practical_alerts import (
    _BLACK_WINDOW_ROW_CACHE,
    _dark_frame_ratio,
    _prefers_motion_blur_classification,
    PracticalEvaluationContext,
    analyze_practical_black_alert,
    analyze_practical_blur_alert,
    analyze_practical_blur_alert_v2,
    analyze_practical_blur_alert_v3,
    analyze_practical_motion_blur_alert,
    build_experiment_window_facts,
    evaluate_practical_alerts,
)
from detector_lab.cli import (
    _resolve_fixture_set_output_profile,
    _resolve_fixture_set_paths,
    _resolve_split_output_dir,
    build_parser,
)
from detector_lab.contracts import field_names_for_output_profile
from detector_lab.reporting import build_eval_row, build_ground_truth_lookup
from detector_lab.runner import (
    DetectorLabBatchConfig,
    DetectorLabSplitBatchConfig,
    DetectorLabConfig,
    run_detector_lab,
    run_detector_lab_batch,
    run_detector_lab_batch_split,
)
from session_models import AlertEvent


def _fake_slice(tmp_path: Path) -> AnalysisSlice:
    """Build one minimal slice that behaves like a 1-second detector-lab window."""
    media_path = tmp_path / "sample.mp4"
    media_path.write_bytes(b"video")
    return AnalysisSlice(
        file_path=media_path,
        source_group=media_path.name,
        source_name=f"{media_path.name} @ 00:00",
        window_index=0,
        window_start_sec=0.0,
        window_duration_sec=1.0,
    )


def _patch_empty_ground_truth_lookup(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep runner-focused tests off the repo-local ground-truth cache path."""
    monkeypatch.setattr(
        "detector_lab.runner._ground_truth_lookup_for_inputs",
        lambda input_paths: {str(path): "" for path in input_paths},
    )


def test_build_experiment_window_facts_reuses_cached_black_window_rows(
    monkeypatch, tmp_path: Path
) -> None:
    """Repeated fact builds should reuse cached black-window detector rows."""
    media_path = tmp_path / "sample.mp4"
    media_path.write_bytes(b"video")
    analysis_slice = AnalysisSlice(
        file_path=media_path,
        source_group=media_path.name,
        source_name=f"{media_path.name} @ 00:01",
        window_index=1,
        window_start_sec=1.0,
        window_duration_sec=1.0,
    )
    context = _fake_blur_context(tmp_path)
    call_count = 0
    _BLACK_WINDOW_ROW_CACHE.clear()

    def fake_black(**kwargs):  # noqa: ANN003
        nonlocal call_count
        call_count += 1
        return {
            "source_group": kwargs["source_group"],
            "source_name": kwargs["source_name"],
            "processing_sec": 0.02,
            "black_segment_count": 0,
            "total_black_sec": 0.0,
            "longest_black_sec": 0.0,
            "black_ratio": 0.0,
        }

    monkeypatch.setattr("detector_lab.practical_alerts.analyze_video_metrics", fake_black)
    monkeypatch.setattr(
        "detector_lab.practical_alerts.prepare_blur_analysis_context",
        lambda slice_: context,
    )
    monkeypatch.setattr(
        "detector_lab.practical_alerts.compute_motion_coherence_multiscale",
        lambda **kwargs: MotionCoherenceMetrics(
            fine_scale_motion_energy=0.10,
            medium_scale_motion_energy=0.10,
            coarse_scale_motion_energy=0.10,
            motion_persistence=0.10,
            motion_coherence=0.10,
            incoherence_avg=0.10,
            incoherence_scores=[0.10],
        ),
    )

    build_experiment_window_facts(analysis_slice, include_motion=True)
    build_experiment_window_facts(analysis_slice, include_motion=True)

    assert call_count == 3


def test_build_experiment_window_facts_reuses_cached_blur_context(
    monkeypatch, tmp_path: Path
) -> None:
    """Repeated fact builds should reuse prepared blur-analysis context in one evaluation context."""
    analysis_slice = _fake_slice(tmp_path)
    blur_context = _fake_blur_context(tmp_path)
    call_count = 0
    evaluation_context = PracticalEvaluationContext(
        black_window_rows={},
        blur_analysis_contexts={},
        experiment_window_facts={},
    )

    monkeypatch.setattr(
        "detector_lab.practical_alerts.analyze_video_metrics",
        lambda **kwargs: {
            "source_group": kwargs["source_group"],
            "source_name": kwargs["source_name"],
            "processing_sec": 0.02,
            "black_segment_count": 0,
            "total_black_sec": 0.0,
            "longest_black_sec": 0.0,
            "black_ratio": 0.0,
        },
    )

    def fake_prepare(slice_):  # noqa: ANN001
        nonlocal call_count
        call_count += 1
        return blur_context

    monkeypatch.setattr(
        "detector_lab.practical_alerts.prepare_blur_analysis_context",
        fake_prepare,
    )

    build_experiment_window_facts(
        analysis_slice,
        include_motion=False,
        evaluation_context=evaluation_context,
    )
    build_experiment_window_facts(
        analysis_slice,
        include_motion=False,
        evaluation_context=evaluation_context,
    )

    assert call_count == 1


def test_run_detector_lab_writes_csv_rows(monkeypatch, tmp_path: Path) -> None:
    """Lab runs should write one comparable CSV row per detector and window."""
    analysis_slice = _fake_slice(tmp_path)
    _patch_empty_ground_truth_lookup(monkeypatch)

    monkeypatch.setattr(
        "detector_lab.runner._discover_lab_slices",
        lambda mode, input_path: [analysis_slice],
    )

    def fake_blur(**kwargs):  # noqa: ANN003
        return {
            "analyzer": "video_blur",
            "source_type": "video",
            "source_group": kwargs["source_group"],
            "source_name": kwargs["source_name"],
            "window_index": kwargs["window_index"],
            "window_start_sec": kwargs["window_start_sec"],
            "window_duration_sec": kwargs["window_duration_sec"],
            "timestamp_utc": "2026-05-26 09:00:00",
            "processing_sec": 0.01,
            "sample_count": 5,
            "sharpness_p10": 0.1,
            "sharpness_p90": 0.2,
            "motion_mean": 0.16,
            "motion_p90": 0.25,
            "blur_score": 0.91,
            "blur_detected": True,
            "threshold_used": 0.88,
        }

    def fake_black(**kwargs):  # noqa: ANN003
        return {
            "analyzer": "video_metrics",
            "source_type": "video",
            "source_group": kwargs["source_group"],
            "source_name": kwargs["source_name"],
            "window_index": kwargs["window_index"],
            "window_start_sec": kwargs["window_start_sec"],
            "window_duration_sec": kwargs["window_duration_sec"],
            "timestamp_utc": "2026-05-26 09:00:00",
            "processing_sec": 0.02,
            "duration_sec": 1.0,
            "black_detected": False,
            "black_segment_count": 0,
            "total_black_sec": 0.0,
            "longest_black_sec": 0.0,
            "black_ratio": 0.0,
        }

    def fake_alerts(session_id, detector_id, row):  # noqa: ANN001
        _ = (session_id, row)
        if detector_id != "video_blur":
            return []
        return [
            AlertEvent(
                session_id="detector-lab",
                timestamp_utc="2026-05-26 09:00:00",
                detector_id="video_blur",
                title="Blur warning",
                message="sample.mp4 @ 00:00 entered a blurry state.",
                severity="warning",
                source_name="sample.mp4 @ 00:00",
            )
        ]

    monkeypatch.setattr("detector_lab.algorithms.analyze_video_blur", fake_blur)
    monkeypatch.setattr("detector_lab.algorithms.analyze_video_metrics", fake_black)
    monkeypatch.setattr("detector_lab.runner.evaluate_alerts", fake_alerts)

    output_csv = tmp_path / "eval.csv"
    rows = run_detector_lab(
        DetectorLabConfig(
            input_path=analysis_slice.file_path,
            mode="video_files",
            output_csv=output_csv,
        )
    )

    assert len(rows) == 2
    assert rows[0]["algorithm_id"] == "production.video_blur.motion_guard_v1"
    assert rows[0]["alert_count"] == 1
    assert rows[0]["motion_p90"] == 0.25
    assert rows[0]["absolute_blur"] == ""
    assert rows[1]["algorithm_id"] == "production.video_metrics.black_screen_v1"
    assert rows[1]["black_ratio"] == 0.0

    with output_csv.open(encoding="utf-8", newline="") as file_handle:
        csv_rows = list(csv.DictReader(file_handle))

    assert csv_rows[0]["detector_id"] == "video_blur"
    assert csv_rows[0]["rule_detector_id"] == "video_blur"
    assert csv_rows[0]["alert_titles"] == "Blur warning"
    assert csv_rows[1]["detector_id"] == "video_metrics"


def test_detector_lab_cli_parser_defaults() -> None:
    """The CLI should default to local video-file evaluation."""
    parser = build_parser()
    args = parser.parse_args(["--input", "sample.mp4"])

    assert args.input == Path("sample.mp4")
    assert args.fixture_set is None
    assert args.mode == "video_files"
    assert args.algorithms is None
    assert args.detectors is None
    assert args.all_algorithms is False
    assert args.output == Path("detector_lab/output/eval.csv")
    assert args.start_window == 0
    assert args.max_windows is None


def test_detector_lab_cli_accepts_video_file_fixture_set() -> None:
    """The CLI should accept the built-in MP4 fixture batch shortcut."""
    parser = build_parser()
    args = parser.parse_args(["--fixture-set", "test_video_files"])

    assert args.input is None
    assert args.fixture_set == "test_video_files"
    assert args.mode == "video_files"


def test_detector_lab_cli_accepts_normal_baseline_fixture_set_with_split_output() -> None:
    """The CLI should expose the normal-baseline clip set and split-output mode."""
    parser = build_parser()
    args = parser.parse_args(
        ["--fixture-set", "normal_baseline_video_files", "--split-output"]
    )

    assert args.fixture_set == "normal_baseline_video_files"
    assert args.split_output is True


def test_video_file_fixture_set_skips_malformed_mp4_fixture() -> None:
    """The default MP4 batch should include current valid fixtures but skip malformed ones."""
    paths = _resolve_fixture_set_paths("test_video_files")

    names = {path.name for path in paths}
    assert "blur_trigger.mp4" in names
    assert "black_trigger.mp4" in names
    assert "truncated_long.mp4" not in names


def test_normal_baseline_fixture_set_resolves_local_mp4_clips_when_available() -> None:
    """The normal-baseline fixture set should resolve local baseline clips when present."""
    paths = _resolve_fixture_set_paths("normal_baseline_video_files")

    if not paths:
        assert paths == ()
        return

    assert len(paths) == 2
    assert paths[0].name == "010300111_20260419_202346_0000-0030.mp4"
    assert paths[1].name == "010300111_20260419_202346_024430-024500.mp4"


def test_all_video_files_fixture_set_includes_detector_and_available_baseline_mp4_inputs() -> None:
    """The combined fixture set should include detector fixtures plus any local baseline clips."""
    paths = _resolve_fixture_set_paths("all_video_files")
    baseline_paths = _resolve_fixture_set_paths("normal_baseline_video_files")

    names = {path.name for path in paths}
    assert "clean_baseline_long.mp4" in names
    assert {path.name for path in baseline_paths}.issubset(names)


def test_run_detector_lab_can_start_after_given_window(monkeypatch, tmp_path: Path) -> None:
    """Lab runs should be able to skip early windows and start later in a clip."""
    first_slice = _fake_slice(tmp_path)
    _patch_empty_ground_truth_lookup(monkeypatch)
    second_slice = AnalysisSlice(
        file_path=first_slice.file_path,
        source_group=first_slice.source_group,
        source_name=f"{first_slice.file_path.name} @ 00:01",
        window_index=1,
        window_start_sec=1.0,
        window_duration_sec=1.0,
    )

    monkeypatch.setattr(
        "detector_lab.runner._discover_lab_slices",
        lambda mode, input_path: [first_slice, second_slice],
    )

    def fake_blur(**kwargs):  # noqa: ANN003
        return {
            "analyzer": "video_blur",
            "source_type": "video",
            "source_group": kwargs["source_group"],
            "source_name": kwargs["source_name"],
            "window_index": kwargs["window_index"],
            "window_start_sec": kwargs["window_start_sec"],
            "window_duration_sec": kwargs["window_duration_sec"],
            "timestamp_utc": "2026-05-26 09:00:00",
            "processing_sec": 0.01,
            "sample_count": 5,
            "sharpness_p10": 0.1,
            "sharpness_p90": 0.2,
            "motion_mean": 0.16,
            "motion_p90": 0.25,
            "blur_score": 0.91,
            "blur_detected": True,
            "threshold_used": 0.88,
        }

    monkeypatch.setattr("detector_lab.algorithms.analyze_video_blur", fake_blur)
    monkeypatch.setattr("detector_lab.runner.evaluate_alerts", lambda *args: [])

    rows = run_detector_lab(
        DetectorLabConfig(
            input_path=first_slice.file_path,
            mode="video_files",
            output_csv=tmp_path / "eval.csv",
            algorithm_ids=("production.video_blur.motion_guard_v1",),
            start_window=1,
        )
    )

    assert len(rows) == 1
    assert rows[0]["window_index"] == 1
    assert rows[0]["source_name"] == f"{first_slice.file_path.name} @ 00:01"

def test_run_detector_lab_supports_custom_rule_variants(monkeypatch, tmp_path: Path) -> None:
    """Experimental rule variants should run without touching production rules."""
    analysis_slice = _fake_slice(tmp_path)
    _patch_empty_ground_truth_lookup(monkeypatch)

    monkeypatch.setattr(
        "detector_lab.runner._discover_lab_slices",
        lambda mode, input_path: [analysis_slice],
    )

    def fake_runner(slice_: AnalysisSlice) -> dict[str, object]:
        return {
            "source_group": slice_.source_group,
            "source_name": slice_.source_name,
            "window_index": slice_.window_index,
            "window_start_sec": slice_.window_start_sec,
            "window_duration_sec": slice_.window_duration_sec,
            "blur_score": 0.91,
        }

    def fake_rule(session_id: str, row: dict[str, object]) -> list[AlertEvent]:
        assert session_id == "detector-lab:experimental.video_blur.rule_v2"
        return [
            AlertEvent(
                session_id=session_id,
                timestamp_utc="2026-05-26 09:00:00",
                detector_id="video_blur",
                title="Experimental blur warning",
                message=f"{row['source_name']} matched custom blur rule.",
                severity="warning",
                source_name=str(row["source_name"]),
            )
        ]

    custom_spec = LabAlgorithmSpec(
        algorithm_id="experimental.video_blur.rule_v2",
        detector_id="video_blur",
        description="Custom rule experiment.",
        runner=fake_runner,
        alert_rule_runner=fake_rule,
    )
    monkeypatch.setattr(
        "detector_lab.runner.resolve_algorithm_specs",
        lambda algorithm_ids: (custom_spec,),
    )

    rows = run_detector_lab(
        DetectorLabConfig(
            input_path=analysis_slice.file_path,
            mode="video_files",
            output_csv=tmp_path / "eval.csv",
            algorithm_ids=(custom_spec.algorithm_id,),
        )
    )

    assert rows[0]["algorithm_id"] == custom_spec.algorithm_id
    assert rows[0]["rule_detector_id"] == ""
    assert rows[0]["alert_titles"] == "Experimental blur warning"

def test_run_detector_lab_batch_combines_rows_for_multiple_inputs(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Batch runs should produce one combined export across multiple MP4 inputs."""
    first_slice = _fake_slice(tmp_path)
    _patch_empty_ground_truth_lookup(monkeypatch)
    second_path = tmp_path / "sample_two.mp4"
    second_path.write_bytes(b"video")
    second_slice = AnalysisSlice(
        file_path=second_path,
        source_group=second_path.name,
        source_name=f"{second_path.name} @ 00:00",
        window_index=0,
        window_start_sec=0.0,
        window_duration_sec=1.0,
    )

    def fake_discover(mode, input_path):  # noqa: ANN001
        _ = mode
        if input_path == first_slice.file_path:
            return [first_slice]
        return [second_slice]

    monkeypatch.setattr("detector_lab.runner._discover_lab_slices", fake_discover)

    def fake_blur(**kwargs):  # noqa: ANN003
        return {
            "analyzer": "video_blur",
            "source_type": "video",
            "source_group": kwargs["source_group"],
            "source_name": kwargs["source_name"],
            "window_index": kwargs["window_index"],
            "window_start_sec": kwargs["window_start_sec"],
            "window_duration_sec": kwargs["window_duration_sec"],
            "timestamp_utc": "2026-05-26 09:00:00",
            "processing_sec": 0.01,
            "sample_count": 5,
            "sharpness_p10": 0.1,
            "sharpness_p90": 0.2,
            "motion_mean": 0.16,
            "motion_p90": 0.25,
            "blur_score": 0.91,
            "blur_detected": True,
            "threshold_used": 0.88,
        }

    def fake_black(**kwargs):  # noqa: ANN003
        return {
            "analyzer": "video_metrics",
            "source_type": "video",
            "source_group": kwargs["source_group"],
            "source_name": kwargs["source_name"],
            "window_index": kwargs["window_index"],
            "window_start_sec": kwargs["window_start_sec"],
            "window_duration_sec": kwargs["window_duration_sec"],
            "timestamp_utc": "2026-05-26 09:00:00",
            "processing_sec": 0.02,
            "duration_sec": 1.0,
            "black_detected": False,
            "black_segment_count": 0,
            "total_black_sec": 0.0,
            "longest_black_sec": 0.0,
            "black_ratio": 0.0,
        }

    monkeypatch.setattr("detector_lab.algorithms.analyze_video_blur", fake_blur)
    monkeypatch.setattr("detector_lab.algorithms.analyze_video_metrics", fake_black)
    monkeypatch.setattr("detector_lab.runner.evaluate_alerts", lambda *args: [])

    output_csv = tmp_path / "batch_eval.csv"
    rows = run_detector_lab_batch(
        DetectorLabBatchConfig(
            input_paths=(first_slice.file_path, second_path),
            mode="video_files",
            output_csv=output_csv,
        )
    )

    assert len(rows) == 4
    assert output_csv.exists()
    assert {row["input_path"] for row in rows} == {str(first_slice.file_path), str(second_path)}


def test_run_detector_lab_batch_split_writes_one_csv_per_input(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Split fixture-set runs should write one output CSV per configured input."""
    first_slice = _fake_slice(tmp_path)
    _patch_empty_ground_truth_lookup(monkeypatch)
    second_path = tmp_path / "sample_two.mp4"
    second_path.write_bytes(b"video")
    second_slice = AnalysisSlice(
        file_path=second_path,
        source_group=second_path.name,
        source_name=f"{second_path.name} @ 00:00",
        window_index=0,
        window_start_sec=0.0,
        window_duration_sec=1.0,
    )

    def fake_discover(mode, input_path):  # noqa: ANN001
        _ = mode
        if input_path == first_slice.file_path:
            return [first_slice]
        return [second_slice]

    monkeypatch.setattr("detector_lab.runner._discover_lab_slices", fake_discover)

    def fake_blur(**kwargs):  # noqa: ANN003
        return {
            "analyzer": "video_blur",
            "source_type": "video",
            "source_group": kwargs["source_group"],
            "source_name": kwargs["source_name"],
            "window_index": kwargs["window_index"],
            "window_start_sec": kwargs["window_start_sec"],
            "window_duration_sec": kwargs["window_duration_sec"],
            "processing_sec": 0.01,
            "sample_count": 5,
            "sharpness_p10": 0.1,
            "sharpness_p90": 0.2,
            "motion_mean": 0.16,
            "motion_p90": 0.25,
            "blur_score": 0.91,
            "blur_detected": True,
            "threshold_used": 0.88,
        }

    monkeypatch.setattr("detector_lab.algorithms.analyze_video_blur", fake_blur)
    monkeypatch.setattr("detector_lab.runner.evaluate_alerts", lambda *args: [])

    output_dir = tmp_path / "split_output"
    outputs = run_detector_lab_batch_split(
        DetectorLabSplitBatchConfig(
            input_paths=(first_slice.file_path, second_path),
            mode="video_files",
            output_dir=output_dir,
            algorithm_ids=("production.video_blur.motion_guard_v1",),
            output_profile="production_fixture_compact",
        )
    )

    assert len(outputs) == 2
    assert (output_dir / "sample_eval.csv").exists()
    assert (output_dir / "sample_two_eval.csv").exists()


def test_run_detector_lab_batch_can_write_compact_production_fixture_csv(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Compact production exports should stay readable and leave experiment-only blur fields blank."""
    analysis_slice = _fake_slice(tmp_path)
    _patch_empty_ground_truth_lookup(monkeypatch)
    monkeypatch.setattr(
        "detector_lab.runner._discover_lab_slices",
        lambda mode, input_path: [analysis_slice],
    )

    def fake_blur(**kwargs):  # noqa: ANN003
        return {
            "analyzer": "video_blur",
            "source_type": "video",
            "source_group": kwargs["source_group"],
            "source_name": kwargs["source_name"],
            "window_index": kwargs["window_index"],
            "window_start_sec": kwargs["window_start_sec"],
            "window_duration_sec": kwargs["window_duration_sec"],
            "processing_sec": 0.01,
            "sample_count": 5,
            "sharpness_p10": 0.1,
            "sharpness_p90": 0.2,
            "motion_mean": 0.16,
            "motion_p90": 0.25,
            "blur_score": 0.91,
            "blur_detected": True,
            "threshold_used": 0.88,
        }

    monkeypatch.setattr("detector_lab.algorithms.analyze_video_blur", fake_blur)
    monkeypatch.setattr("detector_lab.runner.evaluate_alerts", lambda *args: [])

    output_csv = tmp_path / "compact_eval.csv"
    run_detector_lab_batch(
        DetectorLabBatchConfig(
            input_paths=(analysis_slice.file_path,),
            mode="video_files",
            output_csv=output_csv,
            algorithm_ids=("production.video_blur.motion_guard_v1",),
            output_profile="production_fixture_compact",
        )
    )

    with output_csv.open(encoding="utf-8", newline="") as file_handle:
        csv_rows = list(csv.DictReader(file_handle))

    header = list(csv_rows[0].keys())

    assert header == list(field_names_for_output_profile("production_fixture_compact"))
    assert len(csv_rows) == 1
    assert csv_rows[0]["row_index"] == "1"
    assert csv_rows[0]["blur_algorithm_id"] == "production.video_blur.motion_guard_v1"
    assert csv_rows[0]["blur_motion_mean"] == "0.16"
    assert csv_rows[0]["blur_motion_p90"] == "0.25"
    assert csv_rows[0]["blur_absolute_blur"] == ""
    assert csv_rows[0]["blur_multiscale_structure_strength"] == ""
    assert csv_rows[0]["blur_motion_blur_method"] == ""
    assert csv_rows[0]["blur_optical_flow_mean"] == ""
    assert csv_rows[0]["blur_motion_incoherence_penalty"] == ""
    assert csv_rows[0]["blur_blend_id"] == ""
    assert csv_rows[0]["black_algorithm_id"] == ""
    assert "rule_detector_id" not in header
    assert "source_group" not in header
    assert "alert_messages" not in header
    assert "absolute_blur" not in header
    assert "guardrail_reason" not in csv_rows[0]


def test_detector_lab_cli_accepts_algorithm_ids() -> None:
    """The CLI should expose explicit algorithm ids for detector experiments."""
    parser = build_parser()
    args = parser.parse_args(
        [
            "--input",
            "sample.mp4",
            "--algorithms",
            DEFAULT_ALGORITHM_IDS[0],
        ]
    )

    assert args.algorithms == [DEFAULT_ALGORITHM_IDS[0]]


def test_detector_lab_cli_accepts_all_algorithms_shortcut() -> None:
    """The CLI should expose an explicit all-algorithms shortcut."""
    parser = build_parser()
    args = parser.parse_args(
        [
            "--fixture-set",
            "test_video_files",
            "--all-algorithms",
        ]
    )

    assert args.all_algorithms is True
    assert args.algorithms is None
    assert args.detectors is None


def test_field_names_for_output_profile_supports_compact_fixture_exports() -> None:
    """The compact fixture export should stay slimmer than the full experiment CSV."""
    compact_field_names = field_names_for_output_profile("production_fixture_compact")

    assert "rule_detector_id" not in compact_field_names
    assert "source_group" not in compact_field_names
    assert "alert_messages" not in compact_field_names
    assert "absolute_blur" not in compact_field_names
    assert "row_index" in compact_field_names
    assert "blur_algorithm_id" in compact_field_names
    assert "blur_motion_mean" in compact_field_names
    assert "blur_absolute_blur" in compact_field_names
    assert "blur_edge_density" in compact_field_names
    assert "blur_multiscale_structure_strength" in compact_field_names
    assert "blur_motion_blur_method" in compact_field_names
    assert "blur_optical_flow_mean" in compact_field_names
    assert "blur_motion_coherence" in compact_field_names
    assert "blur_blend_id" in compact_field_names
    assert "blur_score" in compact_field_names
    assert "black_algorithm_id" in compact_field_names


def test_fixture_set_output_profile_uses_full_export_for_duplicate_detector_algorithms() -> None:
    """Fixture-set runs should avoid compact merging when detector ids repeat."""
    output_profile = _resolve_fixture_set_output_profile(
        algorithm_ids=(
            "production.video_blur.motion_guard_v1",
            "experimental.video_blur.motion_coherent_v1",
        ),
        resolve_algorithm_specs=lambda ids: tuple(
            LabAlgorithmSpec(
                algorithm_id=algorithm_id,
                detector_id="video_blur",
                description="test",
                runner=lambda analysis_slice: {},  # noqa: ARG005
            )
            for algorithm_id in ids
        ),
    )

    assert output_profile == "full"


def test_fixture_set_output_profile_keeps_compact_export_for_one_algorithm_per_detector() -> None:
    """Fixture-set runs can stay compact when there is only one algorithm per detector."""
    output_profile = _resolve_fixture_set_output_profile(
        algorithm_ids=(
            "production.video_blur.motion_guard_v1",
            "production.video_metrics.black_screen_v1",
        ),
        resolve_algorithm_specs=lambda ids: (
            LabAlgorithmSpec(
                algorithm_id=ids[0],
                detector_id="video_blur",
                description="test",
                runner=lambda analysis_slice: {},  # noqa: ARG005
            ),
            LabAlgorithmSpec(
                algorithm_id=ids[1],
                detector_id="video_metrics",
                description="test",
                runner=lambda analysis_slice: {},  # noqa: ARG005
            ),
        ),
    )

    assert output_profile == "production_fixture_compact"


def test_fixture_set_output_profile_uses_full_export_for_custom_detector_ids() -> None:
    """Custom practical detector ids should force the full export profile."""
    output_profile = _resolve_fixture_set_output_profile(
        algorithm_ids=("practical.blur_alert_v1",),
        resolve_algorithm_specs=lambda ids: (
            LabAlgorithmSpec(
                algorithm_id=ids[0],
                detector_id="practical_blur_alert",
                description="test",
                runner=lambda analysis_slice: {},  # noqa: ARG005
            ),
        ),
    )

    assert output_profile == "full"


def test_split_output_dir_uses_output_stem_as_directory_prefix() -> None:
    """CSV output paths should expand into a sibling directory for split runs."""
    output_dir = _resolve_split_output_dir(
        Path("detector_lab/output/normal_baseline_eval.csv"),
        fixture_set="normal_baseline_video_files",
    )

    assert output_dir == Path(
        "detector_lab/output/normal_baseline_eval_normal_baseline_video_files"
    )


def test_soft_blur_blends_reduce_or_match_hard_max() -> None:
    """Softer blends should not exceed the current hard-max combiner."""
    absolute_blur = 0.93
    dynamic_blur = 0.62

    assert weighted_soft_blend(absolute_blur, dynamic_blur) < max(
        absolute_blur,
        dynamic_blur,
    )
    assert rms_soft_blend(absolute_blur, dynamic_blur) < max(
        absolute_blur,
        dynamic_blur,
    )
    assert agreement_soft_blend(absolute_blur, dynamic_blur) < weighted_soft_blend(
        absolute_blur,
        dynamic_blur,
    )


def test_compression_robust_blend_uses_structure_relief() -> None:
    """The compression-robust blend should drop when structure evidence is healthy."""
    low_structure_score = compression_robust_blend(
        absolute_blur=0.93,
        dynamic_blur=0.62,
        edge_density=0.04,
        mean_edge_strength=0.03,
        texture_energy=0.002,
    )
    high_structure_score = compression_robust_blend(
        absolute_blur=0.93,
        dynamic_blur=0.62,
        edge_density=0.18,
        mean_edge_strength=0.08,
        texture_energy=0.01,
    )

    assert high_structure_score < low_structure_score


def test_generalized_blur_cores_stay_below_hard_max() -> None:
    """Generalized blur cores should be softer than the production hard max."""
    absolute_blur = 0.93
    dynamic_blur = 0.62

    assert geometric_core_blend(absolute_blur, dynamic_blur) < max(
        absolute_blur,
        dynamic_blur,
    )
    assert consensus_core_blend(absolute_blur, dynamic_blur) < max(
        absolute_blur,
        dynamic_blur,
    )


def test_structure_relief_blend_respects_base_blend_choice() -> None:
    """Swapping blur cores should still preserve structure-driven score relief."""
    geometric_score = structure_relief_blend(
        absolute_blur=0.93,
        dynamic_blur=0.62,
        edge_density=0.04,
        mean_edge_strength=0.03,
        texture_energy=0.002,
        base_blend=geometric_core_blend,
    )
    consensus_score = structure_relief_blend(
        absolute_blur=0.93,
        dynamic_blur=0.62,
        edge_density=0.04,
        mean_edge_strength=0.03,
        texture_energy=0.002,
        base_blend=consensus_core_blend,
    )

    assert geometric_score != consensus_score


def test_build_eval_row_includes_ground_truth_summary(tmp_path: Path) -> None:
    """Known checked-in fixtures should carry compact ground-truth context in CSV rows."""
    spec = LabAlgorithmSpec(
        algorithm_id="experimental.video_blur.example_v1",
        detector_id="video_blur",
        description="Example.",
        runner=lambda slice_: {},  # pragma: no cover - not used
    )
    fixture_path = (
        Path("/home/vlad/Projects/election-stream-monitor")
        / "tests/fixtures/media/video_files/blur_middle_long.mp4"
    )
    row = build_eval_row(
        spec=spec,
        input_path=fixture_path,
        ground_truth_summary=build_ground_truth_lookup((fixture_path,))[
            str(fixture_path)
        ],
        row={
            "source_group": fixture_path.name,
            "source_name": fixture_path.name,
            "window_index": 0,
            "window_start_sec": 0.0,
            "window_duration_sec": 1.0,
            "blur_score": 0.9,
        },
        alerts=[],
    )

    assert "mp4_blur_middle_long_dual_detectors" in row["ground_truth_summary"]
    assert "\"expected_blur_true_count\":10" in row["ground_truth_summary"]
    assert "\"per_second_label_legend\":\"0=normal,1=black,2=blur,3=motion_blur,9=unknown\"" in row[
        "ground_truth_summary"
    ]
    assert "\"per_second_labels\":\"0,0,0,2,2,2,0,0,0,0\"" in row["ground_truth_summary"]


def test_build_ground_truth_lookup_persists_stream_summary(tmp_path: Path) -> None:
    """Ground-truth summaries should be cached once per input path and reloaded later."""
    fixture_path = (
        Path("/home/vlad/Projects/election-stream-monitor")
        / "tests/fixtures/media/video_files/blur_middle_long.mp4"
    )
    cache_path = tmp_path / "ground_truth_stream_cache.json"

    first_lookup = build_ground_truth_lookup((fixture_path,), cache_path=cache_path)
    second_lookup = build_ground_truth_lookup((fixture_path,), cache_path=cache_path)

    assert cache_path.exists()
    assert first_lookup[str(fixture_path)] == second_lookup[str(fixture_path)]
    assert "mp4_blur_middle_long_dual_detectors" in first_lookup[str(fixture_path)]
    assert "\"schema_version\": \"ground_truth_summary_v4\"" in cache_path.read_text(encoding="utf-8")


def test_build_ground_truth_lookup_supports_label_only_baseline_clips(tmp_path: Path) -> None:
    """Baseline clips with only per-second labels should still export ground truth."""
    fixture_path = (
        Path("/home/vlad/Projects/election-stream-monitor")
        / "tests/fixtures/media/election_clips/normal_baseline/010300111_20260419_202346_0000-0030.mp4"
    )
    cache_path = tmp_path / "ground_truth_stream_cache.json"

    lookup = build_ground_truth_lookup((fixture_path,), cache_path=cache_path)
    summary = lookup[str(fixture_path)]

    assert "\"per_second_label_legend\":\"0=normal,1=black,2=blur,3=motion_blur,9=unknown\"" in summary
    assert "\"per_second_labels\":\"3,3,3,3,3,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0\"" in summary
    assert "expected_alert_count" not in summary


def _fake_blur_context(tmp_path: Path) -> BlurAnalysisContext:
    """Build one reusable blur context for experiment and practical-alert tests."""
    analysis_slice = _fake_slice(tmp_path)
    measurements = BlurWindowMeasurements(
        frame_scores=[0.12, 0.18, 0.22],
        motion_scores=[0.0, 0.04, 0.06],
        sharpness_p10=0.12,
        sharpness_p90=0.22,
        absolute_blur_scores=[0.88, 0.82, 0.78],
        dynamic_blur_scores=[0.75, 0.8, 0.84],
        edge_density_scores=[0.12, 0.11, 0.1],
        mean_edge_strength_scores=[0.03, 0.03, 0.03],
        texture_energy_scores=[0.005, 0.005, 0.005],
        medium_scale_edge_density_scores=[0.16, 0.16, 0.16],
        coarse_scale_edge_density_scores=[0.22, 0.22, 0.22],
        medium_scale_texture_energy_scores=[0.009, 0.009, 0.009],
        coarse_scale_texture_energy_scores=[0.014, 0.014, 0.014],
        edge_persistence_scores=[0.8, 0.8, 0.8],
        texture_retention_scores=[0.76, 0.76, 0.76],
    )
    return BlurAnalysisContext(
        analysis_slice=analysis_slice,
        display_source_name=analysis_slice.source_name,
        display_source_group=analysis_slice.source_group,
        threshold=0.88,
        start_time=0.0,
        sample_width=4,
        sample_height=4,
        raw_frames=[bytes([0, 1, 2, 3] * 4)] * 3,
        measurements=measurements,
    )


def _fake_motion_blur_measurements(
    *,
    motion_mean: float = 0.16,
    motion_p90: float = 0.22,
    absolute_blur: float = 0.88,
    dynamic_blur: float = 0.82,
    texture_energy: float = 0.20,
) -> SimpleNamespace:
    """Build minimal motion-blur-like measurements for practical policy tests."""
    return SimpleNamespace(
        frame_scores=[0.12, 0.18, 0.22],
        sharpness_p10=0.12,
        sharpness_p90=0.22,
        motion_mean=motion_mean,
        motion_p90=motion_p90,
        absolute_blur_scores=[absolute_blur, absolute_blur, absolute_blur],
        dynamic_blur_scores=[dynamic_blur, dynamic_blur, dynamic_blur],
        texture_energy=texture_energy,
    )


def _practical_black_metrics_row(
    *,
    source_group: str,
    source_name: str,
    black_segment_count: int = 0,
    total_black_sec: float = 0.0,
    longest_black_sec: float = 0.0,
    black_ratio: float = 0.0,
    processing_sec: float = 0.02,
) -> dict[str, object]:
    """Build one black-detector result row in the shape practical alerts consume."""
    return {
        "source_group": source_group,
        "source_name": source_name,
        "processing_sec": processing_sec,
        "black_segment_count": black_segment_count,
        "total_black_sec": total_black_sec,
        "longest_black_sec": longest_black_sec,
        "black_ratio": black_ratio,
    }


def _with_blur_context_measurements(
    context: BlurAnalysisContext,
    *,
    measurements,
    raw_frames: list[bytes] | None = None,
) -> BlurAnalysisContext:
    """Clone a blur context while swapping only measurements or raw-frame samples."""
    return BlurAnalysisContext(
        analysis_slice=context.analysis_slice,
        display_source_name=context.display_source_name,
        display_source_group=context.display_source_group,
        threshold=context.threshold,
        start_time=context.start_time,
        sample_width=context.sample_width,
        sample_height=context.sample_height,
        raw_frames=context.raw_frames if raw_frames is None else raw_frames,
        measurements=measurements,
    )


def _motion_coherence_metrics(
    *,
    fine_scale_motion_energy: float = 0.20,
    medium_scale_motion_energy: float = 0.18,
    coarse_scale_motion_energy: float = 0.15,
    motion_persistence: float = 0.82,
    motion_coherence: float = 0.86,
    incoherence_avg: float = 0.05,
    incoherence_scores: list[float] | None = None,
) -> MotionCoherenceMetrics:
    """Build one motion-coherence payload with readable defaults for policy tests."""
    return MotionCoherenceMetrics(
        fine_scale_motion_energy=fine_scale_motion_energy,
        medium_scale_motion_energy=medium_scale_motion_energy,
        coarse_scale_motion_energy=coarse_scale_motion_energy,
        motion_persistence=motion_persistence,
        motion_coherence=motion_coherence,
        incoherence_avg=incoherence_avg,
        incoherence_scores=[0.05, 0.05] if incoherence_scores is None else incoherence_scores,
    )


def _patch_practical_black_detector(
    monkeypatch: pytest.MonkeyPatch,
    *,
    black_segment_count: int = 0,
    total_black_sec: float = 0.0,
    longest_black_sec: float = 0.0,
    black_ratio: float = 0.0,
    processing_sec: float = 0.02,
) -> None:
    """Patch practical alerts to read a stable black-detector row from the public seam."""
    monkeypatch.setattr(
        "detector_lab.practical_alerts.analyze_video_metrics",
        lambda **kwargs: _practical_black_metrics_row(
            source_group=kwargs["source_group"],
            source_name=kwargs["source_name"],
            black_segment_count=black_segment_count,
            total_black_sec=total_black_sec,
            longest_black_sec=longest_black_sec,
            black_ratio=black_ratio,
            processing_sec=processing_sec,
        ),
    )


def _patch_practical_blur_context(
    monkeypatch: pytest.MonkeyPatch,
    context: BlurAnalysisContext,
) -> None:
    """Patch practical alerts to reuse one prepared blur context via the public seam."""
    monkeypatch.setattr(
        "detector_lab.practical_alerts.prepare_blur_analysis_context",
        lambda slice_: context,
    )


def _patch_practical_motion_metrics(
    monkeypatch: pytest.MonkeyPatch,
    motion_metrics: MotionCoherenceMetrics,
) -> None:
    """Patch practical alerts to reuse one motion-coherence payload via the public seam."""
    monkeypatch.setattr(
        "detector_lab.practical_alerts.compute_motion_coherence_multiscale",
        lambda **kwargs: motion_metrics,
    )


def _fresh_practical_evaluation_context() -> PracticalEvaluationContext:
    """Return one isolated practical-evaluation context for repeated score comparisons."""
    return PracticalEvaluationContext(
        black_window_rows={},
        blur_analysis_contexts={},
        experiment_window_facts={},
    )


def test_sparse_lk_motion_blur_variant_emits_optical_flow_metrics(
    monkeypatch, tmp_path: Path
) -> None:
    """The sparse LK lab variant should export its optical-flow summaries."""
    context = _fake_blur_context(tmp_path)
    monkeypatch.setattr(
        "detector_lab.blur_experiments.prepare_blur_analysis_context",
        lambda slice_: context,
    )
    monkeypatch.setattr(
        "detector_lab.blur_experiments._compute_sparse_lk_flow_trace",
        lambda **kwargs: {
            "flow_mean_scores": [0.0, 0.45, 0.55],
            "flow_p90_scores": [0.0, 0.7, 0.8],
            "flow_coherence_scores": [0.0, 0.85, 0.9],
        },
    )

    row = analyze_video_blur_sparse_lk_motion(context.analysis_slice)

    assert row["motion_blur_method"] == "sparse_lk"
    assert row["optical_flow_mean"] > 0.0
    assert row["optical_flow_p90"] > 0.0
    assert row["optical_flow_coherence"] > 0.0
    assert row["blur_blend_id"] == "sparse_lk"


def test_dense_farneback_motion_blur_variant_emits_optical_flow_metrics(
    monkeypatch, tmp_path: Path
) -> None:
    """The dense Farneback lab variant should export its optical-flow summaries."""
    context = _fake_blur_context(tmp_path)
    monkeypatch.setattr(
        "detector_lab.blur_experiments.prepare_blur_analysis_context",
        lambda slice_: context,
    )
    monkeypatch.setattr(
        "detector_lab.blur_experiments._compute_dense_farneback_flow_trace",
        lambda **kwargs: {
            "flow_mean_scores": [0.0, 0.35, 0.5],
            "flow_p90_scores": [0.0, 0.62, 0.74],
            "flow_coherence_scores": [0.0, 0.78, 0.81],
        },
    )

    row = analyze_video_blur_dense_farneback_motion(context.analysis_slice)

    assert row["motion_blur_method"] == "dense_farneback"
    assert row["optical_flow_mean"] > 0.0


def test_optical_flow_export_metrics_map_trace_exactly() -> None:
    """Optical-flow export fields should summarize the trace with stable formulas."""
    metrics = _optical_flow_export_metrics(
        method="sparse_lk",
        flow_trace=OpticalFlowTrace(
            flow_mean_scores=[0.1, 0.3, 0.5, 0.7],
            flow_p90_scores=[0.1, 0.1, 0.9, 0.9],
            flow_coherence_scores=[0.1, 0.1, 0.9, 0.9],
        ),
    )

    assert metrics["motion_blur_method"] == "sparse_lk"
    assert metrics["optical_flow_mean"] == 0.4
    assert metrics["optical_flow_p90"] == 0.9
    assert metrics["optical_flow_coherence"] == 0.5


def test_optical_flow_export_metrics_fail_closed_for_empty_trace() -> None:
    """Optical-flow export fields should stay zeroed when no trace could be computed."""
    metrics = _optical_flow_export_metrics(
        method="dense_farneback",
        flow_trace=_empty_flow_trace(),
    )

    assert metrics["motion_blur_method"] == "dense_farneback"
    assert metrics["optical_flow_mean"] == 0.0
    assert metrics["optical_flow_p90"] == 0.0
    assert metrics["optical_flow_coherence"] == 0.0


def test_optical_flow_motion_blur_score_increases_with_stronger_flow_support() -> None:
    """Motion-blur score should rise when flow evidence strengthens under fixed softness."""
    weaker = _optical_flow_motion_blur_score(
        absolute_blur=0.9,
        dynamic_blur=0.8,
        optical_flow_mean=0.2,
        optical_flow_p90=0.2,
        optical_flow_coherence=0.2,
    )
    stronger = _optical_flow_motion_blur_score(
        absolute_blur=0.9,
        dynamic_blur=0.8,
        optical_flow_mean=0.7,
        optical_flow_p90=0.8,
        optical_flow_coherence=0.9,
    )

    assert stronger > weaker


def test_optical_flow_motion_blur_score_increases_with_stronger_softness() -> None:
    """Motion-blur score should rise when softness strengthens under fixed flow support."""
    weaker = _optical_flow_motion_blur_score(
        absolute_blur=0.5,
        dynamic_blur=0.45,
        optical_flow_mean=0.7,
        optical_flow_p90=0.8,
        optical_flow_coherence=0.9,
    )
    stronger = _optical_flow_motion_blur_score(
        absolute_blur=0.9,
        dynamic_blur=0.85,
        optical_flow_mean=0.7,
        optical_flow_p90=0.8,
        optical_flow_coherence=0.9,
    )

    assert stronger > weaker


def test_optical_flow_helpers_fail_closed_on_degenerate_low_feature_frames() -> None:
    """Sparse and dense optical-flow helpers should fail closed on flat low-feature frame sequences."""
    pytest.importorskip("cv2")
    flat_frames = [bytes([32] * 64), bytes([32] * 64), bytes([32] * 64)]

    sparse_trace = _compute_sparse_lk_flow_trace(
        width=8,
        height=8,
        raw_frames=flat_frames,
    )
    dense_trace = _compute_dense_farneback_flow_trace(
        width=8,
        height=8,
        raw_frames=flat_frames,
    )

    assert sparse_trace.flow_mean_scores == [0.0, 0.0, 0.0]
    assert sparse_trace.flow_p90_scores == [0.0, 0.0, 0.0]
    assert sparse_trace.flow_coherence_scores == [0.0, 0.0, 0.0]
    assert all(score == 0.0 for score in dense_trace.flow_mean_scores)
    assert all(score == 0.0 for score in dense_trace.flow_p90_scores)


def test_motion_coherent_variant_exports_incoherence_penalty_and_softens_blur_score(
    monkeypatch, tmp_path: Path
) -> None:
    """Motion-coherent blur should export its incoherence penalty and reduce blur strength."""
    context = _fake_blur_context(tmp_path)
    monkeypatch.setattr(
        "detector_lab.blur_experiments.prepare_blur_analysis_context",
        lambda slice_: context,
    )
    monkeypatch.setattr(
        "detector_lab.blur_experiments.compute_motion_coherence_multiscale",
        lambda **kwargs: MotionCoherenceMetrics(
            fine_scale_motion_energy=0.30,
            medium_scale_motion_energy=0.22,
            coarse_scale_motion_energy=0.14,
            motion_persistence=0.58,
            motion_coherence=0.54,
            incoherence_avg=0.50,
            incoherence_scores=[0.50, 0.50, 0.50],
        ),
    )

    row = analyze_video_blur_motion_coherent_v1(context.analysis_slice)
    baseline = max(
        geometric_core_blend(absolute_blur, dynamic_blur)
        for absolute_blur, dynamic_blur in zip(
            context.measurements.absolute_blur_scores,
            context.measurements.dynamic_blur_scores,
            strict=False,
        )
    )

    assert row["blur_blend_id"] == "motion_coherent"
    assert row["motion_incoherence_penalty"] == 0.5
    assert row["fine_scale_motion_energy"] == 0.3
    assert row["motion_coherence"] == 0.54
    assert row["blur_score"] < baseline


def test_motion_coherent_variant_fails_closed_for_empty_incoherence_series(
    monkeypatch, tmp_path: Path
) -> None:
    """Motion-coherent blur should fall back cleanly when incoherence scores are absent."""
    context = _fake_blur_context(tmp_path)
    monkeypatch.setattr(
        "detector_lab.blur_experiments.prepare_blur_analysis_context",
        lambda slice_: context,
    )
    monkeypatch.setattr(
        "detector_lab.blur_experiments.compute_motion_coherence_multiscale",
        lambda **kwargs: MotionCoherenceMetrics(
            fine_scale_motion_energy=0.3,
            medium_scale_motion_energy=0.22,
            coarse_scale_motion_energy=0.14,
            motion_persistence=0.58,
            motion_coherence=0.54,
            incoherence_avg=0.5,
            incoherence_scores=[],
        ),
    )

    row = analyze_video_blur_motion_coherent_v1(context.analysis_slice)
    per_frame_scores = [
        geometric_core_blend(absolute_blur, dynamic_blur)
        for absolute_blur, dynamic_blur in zip(
            context.measurements.absolute_blur_scores,
            context.measurements.dynamic_blur_scores,
            strict=False,
        )
    ]
    baseline_window_score = round(sorted(per_frame_scores)[len(per_frame_scores) // 2], 3)

    assert row["blur_score"] == baseline_window_score
    assert "motion_incoherence_penalty" not in row
    assert "motion_coherence" not in row


def test_motion_coherent_variant_exports_zero_motion_baseline(
    monkeypatch, tmp_path: Path
) -> None:
    """Motion-coherent blur should export zero motion metrics and preserve baseline blur when motion is absent."""
    context = _fake_blur_context(tmp_path)
    monkeypatch.setattr(
        "detector_lab.blur_experiments.prepare_blur_analysis_context",
        lambda slice_: context,
    )
    monkeypatch.setattr(
        "detector_lab.blur_experiments.compute_motion_coherence_multiscale",
        lambda **kwargs: MotionCoherenceMetrics(
            fine_scale_motion_energy=0.0,
            medium_scale_motion_energy=0.0,
            coarse_scale_motion_energy=0.0,
            motion_persistence=0.0,
            motion_coherence=0.0,
            incoherence_avg=0.0,
            incoherence_scores=[0.0, 0.0, 0.0],
        ),
    )

    row = analyze_video_blur_motion_coherent_v1(context.analysis_slice)
    per_frame_scores = [
        geometric_core_blend(absolute_blur, dynamic_blur)
        for absolute_blur, dynamic_blur in zip(
            context.measurements.absolute_blur_scores,
            context.measurements.dynamic_blur_scores,
            strict=False,
        )
    ]
    baseline_window_score = round(sorted(per_frame_scores)[len(per_frame_scores) // 2], 3)

    assert row["fine_scale_motion_energy"] == 0.0
    assert row["medium_scale_motion_energy"] == 0.0
    assert row["coarse_scale_motion_energy"] == 0.0
    assert row["motion_persistence"] == 0.0
    assert row["motion_coherence"] == 0.0
    assert row["motion_incoherence_penalty"] == 0.0
    assert row["blur_score"] == baseline_window_score


def test_motion_coherent_variant_score_drops_as_incoherence_rises(
    monkeypatch, tmp_path: Path
) -> None:
    """Motion-coherent blur should get weaker as motion incoherence increases."""
    context = _fake_blur_context(tmp_path)
    monkeypatch.setattr(
        "detector_lab.blur_experiments.prepare_blur_analysis_context",
        lambda slice_: context,
    )

    low_incoherence = MotionCoherenceMetrics(
        fine_scale_motion_energy=0.30,
        medium_scale_motion_energy=0.22,
        coarse_scale_motion_energy=0.14,
        motion_persistence=0.58,
        motion_coherence=0.54,
        incoherence_avg=0.10,
        incoherence_scores=[0.10, 0.10, 0.10],
    )
    high_incoherence = MotionCoherenceMetrics(
        fine_scale_motion_energy=0.30,
        medium_scale_motion_energy=0.22,
        coarse_scale_motion_energy=0.14,
        motion_persistence=0.58,
        motion_coherence=0.54,
        incoherence_avg=0.70,
        incoherence_scores=[0.70, 0.70, 0.70],
    )

    monkeypatch.setattr(
        "detector_lab.blur_experiments.compute_motion_coherence_multiscale",
        lambda **kwargs: low_incoherence,
    )
    low_row = analyze_video_blur_motion_coherent_v1(context.analysis_slice)

    monkeypatch.setattr(
        "detector_lab.blur_experiments.compute_motion_coherence_multiscale",
        lambda **kwargs: high_incoherence,
    )
    high_row = analyze_video_blur_motion_coherent_v1(context.analysis_slice)

    assert low_row["motion_incoherence_penalty"] == 0.1
    assert high_row["motion_incoherence_penalty"] == 0.7
    assert high_row["blur_score"] < low_row["blur_score"]


def test_practical_black_alert_uses_ratio_first_black_score(monkeypatch, tmp_path: Path) -> None:
    """The practical black alert should trigger on a black-dominant window."""
    analysis_slice = _fake_slice(tmp_path)
    monkeypatch.setattr(
        "detector_lab.practical_alerts.analyze_video_metrics",
        lambda **kwargs: {
            "source_group": kwargs["source_group"],
            "source_name": kwargs["source_name"],
            "processing_sec": 0.02,
            "black_segment_count": 1,
            "total_black_sec": 0.8,
            "longest_black_sec": 0.8,
            "black_ratio": 0.8,
        },
    )

    row = analyze_practical_black_alert(analysis_slice)

    assert row["practical_detected"] is True
    assert row["practical_score"] >= 0.55
    assert row["black_detected"] is True


def test_practical_blur_alert_skips_black_dominant_windows(monkeypatch, tmp_path: Path) -> None:
    """The practical blur alert should stay quiet when the black guardrail trips."""
    analysis_slice = _fake_slice(tmp_path)
    monkeypatch.setattr(
        "detector_lab.practical_alerts.analyze_video_metrics",
        lambda **kwargs: {
            "source_group": kwargs["source_group"],
            "source_name": kwargs["source_name"],
            "processing_sec": 0.02,
            "black_segment_count": 1,
            "total_black_sec": 0.5,
            "longest_black_sec": 0.5,
            "black_ratio": 0.5,
        },
    )
    monkeypatch.setattr(
        "detector_lab.practical_alerts.prepare_blur_analysis_context",
        lambda slice_: _fake_blur_context(tmp_path),
    )

    row = analyze_practical_blur_alert(analysis_slice)

    assert row["practical_detected"] is False
    assert row["guardrail_reason"] == "black_dominant"
    assert row["blur_score"] == 0.0


def test_practical_blur_alert_v2_uses_v2_analyzer_name(monkeypatch, tmp_path: Path) -> None:
    """The calibrated practical blur alert should export a distinct analyzer id."""
    analysis_slice = _fake_slice(tmp_path)
    monkeypatch.setattr(
        "detector_lab.practical_alerts.analyze_video_metrics",
        lambda **kwargs: {
            "source_group": kwargs["source_group"],
            "source_name": kwargs["source_name"],
            "processing_sec": 0.02,
            "black_segment_count": 0,
            "total_black_sec": 0.0,
            "longest_black_sec": 0.0,
            "black_ratio": 0.0,
        },
    )
    monkeypatch.setattr(
        "detector_lab.practical_alerts.prepare_blur_analysis_context",
        lambda slice_: _fake_blur_context(tmp_path),
    )
    monkeypatch.setattr(
        "detector_lab.practical_alerts._prefers_motion_blur_classification",
        lambda **kwargs: False,
    )

    row = analyze_practical_blur_alert_v2(analysis_slice)

    assert row["analyzer"] == "practical_blur_alert_v2"
    assert row["practical_threshold"] == 0.955


def test_practical_blur_alert_v2_can_step_aside_for_motion_blur(
    monkeypatch, tmp_path: Path
) -> None:
    """The calibrated blur alert should step aside when the stricter motion gate trips."""
    analysis_slice = _fake_slice(tmp_path)
    monkeypatch.setattr(
        "detector_lab.practical_alerts.analyze_video_metrics",
        lambda **kwargs: {
            "source_group": kwargs["source_group"],
            "source_name": kwargs["source_name"],
            "processing_sec": 0.02,
            "black_segment_count": 0,
            "total_black_sec": 0.0,
            "longest_black_sec": 0.0,
            "black_ratio": 0.0,
        },
    )
    monkeypatch.setattr(
        "detector_lab.practical_alerts.prepare_blur_analysis_context",
        lambda slice_: _fake_blur_context(tmp_path),
    )
    monkeypatch.setattr(
        "detector_lab.practical_alerts._prefers_motion_blur_classification",
        lambda **kwargs: True,
    )

    row = analyze_practical_blur_alert_v2(analysis_slice)

    assert row["practical_detected"] is False
    assert row["guardrail_reason"] == "prefer_motion_blur"
    assert row["blur_score"] == 0.0


def test_dark_frame_ratio_marks_dark_flat_frames() -> None:
    """Dark low-contrast frames should count toward the dark-frame guardrail."""
    dark_frame = bytes([20] * 16)
    textured_frame = bytes([0, 255] * 8)

    ratio = _dark_frame_ratio([dark_frame, dark_frame, textured_frame])

    assert ratio == 2 / 3


def test_practical_blur_alert_v3_suppresses_dark_frame_windows(
    monkeypatch, tmp_path: Path
) -> None:
    """The v3 blur alert should suppress windows dominated by dark flat frames."""
    analysis_slice = _fake_slice(tmp_path)
    context = _fake_blur_context(tmp_path)
    dark_frame = bytes([18] * 16)
    monkeypatch.setattr(
        "detector_lab.practical_alerts.analyze_video_metrics",
        lambda **kwargs: {
            "source_group": kwargs["source_group"],
            "source_name": kwargs["source_name"],
            "processing_sec": 0.02,
            "black_segment_count": 0,
            "total_black_sec": 0.0,
            "longest_black_sec": 0.0,
            "black_ratio": 0.0,
        },
    )
    monkeypatch.setattr(
        "detector_lab.practical_alerts.prepare_blur_analysis_context",
        lambda slice_: BlurAnalysisContext(
            analysis_slice=context.analysis_slice,
            display_source_name=context.display_source_name,
            display_source_group=context.display_source_group,
            threshold=context.threshold,
            start_time=context.start_time,
            sample_width=4,
            sample_height=4,
            raw_frames=[dark_frame, dark_frame, dark_frame, context.raw_frames[0]],
            measurements=context.measurements,
        ),
    )
    monkeypatch.setattr(
        "detector_lab.practical_alerts._neighbor_black_ratios",
        lambda analysis_slice: (0.0, 0.0),
    )

    row = analyze_practical_blur_alert_v3(analysis_slice)

    assert row["practical_detected"] is False
    assert row["guardrail_reason"] == "dark_frame_dominant"
    assert row["blur_score"] == 0.0


def test_practical_blur_alert_v3_suppresses_at_exact_dark_frame_hard_boundary(
    monkeypatch, tmp_path: Path
) -> None:
    """The v3 blur alert should suppress at the exact hard dark-frame boundary."""
    analysis_slice = _fake_slice(tmp_path)
    context = _fake_blur_context(tmp_path)
    monkeypatch.setattr(
        "detector_lab.practical_alerts.analyze_video_metrics",
        lambda **kwargs: {
            "source_group": kwargs["source_group"],
            "source_name": kwargs["source_name"],
            "processing_sec": 0.02,
            "black_segment_count": 0,
            "total_black_sec": 0.0,
            "longest_black_sec": 0.0,
            "black_ratio": 0.0,
        },
    )
    monkeypatch.setattr(
        "detector_lab.practical_alerts.prepare_blur_analysis_context",
        lambda slice_: context,
    )
    monkeypatch.setattr(
        "detector_lab.practical_alerts._dark_frame_ratio",
        lambda raw_frames: 0.30,
    )
    monkeypatch.setattr(
        "detector_lab.practical_alerts._neighbor_black_ratios",
        lambda analysis_slice: (0.0, 0.0),
    )

    row = analyze_practical_blur_alert_v3(analysis_slice)

    assert row["practical_detected"] is False
    assert row["guardrail_reason"] == "dark_frame_dominant"
    assert row["practical_score"] == 0.0


def test_practical_blur_alert_v3_suppresses_black_dark_transition_windows(
    monkeypatch, tmp_path: Path
) -> None:
    """The v3 blur alert should suppress gray-zone black-plus-dark windows."""
    analysis_slice = _fake_slice(tmp_path)
    context = _fake_blur_context(tmp_path)
    monkeypatch.setattr(
        "detector_lab.practical_alerts.analyze_video_metrics",
        lambda **kwargs: {
            "source_group": kwargs["source_group"],
            "source_name": kwargs["source_name"],
            "processing_sec": 0.02,
            "black_segment_count": 1,
            "total_black_sec": 0.2,
            "longest_black_sec": 0.2,
            "black_ratio": 0.2,
        },
    )
    monkeypatch.setattr(
        "detector_lab.practical_alerts.prepare_blur_analysis_context",
        lambda slice_: context,
    )
    monkeypatch.setattr(
        "detector_lab.practical_alerts._neighbor_black_ratios",
        lambda analysis_slice: (0.0, 0.0),
    )
    monkeypatch.setattr(
        "detector_lab.practical_alerts._dark_frame_ratio",
        lambda raw_frames: 0.25,
    )

    row = analyze_practical_blur_alert_v3(analysis_slice)

    assert row["practical_detected"] is False
    assert row["guardrail_reason"] == "black_dark_transition"
    assert row["blur_score"] == 0.0


def test_practical_blur_alert_v3_suppresses_at_exact_black_dark_mixed_boundary(
    monkeypatch, tmp_path: Path
) -> None:
    """The v3 blur alert should suppress at the exact black-plus-dark mixed boundary."""
    analysis_slice = _fake_slice(tmp_path)
    context = _fake_blur_context(tmp_path)
    monkeypatch.setattr(
        "detector_lab.practical_alerts.analyze_video_metrics",
        lambda **kwargs: {
            "source_group": kwargs["source_group"],
            "source_name": kwargs["source_name"],
            "processing_sec": 0.02,
            "black_segment_count": 1,
            "total_black_sec": 0.15,
            "longest_black_sec": 0.15,
            "black_ratio": 0.15,
        },
    )
    monkeypatch.setattr(
        "detector_lab.practical_alerts.prepare_blur_analysis_context",
        lambda slice_: context,
    )
    monkeypatch.setattr(
        "detector_lab.practical_alerts._neighbor_black_ratios",
        lambda analysis_slice: (0.0, 0.0),
    )
    monkeypatch.setattr(
        "detector_lab.practical_alerts._dark_frame_ratio",
        lambda raw_frames: 0.20,
    )

    row = analyze_practical_blur_alert_v3(analysis_slice)

    assert row["practical_detected"] is False
    assert row["guardrail_reason"] == "black_dark_transition"
    assert row["practical_score"] == 0.0


def test_practical_blur_alert_v3_suppresses_black_neighbor_transition_windows(
    monkeypatch, tmp_path: Path
) -> None:
    """The v3 blur alert should suppress blur-like windows next to strong black windows."""
    analysis_slice = _fake_slice(tmp_path)
    context = _fake_blur_context(tmp_path)
    monkeypatch.setattr(
        "detector_lab.practical_alerts.analyze_video_metrics",
        lambda **kwargs: {
            "source_group": kwargs["source_group"],
            "source_name": kwargs["source_name"],
            "processing_sec": 0.02,
            "black_segment_count": 0,
            "total_black_sec": 0.0,
            "longest_black_sec": 0.0,
            "black_ratio": 0.0,
        },
    )
    monkeypatch.setattr(
        "detector_lab.practical_alerts.prepare_blur_analysis_context",
        lambda slice_: context,
    )
    monkeypatch.setattr(
        "detector_lab.practical_alerts._dark_frame_ratio",
        lambda raw_frames: 0.0,
    )
    monkeypatch.setattr(
        "detector_lab.practical_alerts._neighbor_black_ratios",
        lambda analysis_slice: (0.0, 0.8),
    )

    row = analyze_practical_blur_alert_v3(analysis_slice)

    assert row["practical_detected"] is False
    assert row["guardrail_reason"] == "black_neighbor_transition"
    assert 0.0 < row["blur_score"] < row["practical_threshold"]


def test_practical_blur_alert_v3_applies_hard_neighbor_penalty_at_exact_boundary(
    monkeypatch, tmp_path: Path
) -> None:
    """The v3 blur alert should penalize at the exact hard neighbor-black boundary."""
    analysis_slice = _fake_slice(tmp_path)
    context = _fake_blur_context(tmp_path)
    monkeypatch.setattr(
        "detector_lab.practical_alerts.analyze_video_metrics",
        lambda **kwargs: {
            "source_group": kwargs["source_group"],
            "source_name": kwargs["source_name"],
            "processing_sec": 0.02,
            "black_segment_count": 0,
            "total_black_sec": 0.0,
            "longest_black_sec": 0.0,
            "black_ratio": 0.0,
        },
    )
    monkeypatch.setattr(
        "detector_lab.practical_alerts.prepare_blur_analysis_context",
        lambda slice_: context,
    )
    monkeypatch.setattr(
        "detector_lab.practical_alerts._dark_frame_ratio",
        lambda raw_frames: 0.0,
    )
    monkeypatch.setattr(
        "detector_lab.practical_alerts._prefers_motion_blur_classification",
        lambda **kwargs: False,
    )
    monkeypatch.setattr(
        "detector_lab.practical_alerts._neighbor_black_ratios",
        lambda analysis_slice: (0.0, 0.70),
    )

    row = analyze_practical_blur_alert_v3(analysis_slice)

    assert row["guardrail_reason"] == "black_neighbor_transition"
    assert 0.0 < row["practical_score"] < row["practical_threshold"]


def test_practical_blur_alert_v3_skips_hard_neighbor_penalty_just_below_boundary(
    monkeypatch, tmp_path: Path
) -> None:
    """The v3 blur alert should not penalize when neighbor-black stays just below the hard threshold."""
    analysis_slice = _fake_slice(tmp_path)
    context = _fake_blur_context(tmp_path)
    monkeypatch.setattr(
        "detector_lab.practical_alerts.analyze_video_metrics",
        lambda **kwargs: {
            "source_group": kwargs["source_group"],
            "source_name": kwargs["source_name"],
            "processing_sec": 0.02,
            "black_segment_count": 0,
            "total_black_sec": 0.0,
            "longest_black_sec": 0.0,
            "black_ratio": 0.0,
        },
    )
    monkeypatch.setattr(
        "detector_lab.practical_alerts.prepare_blur_analysis_context",
        lambda slice_: context,
    )
    monkeypatch.setattr(
        "detector_lab.practical_alerts._dark_frame_ratio",
        lambda raw_frames: 0.0,
    )
    monkeypatch.setattr(
        "detector_lab.practical_alerts._prefers_motion_blur_classification",
        lambda **kwargs: False,
    )
    monkeypatch.setattr(
        "detector_lab.practical_alerts._weighted_geometric_blur_core",
        lambda **kwargs: 0.96,
    )
    monkeypatch.setattr(
        "detector_lab.practical_alerts._neighbor_black_ratios",
        lambda analysis_slice: (0.0, 0.699),
    )

    row = analyze_practical_blur_alert_v3(analysis_slice)

    assert row["guardrail_reason"] == ""
    assert row["practical_score"] == 0.96
    assert row["practical_detected"] is True


def test_practical_blur_alert_v3_penalty_can_demote_otherwise_alerting_score(
    monkeypatch, tmp_path: Path
) -> None:
    """Black-neighbor penalty should be able to push an otherwise alerting blur score below threshold."""
    analysis_slice = _fake_slice(tmp_path)
    context = _fake_blur_context(tmp_path)
    monkeypatch.setattr(
        "detector_lab.practical_alerts.analyze_video_metrics",
        lambda **kwargs: {
            "source_group": kwargs["source_group"],
            "source_name": kwargs["source_name"],
            "processing_sec": 0.02,
            "black_segment_count": 0,
            "total_black_sec": 0.0,
            "longest_black_sec": 0.0,
            "black_ratio": 0.0,
        },
    )
    monkeypatch.setattr(
        "detector_lab.practical_alerts.prepare_blur_analysis_context",
        lambda slice_: context,
    )
    monkeypatch.setattr(
        "detector_lab.practical_alerts._dark_frame_ratio",
        lambda raw_frames: 0.0,
    )
    monkeypatch.setattr(
        "detector_lab.practical_alerts._prefers_motion_blur_classification",
        lambda **kwargs: False,
    )
    monkeypatch.setattr(
        "detector_lab.practical_alerts._weighted_geometric_blur_core",
        lambda **kwargs: 0.96,
    )
    monkeypatch.setattr(
        "detector_lab.practical_alerts._neighbor_black_ratios",
        lambda analysis_slice: (0.0, 0.70),
    )

    row = analyze_practical_blur_alert_v3(analysis_slice)

    assert row["guardrail_reason"] == "black_neighbor_transition"
    assert row["practical_score"] == 0.845
    assert row["practical_detected"] is False


def test_practical_blur_alert_v3_skips_hard_neighbor_penalty_above_max_blur_score(
    monkeypatch, tmp_path: Path
) -> None:
    """The v3 blur alert should keep very strong blur scores despite black-neighbor context."""
    analysis_slice = _fake_slice(tmp_path)
    context = _fake_blur_context(tmp_path)
    monkeypatch.setattr(
        "detector_lab.practical_alerts.analyze_video_metrics",
        lambda **kwargs: {
            "source_group": kwargs["source_group"],
            "source_name": kwargs["source_name"],
            "processing_sec": 0.02,
            "black_segment_count": 0,
            "total_black_sec": 0.0,
            "longest_black_sec": 0.0,
            "black_ratio": 0.0,
        },
    )
    monkeypatch.setattr(
        "detector_lab.practical_alerts.prepare_blur_analysis_context",
        lambda slice_: context,
    )
    monkeypatch.setattr(
        "detector_lab.practical_alerts._dark_frame_ratio",
        lambda raw_frames: 0.0,
    )
    monkeypatch.setattr(
        "detector_lab.practical_alerts._prefers_motion_blur_classification",
        lambda **kwargs: False,
    )
    monkeypatch.setattr(
        "detector_lab.practical_alerts._weighted_geometric_blur_core",
        lambda **kwargs: 0.97,
    )
    monkeypatch.setattr(
        "detector_lab.practical_alerts._neighbor_black_ratios",
        lambda analysis_slice: (0.0, 0.70),
    )

    row = analyze_practical_blur_alert_v3(analysis_slice)

    assert row["guardrail_reason"] == ""
    assert row["practical_score"] == 0.97
    assert row["practical_detected"] is True


def test_practical_blur_alert_v3_applies_mixed_neighbor_penalty(
    monkeypatch, tmp_path: Path
) -> None:
    """The v3 blur alert should soften scores for mixed current-plus-neighbor black context."""
    analysis_slice = _fake_slice(tmp_path)
    context = _fake_blur_context(tmp_path)
    monkeypatch.setattr(
        "detector_lab.practical_alerts.analyze_video_metrics",
        lambda **kwargs: {
            "source_group": kwargs["source_group"],
            "source_name": kwargs["source_name"],
            "processing_sec": 0.02,
            "black_segment_count": 0,
            "total_black_sec": 0.0,
            "longest_black_sec": 0.0,
            "black_ratio": 0.1,
        },
    )
    monkeypatch.setattr(
        "detector_lab.practical_alerts.prepare_blur_analysis_context",
        lambda slice_: context,
    )
    monkeypatch.setattr(
        "detector_lab.practical_alerts._dark_frame_ratio",
        lambda raw_frames: 0.0,
    )
    monkeypatch.setattr(
        "detector_lab.practical_alerts._prefers_motion_blur_classification",
        lambda **kwargs: False,
    )
    monkeypatch.setattr(
        "detector_lab.practical_alerts._neighbor_black_ratios",
        lambda analysis_slice: (0.0, 0.4),
    )

    row = analyze_practical_blur_alert_v3(analysis_slice)

    assert row["practical_detected"] is False
    assert row["guardrail_reason"] == "black_neighbor_transition"
    assert 0.0 < row["practical_score"] < row["practical_threshold"]


def test_practical_blur_alert_v3_honors_structure_escape_at_exact_boundary(
    monkeypatch, tmp_path: Path
) -> None:
    """The v3 blur alert should bypass neighbor penalties at the exact structure-escape boundary."""
    analysis_slice = _fake_slice(tmp_path)
    context = _fake_blur_context(tmp_path)
    collapse_measurements = BlurWindowMeasurements(
        frame_scores=context.measurements.frame_scores,
        motion_scores=context.measurements.motion_scores,
        sharpness_p10=context.measurements.sharpness_p10,
        sharpness_p90=context.measurements.sharpness_p90,
        absolute_blur_scores=context.measurements.absolute_blur_scores,
        dynamic_blur_scores=context.measurements.dynamic_blur_scores,
        edge_density_scores=[0.075, 0.075, 0.075],
        mean_edge_strength_scores=context.measurements.mean_edge_strength_scores,
        texture_energy_scores=context.measurements.texture_energy_scores,
        medium_scale_edge_density_scores=context.measurements.medium_scale_edge_density_scores,
        coarse_scale_edge_density_scores=context.measurements.coarse_scale_edge_density_scores,
        medium_scale_texture_energy_scores=[0.004, 0.004, 0.004],
        coarse_scale_texture_energy_scores=context.measurements.coarse_scale_texture_energy_scores,
        edge_persistence_scores=context.measurements.edge_persistence_scores,
        texture_retention_scores=context.measurements.texture_retention_scores,
    )
    monkeypatch.setattr(
        "detector_lab.practical_alerts.analyze_video_metrics",
        lambda **kwargs: {
            "source_group": kwargs["source_group"],
            "source_name": kwargs["source_name"],
            "processing_sec": 0.02,
            "black_segment_count": 0,
            "total_black_sec": 0.0,
            "longest_black_sec": 0.0,
            "black_ratio": 0.0,
        },
    )
    monkeypatch.setattr(
        "detector_lab.practical_alerts.prepare_blur_analysis_context",
        lambda slice_: BlurAnalysisContext(
            analysis_slice=context.analysis_slice,
            display_source_name=context.display_source_name,
            display_source_group=context.display_source_group,
            threshold=context.threshold,
            start_time=context.start_time,
            sample_width=context.sample_width,
            sample_height=context.sample_height,
            raw_frames=context.raw_frames,
            measurements=collapse_measurements,
        ),
    )
    monkeypatch.setattr(
        "detector_lab.practical_alerts._dark_frame_ratio",
        lambda raw_frames: 0.0,
    )
    monkeypatch.setattr(
        "detector_lab.practical_alerts._prefers_motion_blur_classification",
        lambda **kwargs: False,
    )
    monkeypatch.setattr(
        "detector_lab.practical_alerts._neighbor_black_ratios",
        lambda analysis_slice: (0.0, 0.70),
    )

    row = analyze_practical_blur_alert_v3(analysis_slice)

    assert row["guardrail_reason"] == ""
    assert row["practical_score"] > 0.0


def test_practical_blur_alert_v3_bypasses_neighbor_penalty_for_strong_structure_collapse(
    monkeypatch, tmp_path: Path
) -> None:
    """Strong blur structure collapse should bypass the black-neighbor penalty."""
    analysis_slice = _fake_slice(tmp_path)
    context = _fake_blur_context(tmp_path)
    collapse_measurements = BlurWindowMeasurements(
        frame_scores=context.measurements.frame_scores,
        motion_scores=context.measurements.motion_scores,
        sharpness_p10=context.measurements.sharpness_p10,
        sharpness_p90=context.measurements.sharpness_p90,
        absolute_blur_scores=context.measurements.absolute_blur_scores,
        dynamic_blur_scores=context.measurements.dynamic_blur_scores,
        edge_density_scores=[0.05, 0.05, 0.05],
        mean_edge_strength_scores=context.measurements.mean_edge_strength_scores,
        texture_energy_scores=context.measurements.texture_energy_scores,
        medium_scale_edge_density_scores=context.measurements.medium_scale_edge_density_scores,
        coarse_scale_edge_density_scores=context.measurements.coarse_scale_edge_density_scores,
        medium_scale_texture_energy_scores=[0.003, 0.003, 0.003],
        coarse_scale_texture_energy_scores=context.measurements.coarse_scale_texture_energy_scores,
        edge_persistence_scores=context.measurements.edge_persistence_scores,
        texture_retention_scores=context.measurements.texture_retention_scores,
    )
    monkeypatch.setattr(
        "detector_lab.practical_alerts.analyze_video_metrics",
        lambda **kwargs: {
            "source_group": kwargs["source_group"],
            "source_name": kwargs["source_name"],
            "processing_sec": 0.02,
            "black_segment_count": 0,
            "total_black_sec": 0.0,
            "longest_black_sec": 0.0,
            "black_ratio": 0.0,
        },
    )
    monkeypatch.setattr(
        "detector_lab.practical_alerts.prepare_blur_analysis_context",
        lambda slice_: BlurAnalysisContext(
            analysis_slice=context.analysis_slice,
            display_source_name=context.display_source_name,
            display_source_group=context.display_source_group,
            threshold=context.threshold,
            start_time=context.start_time,
            sample_width=context.sample_width,
            sample_height=context.sample_height,
            raw_frames=context.raw_frames,
            measurements=collapse_measurements,
        ),
    )
    monkeypatch.setattr(
        "detector_lab.practical_alerts._dark_frame_ratio",
        lambda raw_frames: 0.0,
    )
    monkeypatch.setattr(
        "detector_lab.practical_alerts._prefers_motion_blur_classification",
        lambda **kwargs: False,
    )
    monkeypatch.setattr(
        "detector_lab.practical_alerts._neighbor_black_ratios",
        lambda analysis_slice: (0.0, 0.8),
    )

    row = analyze_practical_blur_alert_v3(analysis_slice)

    assert row["guardrail_reason"] == ""
    assert row["practical_score"] > 0.0


def test_practical_blur_alert_v2_score_increases_when_medium_scale_texture_drops(
    monkeypatch, tmp_path: Path
) -> None:
    """The calibrated blur score should rise as medium-scale texture collapses."""
    analysis_slice = _fake_slice(tmp_path)
    context = _fake_blur_context(tmp_path)

    def build_measurements(texture_value: float) -> BlurWindowMeasurements:
        return BlurWindowMeasurements(
            frame_scores=context.measurements.frame_scores,
            motion_scores=context.measurements.motion_scores,
            sharpness_p10=context.measurements.sharpness_p10,
            sharpness_p90=context.measurements.sharpness_p90,
            absolute_blur_scores=context.measurements.absolute_blur_scores,
            dynamic_blur_scores=context.measurements.dynamic_blur_scores,
            edge_density_scores=context.measurements.edge_density_scores,
            mean_edge_strength_scores=context.measurements.mean_edge_strength_scores,
            texture_energy_scores=context.measurements.texture_energy_scores,
            medium_scale_edge_density_scores=context.measurements.medium_scale_edge_density_scores,
            coarse_scale_edge_density_scores=context.measurements.coarse_scale_edge_density_scores,
            medium_scale_texture_energy_scores=[texture_value, texture_value, texture_value],
            coarse_scale_texture_energy_scores=context.measurements.coarse_scale_texture_energy_scores,
            edge_persistence_scores=context.measurements.edge_persistence_scores,
            texture_retention_scores=context.measurements.texture_retention_scores,
        )

    monkeypatch.setattr(
        "detector_lab.practical_alerts.analyze_video_metrics",
        lambda **kwargs: {
            "source_group": kwargs["source_group"],
            "source_name": kwargs["source_name"],
            "processing_sec": 0.02,
            "black_segment_count": 0,
            "total_black_sec": 0.0,
            "longest_black_sec": 0.0,
            "black_ratio": 0.0,
        },
    )
    monkeypatch.setattr(
        "detector_lab.practical_alerts._prefers_motion_blur_classification",
        lambda **kwargs: False,
    )

    monkeypatch.setattr(
        "detector_lab.practical_alerts.prepare_blur_analysis_context",
        lambda slice_: BlurAnalysisContext(
            analysis_slice=context.analysis_slice,
            display_source_name=context.display_source_name,
            display_source_group=context.display_source_group,
            threshold=context.threshold,
            start_time=context.start_time,
            sample_width=context.sample_width,
            sample_height=context.sample_height,
            raw_frames=context.raw_frames,
            measurements=build_measurements(0.30),
        ),
    )
    higher_texture_row = analyze_practical_blur_alert_v2(
        analysis_slice,
        evaluation_context=_fresh_practical_evaluation_context(),
    )

    monkeypatch.setattr(
        "detector_lab.practical_alerts.prepare_blur_analysis_context",
        lambda slice_: BlurAnalysisContext(
            analysis_slice=context.analysis_slice,
            display_source_name=context.display_source_name,
            display_source_group=context.display_source_group,
            threshold=context.threshold,
            start_time=context.start_time,
            sample_width=context.sample_width,
            sample_height=context.sample_height,
            raw_frames=context.raw_frames,
            measurements=build_measurements(0.02),
        ),
    )
    lower_texture_row = analyze_practical_blur_alert_v2(
        analysis_slice,
        evaluation_context=_fresh_practical_evaluation_context(),
    )

    assert lower_texture_row["practical_score"] > higher_texture_row["practical_score"]


def test_practical_blur_alert_v2_score_increases_when_edge_density_drops(
    monkeypatch, tmp_path: Path
) -> None:
    """The calibrated blur score should rise as edge density collapses."""
    analysis_slice = _fake_slice(tmp_path)
    context = _fake_blur_context(tmp_path)

    def build_measurements(edge_value: float) -> BlurWindowMeasurements:
        return BlurWindowMeasurements(
            frame_scores=context.measurements.frame_scores,
            motion_scores=context.measurements.motion_scores,
            sharpness_p10=context.measurements.sharpness_p10,
            sharpness_p90=context.measurements.sharpness_p90,
            absolute_blur_scores=context.measurements.absolute_blur_scores,
            dynamic_blur_scores=context.measurements.dynamic_blur_scores,
            edge_density_scores=[edge_value, edge_value, edge_value],
            mean_edge_strength_scores=context.measurements.mean_edge_strength_scores,
            texture_energy_scores=context.measurements.texture_energy_scores,
            medium_scale_edge_density_scores=context.measurements.medium_scale_edge_density_scores,
            coarse_scale_edge_density_scores=context.measurements.coarse_scale_edge_density_scores,
            medium_scale_texture_energy_scores=context.measurements.medium_scale_texture_energy_scores,
            coarse_scale_texture_energy_scores=context.measurements.coarse_scale_texture_energy_scores,
            edge_persistence_scores=context.measurements.edge_persistence_scores,
            texture_retention_scores=context.measurements.texture_retention_scores,
        )

    monkeypatch.setattr(
        "detector_lab.practical_alerts.analyze_video_metrics",
        lambda **kwargs: {
            "source_group": kwargs["source_group"],
            "source_name": kwargs["source_name"],
            "processing_sec": 0.02,
            "black_segment_count": 0,
            "total_black_sec": 0.0,
            "longest_black_sec": 0.0,
            "black_ratio": 0.0,
        },
    )
    monkeypatch.setattr(
        "detector_lab.practical_alerts._prefers_motion_blur_classification",
        lambda **kwargs: False,
    )

    monkeypatch.setattr(
        "detector_lab.practical_alerts.prepare_blur_analysis_context",
        lambda slice_: BlurAnalysisContext(
            analysis_slice=context.analysis_slice,
            display_source_name=context.display_source_name,
            display_source_group=context.display_source_group,
            threshold=context.threshold,
            start_time=context.start_time,
            sample_width=context.sample_width,
            sample_height=context.sample_height,
            raw_frames=context.raw_frames,
            measurements=build_measurements(0.40),
        ),
    )
    denser_edges_row = analyze_practical_blur_alert_v2(
        analysis_slice,
        evaluation_context=_fresh_practical_evaluation_context(),
    )

    monkeypatch.setattr(
        "detector_lab.practical_alerts.prepare_blur_analysis_context",
        lambda slice_: BlurAnalysisContext(
            analysis_slice=context.analysis_slice,
            display_source_name=context.display_source_name,
            display_source_group=context.display_source_group,
            threshold=context.threshold,
            start_time=context.start_time,
            sample_width=context.sample_width,
            sample_height=context.sample_height,
            raw_frames=context.raw_frames,
            measurements=build_measurements(0.05),
        ),
    )
    sparse_edges_row = analyze_practical_blur_alert_v2(
        analysis_slice,
        evaluation_context=_fresh_practical_evaluation_context(),
    )

    assert sparse_edges_row["practical_score"] > denser_edges_row["practical_score"]


def test_practical_motion_blur_alert_skips_black_neighbor_transition_windows(
    monkeypatch, tmp_path: Path
) -> None:
    """The practical motion-blur alert should ignore black-transition motion spikes."""
    analysis_slice = _fake_slice(tmp_path)
    context = _fake_blur_context(tmp_path)
    monkeypatch.setattr(
        "detector_lab.practical_alerts.analyze_video_metrics",
        lambda **kwargs: {
            "source_group": kwargs["source_group"],
            "source_name": kwargs["source_name"],
            "processing_sec": 0.02,
            "black_segment_count": 0,
            "total_black_sec": 0.0,
            "longest_black_sec": 0.0,
            "black_ratio": 0.0,
        },
    )
    monkeypatch.setattr(
        "detector_lab.practical_alerts.prepare_blur_analysis_context",
        lambda slice_: context,
    )
    monkeypatch.setattr(
        "detector_lab.practical_alerts.compute_motion_coherence_multiscale",
        lambda **kwargs: MotionCoherenceMetrics(
            fine_scale_motion_energy=0.20,
            medium_scale_motion_energy=0.18,
            coarse_scale_motion_energy=0.15,
            motion_persistence=0.82,
            motion_coherence=0.86,
            incoherence_avg=0.05,
            incoherence_scores=[0.05, 0.05],
        ),
    )
    monkeypatch.setattr(
        "detector_lab.practical_alerts._neighbor_black_ratios",
        lambda analysis_slice: (0.0, 0.8),
    )

    row = analyze_practical_motion_blur_alert(analysis_slice)

    assert row["practical_detected"] is False
    assert row["guardrail_reason"] == "black_transition_motion"
    assert row["practical_score"] == 0.0


def test_practical_motion_blur_alert_black_transition_guardrail_overrides_otherwise_positive_score(
    monkeypatch, tmp_path: Path
) -> None:
    """Black-neighbor suppression should win even when the motion-blur score would otherwise trigger."""
    analysis_slice = _fake_slice(tmp_path)
    context = _fake_blur_context(tmp_path)
    strong_measurements = _fake_motion_blur_measurements(
        motion_mean=0.70,
        motion_p90=0.85,
        absolute_blur=0.90,
        dynamic_blur=0.92,
        texture_energy=0.05,
    )
    motion_metrics = MotionCoherenceMetrics(
        fine_scale_motion_energy=0.26,
        medium_scale_motion_energy=0.23,
        coarse_scale_motion_energy=0.19,
        motion_persistence=0.95,
        motion_coherence=0.96,
        incoherence_avg=0.03,
        incoherence_scores=[0.03, 0.03],
    )
    monkeypatch.setattr(
        "detector_lab.practical_alerts.analyze_video_metrics",
        lambda **kwargs: {
            "source_group": kwargs["source_group"],
            "source_name": kwargs["source_name"],
            "processing_sec": 0.02,
            "black_segment_count": 0,
            "total_black_sec": 0.0,
            "longest_black_sec": 0.0,
            "black_ratio": 0.0,
        },
    )
    monkeypatch.setattr(
        "detector_lab.practical_alerts.prepare_blur_analysis_context",
        lambda slice_: BlurAnalysisContext(
            analysis_slice=context.analysis_slice,
            display_source_name=context.display_source_name,
            display_source_group=context.display_source_group,
            threshold=context.threshold,
            start_time=context.start_time,
            sample_width=context.sample_width,
            sample_height=context.sample_height,
            raw_frames=context.raw_frames,
            measurements=strong_measurements,
        ),
    )
    monkeypatch.setattr(
        "detector_lab.practical_alerts.compute_motion_coherence_multiscale",
        lambda **kwargs: motion_metrics,
    )
    monkeypatch.setattr(
        "detector_lab.practical_alerts._neighbor_black_ratios",
        lambda analysis_slice: (0.0, 0.0),
    )

    unsuppressed_row = analyze_practical_motion_blur_alert(analysis_slice)

    monkeypatch.setattr(
        "detector_lab.practical_alerts._neighbor_black_ratios",
        lambda analysis_slice: (0.0, 0.70),
    )
    suppressed_row = analyze_practical_motion_blur_alert(analysis_slice)

    assert unsuppressed_row["practical_detected"] is True
    assert unsuppressed_row["practical_score"] >= unsuppressed_row["practical_threshold"]
    assert suppressed_row["practical_detected"] is False
    assert suppressed_row["guardrail_reason"] == "black_transition_motion"
    assert suppressed_row["practical_score"] == 0.0


def test_practical_motion_blur_alert_skips_black_dominant_windows(
    monkeypatch, tmp_path: Path
) -> None:
    """The practical motion-blur alert should stay quiet on black-dominant windows."""
    analysis_slice = _fake_slice(tmp_path)
    context = _fake_blur_context(tmp_path)
    monkeypatch.setattr(
        "detector_lab.practical_alerts.analyze_video_metrics",
        lambda **kwargs: {
            "source_group": kwargs["source_group"],
            "source_name": kwargs["source_name"],
            "processing_sec": 0.02,
            "black_segment_count": 1,
            "total_black_sec": 0.5,
            "longest_black_sec": 0.5,
            "black_ratio": 0.5,
        },
    )
    monkeypatch.setattr(
        "detector_lab.practical_alerts.prepare_blur_analysis_context",
        lambda slice_: context,
    )
    monkeypatch.setattr(
        "detector_lab.practical_alerts.compute_motion_coherence_multiscale",
        lambda **kwargs: MotionCoherenceMetrics(
            fine_scale_motion_energy=0.20,
            medium_scale_motion_energy=0.18,
            coarse_scale_motion_energy=0.15,
            motion_persistence=0.82,
            motion_coherence=0.86,
            incoherence_avg=0.05,
            incoherence_scores=[0.05, 0.05],
        ),
    )

    row = analyze_practical_motion_blur_alert(analysis_slice)

    assert row["practical_detected"] is False
    assert row["guardrail_reason"] == "black_dominant"
    assert row["practical_score"] == 0.0


def test_practical_motion_blur_alert_requires_minimum_softness(
    monkeypatch, tmp_path: Path
) -> None:
    """The practical motion-blur alert should reject motion without enough softness."""
    analysis_slice = _fake_slice(tmp_path)
    context = _fake_blur_context(tmp_path)
    low_softness_measurements = BlurWindowMeasurements(
        frame_scores=context.measurements.frame_scores,
        motion_scores=context.measurements.motion_scores,
        sharpness_p10=context.measurements.sharpness_p10,
        sharpness_p90=context.measurements.sharpness_p90,
        absolute_blur_scores=[0.20, 0.24, 0.28],
        dynamic_blur_scores=[0.22, 0.26, 0.30],
        edge_density_scores=context.measurements.edge_density_scores,
        mean_edge_strength_scores=context.measurements.mean_edge_strength_scores,
        texture_energy_scores=[0.95, 0.95, 0.95],
        medium_scale_edge_density_scores=context.measurements.medium_scale_edge_density_scores,
        coarse_scale_edge_density_scores=context.measurements.coarse_scale_edge_density_scores,
        medium_scale_texture_energy_scores=context.measurements.medium_scale_texture_energy_scores,
        coarse_scale_texture_energy_scores=context.measurements.coarse_scale_texture_energy_scores,
        edge_persistence_scores=context.measurements.edge_persistence_scores,
        texture_retention_scores=context.measurements.texture_retention_scores,
    )
    monkeypatch.setattr(
        "detector_lab.practical_alerts.analyze_video_metrics",
        lambda **kwargs: {
            "source_group": kwargs["source_group"],
            "source_name": kwargs["source_name"],
            "processing_sec": 0.02,
            "black_segment_count": 0,
            "total_black_sec": 0.0,
            "longest_black_sec": 0.0,
            "black_ratio": 0.0,
        },
    )
    monkeypatch.setattr(
        "detector_lab.practical_alerts.prepare_blur_analysis_context",
        lambda slice_: BlurAnalysisContext(
            analysis_slice=context.analysis_slice,
            display_source_name=context.display_source_name,
            display_source_group=context.display_source_group,
            threshold=context.threshold,
            start_time=context.start_time,
            sample_width=context.sample_width,
            sample_height=context.sample_height,
            raw_frames=context.raw_frames,
            measurements=low_softness_measurements,
        ),
    )
    monkeypatch.setattr(
        "detector_lab.practical_alerts.compute_motion_coherence_multiscale",
        lambda **kwargs: MotionCoherenceMetrics(
            fine_scale_motion_energy=0.25,
            medium_scale_motion_energy=0.22,
            coarse_scale_motion_energy=0.18,
            motion_persistence=0.90,
            motion_coherence=0.92,
            incoherence_avg=0.03,
            incoherence_scores=[0.03, 0.03],
        ),
    )
    monkeypatch.setattr(
        "detector_lab.practical_alerts._neighbor_black_ratios",
        lambda analysis_slice: (0.0, 0.0),
    )

    row = analyze_practical_motion_blur_alert(analysis_slice)

    assert row["practical_detected"] is False
    assert row["guardrail_reason"] == "softness_too_low"
    assert row["practical_score"] == 0.0


def test_practical_motion_blur_alert_skips_mixed_black_neighbor_transition_windows(
    monkeypatch, tmp_path: Path
) -> None:
    """The practical motion-blur alert should reject mixed current-plus-neighbor black transitions."""
    analysis_slice = _fake_slice(tmp_path)
    context = _fake_blur_context(tmp_path)
    _patch_practical_black_detector(
        monkeypatch,
        black_segment_count=1,
        total_black_sec=0.1,
        longest_black_sec=0.1,
        black_ratio=0.1,
    )
    _patch_practical_blur_context(monkeypatch, context)
    _patch_practical_motion_metrics(monkeypatch, _motion_coherence_metrics())
    monkeypatch.setattr(
        "detector_lab.practical_alerts._neighbor_black_ratios",
        lambda analysis_slice: (0.0, 0.4),
    )

    row = analyze_practical_motion_blur_alert(analysis_slice)

    assert row["practical_detected"] is False
    assert row["guardrail_reason"] == "black_transition_motion"
    assert row["practical_score"] == 0.0


@pytest.mark.parametrize(
    (
        "black_ratio",
        "neighbor_black_ratio",
        "expected_detected",
        "expected_guardrail_reason",
    ),
    [
        (0.10, 0.40, False, "black_transition_motion"),
        (0.099, 0.399, True, ""),
        (0.10, 0.399, True, ""),
    ],
)
def test_practical_motion_blur_alert_mixed_black_transition_boundary_behavior(
    monkeypatch,
    tmp_path: Path,
    black_ratio: float,
    neighbor_black_ratio: float,
    expected_detected: bool,
    expected_guardrail_reason: str,
) -> None:
    """Mixed black-transition suppression should stay inclusive at the boundary and permissive just below it."""
    analysis_slice = _fake_slice(tmp_path)
    context = _fake_blur_context(tmp_path)
    strong_measurements = _fake_motion_blur_measurements(
        motion_mean=0.70,
        motion_p90=0.85,
        absolute_blur=0.90,
        dynamic_blur=0.92,
        texture_energy=0.05,
    )
    _patch_practical_black_detector(
        monkeypatch,
        black_segment_count=1,
        total_black_sec=black_ratio,
        longest_black_sec=black_ratio,
        black_ratio=black_ratio,
    )
    _patch_practical_blur_context(
        monkeypatch,
        _with_blur_context_measurements(context, measurements=strong_measurements),
    )
    _patch_practical_motion_metrics(
        monkeypatch,
        _motion_coherence_metrics(
            fine_scale_motion_energy=0.26,
            medium_scale_motion_energy=0.23,
            coarse_scale_motion_energy=0.19,
            motion_persistence=0.95,
            motion_coherence=0.96,
            incoherence_avg=0.03,
            incoherence_scores=[0.03, 0.03],
        ),
    )
    monkeypatch.setattr(
        "detector_lab.practical_alerts._neighbor_black_ratios",
        lambda analysis_slice: (0.0, neighbor_black_ratio),
    )

    row = analyze_practical_motion_blur_alert(analysis_slice)

    assert row["practical_detected"] is expected_detected
    assert row["guardrail_reason"] == expected_guardrail_reason
    if expected_detected:
        assert row["practical_score"] >= row["practical_threshold"]
    else:
        assert row["practical_score"] == 0.0


def test_practical_motion_blur_alert_skips_exact_black_ratio_boundary(
    monkeypatch, tmp_path: Path
) -> None:
    """The practical motion-blur alert should suppress at the exact black-dominant boundary."""
    analysis_slice = _fake_slice(tmp_path)
    context = _fake_blur_context(tmp_path)
    monkeypatch.setattr(
        "detector_lab.practical_alerts.analyze_video_metrics",
        lambda **kwargs: {
            "source_group": kwargs["source_group"],
            "source_name": kwargs["source_name"],
            "processing_sec": 0.02,
            "black_segment_count": 1,
            "total_black_sec": 0.4,
            "longest_black_sec": 0.4,
            "black_ratio": 0.40,
        },
    )
    monkeypatch.setattr(
        "detector_lab.practical_alerts.prepare_blur_analysis_context",
        lambda slice_: context,
    )
    monkeypatch.setattr(
        "detector_lab.practical_alerts.compute_motion_coherence_multiscale",
        lambda **kwargs: MotionCoherenceMetrics(
            fine_scale_motion_energy=0.20,
            medium_scale_motion_energy=0.18,
            coarse_scale_motion_energy=0.15,
            motion_persistence=0.82,
            motion_coherence=0.86,
            incoherence_avg=0.05,
            incoherence_scores=[0.05, 0.05],
        ),
    )

    row = analyze_practical_motion_blur_alert(analysis_slice)

    assert row["practical_detected"] is False
    assert row["guardrail_reason"] == "black_dominant"
    assert row["practical_score"] == 0.0


def test_practical_motion_blur_alert_accepts_exact_minimum_coherence_with_strong_softness(
    monkeypatch, tmp_path: Path
) -> None:
    """The practical motion-blur alert should allow the exact coherence boundary when other support is strong."""
    analysis_slice = _fake_slice(tmp_path)
    context = _fake_blur_context(tmp_path)
    strong_motion_measurements = BlurWindowMeasurements(
        frame_scores=context.measurements.frame_scores,
        motion_scores=[0.0, 0.25, 0.30],
        sharpness_p10=context.measurements.sharpness_p10,
        sharpness_p90=context.measurements.sharpness_p90,
        absolute_blur_scores=context.measurements.absolute_blur_scores,
        dynamic_blur_scores=context.measurements.dynamic_blur_scores,
        edge_density_scores=context.measurements.edge_density_scores,
        mean_edge_strength_scores=context.measurements.mean_edge_strength_scores,
        texture_energy_scores=context.measurements.texture_energy_scores,
        medium_scale_edge_density_scores=context.measurements.medium_scale_edge_density_scores,
        coarse_scale_edge_density_scores=context.measurements.coarse_scale_edge_density_scores,
        medium_scale_texture_energy_scores=context.measurements.medium_scale_texture_energy_scores,
        coarse_scale_texture_energy_scores=context.measurements.coarse_scale_texture_energy_scores,
        edge_persistence_scores=context.measurements.edge_persistence_scores,
        texture_retention_scores=context.measurements.texture_retention_scores,
    )
    monkeypatch.setattr(
        "detector_lab.practical_alerts.analyze_video_metrics",
        lambda **kwargs: {
            "source_group": kwargs["source_group"],
            "source_name": kwargs["source_name"],
            "processing_sec": 0.02,
            "black_segment_count": 0,
            "total_black_sec": 0.0,
            "longest_black_sec": 0.0,
            "black_ratio": 0.0,
        },
    )
    monkeypatch.setattr(
        "detector_lab.practical_alerts.prepare_blur_analysis_context",
        lambda slice_: BlurAnalysisContext(
            analysis_slice=context.analysis_slice,
            display_source_name=context.display_source_name,
            display_source_group=context.display_source_group,
            threshold=context.threshold,
            start_time=context.start_time,
            sample_width=context.sample_width,
            sample_height=context.sample_height,
            raw_frames=context.raw_frames,
            measurements=strong_motion_measurements,
        ),
    )
    monkeypatch.setattr(
        "detector_lab.practical_alerts.compute_motion_coherence_multiscale",
        lambda **kwargs: MotionCoherenceMetrics(
            fine_scale_motion_energy=0.26,
            medium_scale_motion_energy=0.23,
            coarse_scale_motion_energy=0.19,
            motion_persistence=0.97,
            motion_coherence=0.30,
            incoherence_avg=0.03,
            incoherence_scores=[0.03, 0.03],
        ),
    )
    monkeypatch.setattr(
        "detector_lab.practical_alerts._neighbor_black_ratios",
        lambda analysis_slice: (0.0, 0.0),
    )

    row = analyze_practical_motion_blur_alert(analysis_slice)

    assert row["guardrail_reason"] == ""
    assert row["practical_detected"] is True
    assert row["practical_score"] >= row["practical_threshold"]


@pytest.mark.parametrize(
    ("motion_mean", "expected_score", "expected_detected"),
    [
        (0.62545, 0.68, True),
        (0.60545, 0.679, False),
    ],
)
def test_practical_motion_blur_alert_final_threshold_behavior(
    monkeypatch,
    tmp_path: Path,
    motion_mean: float,
    expected_score: float,
    expected_detected: bool,
) -> None:
    """The final motion-blur threshold should stay inclusive and fail closed just below it."""
    analysis_slice = _fake_slice(tmp_path)
    context = _fake_blur_context(tmp_path)
    boundary_measurements = _fake_motion_blur_measurements(
        motion_mean=motion_mean,
        motion_p90=0.80,
        absolute_blur=0.62,
        dynamic_blur=0.64,
        texture_energy=0.10,
    )
    _patch_practical_black_detector(monkeypatch)
    _patch_practical_blur_context(
        monkeypatch,
        _with_blur_context_measurements(context, measurements=boundary_measurements),
    )
    _patch_practical_motion_metrics(
        monkeypatch,
        _motion_coherence_metrics(
            fine_scale_motion_energy=0.26,
            medium_scale_motion_energy=0.23,
            coarse_scale_motion_energy=0.19,
            motion_persistence=0.651,
            motion_coherence=0.651,
            incoherence_avg=0.03,
            incoherence_scores=[0.03, 0.03],
        ),
    )
    monkeypatch.setattr(
        "detector_lab.practical_alerts._neighbor_black_ratios",
        lambda analysis_slice: (0.0, 0.0),
    )

    row = analyze_practical_motion_blur_alert(analysis_slice)

    assert row["guardrail_reason"] == ""
    assert row["practical_score"] == expected_score
    assert row["practical_detected"] is expected_detected


def test_practical_motion_blur_alert_rejects_just_below_minimum_coherence(
    monkeypatch, tmp_path: Path
) -> None:
    """The practical motion-blur alert should fail closed just below the coherence boundary."""
    analysis_slice = _fake_slice(tmp_path)
    context = _fake_blur_context(tmp_path)
    monkeypatch.setattr(
        "detector_lab.practical_alerts.analyze_video_metrics",
        lambda **kwargs: {
            "source_group": kwargs["source_group"],
            "source_name": kwargs["source_name"],
            "processing_sec": 0.02,
            "black_segment_count": 0,
            "total_black_sec": 0.0,
            "longest_black_sec": 0.0,
            "black_ratio": 0.0,
        },
    )
    monkeypatch.setattr(
        "detector_lab.practical_alerts.prepare_blur_analysis_context",
        lambda slice_: BlurAnalysisContext(
            analysis_slice=context.analysis_slice,
            display_source_name=context.display_source_name,
            display_source_group=context.display_source_group,
            threshold=context.threshold,
            start_time=context.start_time,
            sample_width=context.sample_width,
            sample_height=context.sample_height,
            raw_frames=context.raw_frames,
            measurements=_fake_motion_blur_measurements(),
        ),
    )
    monkeypatch.setattr(
        "detector_lab.practical_alerts.compute_motion_coherence_multiscale",
        lambda **kwargs: MotionCoherenceMetrics(
            fine_scale_motion_energy=0.24,
            medium_scale_motion_energy=0.20,
            coarse_scale_motion_energy=0.17,
            motion_persistence=0.95,
            motion_coherence=0.299,
            incoherence_avg=0.04,
            incoherence_scores=[0.04, 0.04],
        ),
    )
    monkeypatch.setattr(
        "detector_lab.practical_alerts._neighbor_black_ratios",
        lambda analysis_slice: (0.0, 0.0),
    )

    row = analyze_practical_motion_blur_alert(analysis_slice)

    assert row["practical_detected"] is False
    assert row["guardrail_reason"] == "motion_incoherent"
    assert row["practical_score"] == 0.0


def test_practical_motion_blur_alert_score_increases_with_motion_persistence(
    monkeypatch, tmp_path: Path
) -> None:
    """The practical motion-blur score should increase when persistence strengthens."""
    analysis_slice = _fake_slice(tmp_path)
    context = _fake_blur_context(tmp_path)
    monkeypatch.setattr(
        "detector_lab.practical_alerts.analyze_video_metrics",
        lambda **kwargs: {
            "source_group": kwargs["source_group"],
            "source_name": kwargs["source_name"],
            "processing_sec": 0.02,
            "black_segment_count": 0,
            "total_black_sec": 0.0,
            "longest_black_sec": 0.0,
            "black_ratio": 0.0,
        },
    )
    monkeypatch.setattr(
        "detector_lab.practical_alerts.prepare_blur_analysis_context",
        lambda slice_: BlurAnalysisContext(
            analysis_slice=context.analysis_slice,
            display_source_name=context.display_source_name,
            display_source_group=context.display_source_group,
            threshold=context.threshold,
            start_time=context.start_time,
            sample_width=context.sample_width,
            sample_height=context.sample_height,
            raw_frames=context.raw_frames,
            measurements=_fake_motion_blur_measurements(),
        ),
    )
    monkeypatch.setattr(
        "detector_lab.practical_alerts._neighbor_black_ratios",
        lambda analysis_slice: (0.0, 0.0),
    )

    low_persistence = MotionCoherenceMetrics(
        fine_scale_motion_energy=0.25,
        medium_scale_motion_energy=0.22,
        coarse_scale_motion_energy=0.19,
        motion_persistence=0.40,
        motion_coherence=0.80,
        incoherence_avg=0.04,
        incoherence_scores=[0.04, 0.04],
    )
    high_persistence = MotionCoherenceMetrics(
        fine_scale_motion_energy=0.25,
        medium_scale_motion_energy=0.22,
        coarse_scale_motion_energy=0.19,
        motion_persistence=0.90,
        motion_coherence=0.80,
        incoherence_avg=0.04,
        incoherence_scores=[0.04, 0.04],
    )

    monkeypatch.setattr(
        "detector_lab.practical_alerts.compute_motion_coherence_multiscale",
        lambda **kwargs: low_persistence,
    )
    low_row = analyze_practical_motion_blur_alert(
        analysis_slice,
        evaluation_context=_fresh_practical_evaluation_context(),
    )

    monkeypatch.setattr(
        "detector_lab.practical_alerts.compute_motion_coherence_multiscale",
        lambda **kwargs: high_persistence,
    )
    high_row = analyze_practical_motion_blur_alert(
        analysis_slice,
        evaluation_context=_fresh_practical_evaluation_context(),
    )

    assert high_row["practical_score"] > low_row["practical_score"]


def test_practical_motion_blur_alert_score_increases_with_motion_coherence(
    monkeypatch, tmp_path: Path
) -> None:
    """The practical motion-blur score should increase when coherence strengthens."""
    analysis_slice = _fake_slice(tmp_path)
    context = _fake_blur_context(tmp_path)
    monkeypatch.setattr(
        "detector_lab.practical_alerts.analyze_video_metrics",
        lambda **kwargs: {
            "source_group": kwargs["source_group"],
            "source_name": kwargs["source_name"],
            "processing_sec": 0.02,
            "black_segment_count": 0,
            "total_black_sec": 0.0,
            "longest_black_sec": 0.0,
            "black_ratio": 0.0,
        },
    )
    monkeypatch.setattr(
        "detector_lab.practical_alerts.prepare_blur_analysis_context",
        lambda slice_: BlurAnalysisContext(
            analysis_slice=context.analysis_slice,
            display_source_name=context.display_source_name,
            display_source_group=context.display_source_group,
            threshold=context.threshold,
            start_time=context.start_time,
            sample_width=context.sample_width,
            sample_height=context.sample_height,
            raw_frames=context.raw_frames,
            measurements=_fake_motion_blur_measurements(),
        ),
    )
    monkeypatch.setattr(
        "detector_lab.practical_alerts._neighbor_black_ratios",
        lambda analysis_slice: (0.0, 0.0),
    )

    low_coherence = MotionCoherenceMetrics(
        fine_scale_motion_energy=0.25,
        medium_scale_motion_energy=0.22,
        coarse_scale_motion_energy=0.19,
        motion_persistence=0.80,
        motion_coherence=0.40,
        incoherence_avg=0.04,
        incoherence_scores=[0.04, 0.04],
    )
    high_coherence = MotionCoherenceMetrics(
        fine_scale_motion_energy=0.25,
        medium_scale_motion_energy=0.22,
        coarse_scale_motion_energy=0.19,
        motion_persistence=0.80,
        motion_coherence=0.90,
        incoherence_avg=0.04,
        incoherence_scores=[0.04, 0.04],
    )

    monkeypatch.setattr(
        "detector_lab.practical_alerts.compute_motion_coherence_multiscale",
        lambda **kwargs: low_coherence,
    )
    low_row = analyze_practical_motion_blur_alert(
        analysis_slice,
        evaluation_context=_fresh_practical_evaluation_context(),
    )

    monkeypatch.setattr(
        "detector_lab.practical_alerts.compute_motion_coherence_multiscale",
        lambda **kwargs: high_coherence,
    )
    high_row = analyze_practical_motion_blur_alert(
        analysis_slice,
        evaluation_context=_fresh_practical_evaluation_context(),
    )

    assert high_row["practical_score"] > low_row["practical_score"]


def test_practical_motion_blur_alert_score_increases_with_softness(
    monkeypatch, tmp_path: Path
) -> None:
    """The practical motion-blur score should increase when softness strengthens."""
    analysis_slice = _fake_slice(tmp_path)
    context = _fake_blur_context(tmp_path)
    monkeypatch.setattr(
        "detector_lab.practical_alerts.analyze_video_metrics",
        lambda **kwargs: {
            "source_group": kwargs["source_group"],
            "source_name": kwargs["source_name"],
            "processing_sec": 0.02,
            "black_segment_count": 0,
            "total_black_sec": 0.0,
            "longest_black_sec": 0.0,
            "black_ratio": 0.0,
        },
    )
    monkeypatch.setattr(
        "detector_lab.practical_alerts._neighbor_black_ratios",
        lambda analysis_slice: (0.0, 0.0),
    )
    monkeypatch.setattr(
        "detector_lab.practical_alerts.compute_motion_coherence_multiscale",
        lambda **kwargs: MotionCoherenceMetrics(
            fine_scale_motion_energy=0.25,
            medium_scale_motion_energy=0.22,
            coarse_scale_motion_energy=0.19,
            motion_persistence=0.80,
            motion_coherence=0.80,
            incoherence_avg=0.04,
            incoherence_scores=[0.04, 0.04],
        ),
    )

    monkeypatch.setattr(
        "detector_lab.practical_alerts.prepare_blur_analysis_context",
        lambda slice_: BlurAnalysisContext(
            analysis_slice=context.analysis_slice,
            display_source_name=context.display_source_name,
            display_source_group=context.display_source_group,
            threshold=context.threshold,
            start_time=context.start_time,
            sample_width=context.sample_width,
            sample_height=context.sample_height,
            raw_frames=context.raw_frames,
            measurements=_fake_motion_blur_measurements(
                absolute_blur=0.60,
                dynamic_blur=0.60,
                texture_energy=0.40,
            ),
        ),
    )
    lower_softness_row = analyze_practical_motion_blur_alert(
        analysis_slice,
        evaluation_context=_fresh_practical_evaluation_context(),
    )

    monkeypatch.setattr(
        "detector_lab.practical_alerts.prepare_blur_analysis_context",
        lambda slice_: BlurAnalysisContext(
            analysis_slice=context.analysis_slice,
            display_source_name=context.display_source_name,
            display_source_group=context.display_source_group,
            threshold=context.threshold,
            start_time=context.start_time,
            sample_width=context.sample_width,
            sample_height=context.sample_height,
            raw_frames=context.raw_frames,
            measurements=_fake_motion_blur_measurements(
                absolute_blur=0.90,
                dynamic_blur=0.90,
                texture_energy=0.05,
            ),
        ),
    )
    higher_softness_row = analyze_practical_motion_blur_alert(
        analysis_slice,
        evaluation_context=_fresh_practical_evaluation_context(),
    )

    assert higher_softness_row["practical_score"] > lower_softness_row["practical_score"]


def test_evaluate_practical_alerts_handles_missing_optional_score_metadata() -> None:
    """Practical alert formatting should fail closed when optional score metadata is absent."""
    alerts = evaluate_practical_alerts(
        session_id="detector-lab:practical.motion",
        row={
            "analyzer": "practical_motion_blur_alert",
            "source_name": "sample.mp4 @ 00:00",
            "practical_detected": True,
            "practical_score": None,
            "practical_threshold": "not-a-number",
            "window_index": "",
            "window_start_sec": "",
        },
    )

    assert len(alerts) == 1
    assert alerts[0].message == "sample.mp4 @ 00:00 scored 0.000 against threshold 0.000."
    assert alerts[0].window_index is None
    assert alerts[0].window_start_sec is None


def test_evaluate_practical_alerts_preserves_optional_window_metadata() -> None:
    """Practical alerts should preserve optional slice metadata when it is present."""
    alerts = evaluate_practical_alerts(
        session_id="detector-lab:practical.blur",
        row={
            "analyzer": "practical_blur_alert_v3",
            "source_name": "sample.mp4 @ 00:12",
            "window_index": 12,
            "window_start_sec": 12.0,
            "practical_detected": True,
            "practical_score": 0.955,
            "practical_threshold": 0.955,
        },
    )

    assert len(alerts) == 1
    assert alerts[0].detector_id == "practical_blur_alert_v3"
    assert alerts[0].source_name == "sample.mp4 @ 00:12"
    assert alerts[0].window_index == 12
    assert alerts[0].window_start_sec == 12.0


@pytest.mark.parametrize(
    ("texture_energy", "expected_detected", "expected_guardrail_reason"),
    [
        (0.475, True, ""),
        (0.48, False, "softness_too_low"),
    ],
)
def test_practical_motion_blur_alert_minimum_softness_boundary_behavior(
    monkeypatch,
    tmp_path: Path,
    texture_energy: float,
    expected_detected: bool,
    expected_guardrail_reason: str,
) -> None:
    """The minimum-softness guard should stay inclusive at the boundary and fail closed below it."""
    analysis_slice = _fake_slice(tmp_path)
    context = _fake_blur_context(tmp_path)
    softness_measurements = BlurWindowMeasurements(
        frame_scores=context.measurements.frame_scores,
        motion_scores=[0.0, 0.50, 0.50],
        sharpness_p10=context.measurements.sharpness_p10,
        sharpness_p90=context.measurements.sharpness_p90,
        absolute_blur_scores=[0.60, 0.60, 0.60],
        dynamic_blur_scores=[0.50, 0.50, 0.50],
        edge_density_scores=context.measurements.edge_density_scores,
        mean_edge_strength_scores=context.measurements.mean_edge_strength_scores,
        texture_energy_scores=[texture_energy, texture_energy, texture_energy],
        medium_scale_edge_density_scores=context.measurements.medium_scale_edge_density_scores,
        coarse_scale_edge_density_scores=context.measurements.coarse_scale_edge_density_scores,
        medium_scale_texture_energy_scores=context.measurements.medium_scale_texture_energy_scores,
        coarse_scale_texture_energy_scores=context.measurements.coarse_scale_texture_energy_scores,
        edge_persistence_scores=context.measurements.edge_persistence_scores,
        texture_retention_scores=context.measurements.texture_retention_scores,
    )
    _patch_practical_black_detector(monkeypatch)
    _patch_practical_blur_context(
        monkeypatch,
        _with_blur_context_measurements(context, measurements=softness_measurements),
    )
    _patch_practical_motion_metrics(
        monkeypatch,
        _motion_coherence_metrics(
            fine_scale_motion_energy=0.26,
            medium_scale_motion_energy=0.23,
            coarse_scale_motion_energy=0.19,
            motion_persistence=1.0,
            motion_coherence=1.0,
            incoherence_avg=0.03,
            incoherence_scores=[0.03, 0.03],
        ),
    )
    monkeypatch.setattr(
        "detector_lab.practical_alerts._neighbor_black_ratios",
        lambda analysis_slice: (0.0, 0.0),
    )

    row = analyze_practical_motion_blur_alert(analysis_slice)

    assert row["guardrail_reason"] == expected_guardrail_reason
    assert row["practical_detected"] is expected_detected
    if expected_detected:
        assert row["practical_score"] >= row["practical_threshold"]
    else:
        assert row["practical_score"] == 0.0


def test_evaluate_practical_alerts_formats_operator_message_from_score_fields() -> None:
    """Practical alerts should expose a stable operator-facing score message."""
    alerts = evaluate_practical_alerts(
        session_id="detector-lab:practical.motion",
        row={
            "analyzer": "practical_motion_blur_alert",
            "source_name": "sample.mp4 @ 00:00",
            "window_index": 0,
            "window_start_sec": 0.0,
            "practical_score": 0.68,
            "practical_threshold": 0.68,
            "practical_detected": True,
        },
    )

    assert len(alerts) == 1
    assert alerts[0].title == "Practical motion blur alert"
    assert alerts[0].message == "sample.mp4 @ 00:00 scored 0.680 against threshold 0.680."


def test_prefers_motion_blur_classification_accepts_exact_boundary(
    monkeypatch, tmp_path: Path
) -> None:
    """The blur-to-motion preference should activate at the exact configured boundaries."""
    context = _fake_blur_context(tmp_path)
    boundary_measurements = BlurWindowMeasurements(
        frame_scores=context.measurements.frame_scores,
        motion_scores=[0.0, 0.12, 0.21],
        sharpness_p10=context.measurements.sharpness_p10,
        sharpness_p90=context.measurements.sharpness_p90,
        absolute_blur_scores=context.measurements.absolute_blur_scores,
        dynamic_blur_scores=context.measurements.dynamic_blur_scores,
        edge_density_scores=context.measurements.edge_density_scores,
        mean_edge_strength_scores=context.measurements.mean_edge_strength_scores,
        texture_energy_scores=context.measurements.texture_energy_scores,
        medium_scale_edge_density_scores=context.measurements.medium_scale_edge_density_scores,
        coarse_scale_edge_density_scores=context.measurements.coarse_scale_edge_density_scores,
        medium_scale_texture_energy_scores=context.measurements.medium_scale_texture_energy_scores,
        coarse_scale_texture_energy_scores=context.measurements.coarse_scale_texture_energy_scores,
        edge_persistence_scores=context.measurements.edge_persistence_scores,
        texture_retention_scores=context.measurements.texture_retention_scores,
    )
    monkeypatch.setattr(
        "detector_lab.practical_alerts.compute_motion_coherence_multiscale",
        lambda **kwargs: MotionCoherenceMetrics(
            fine_scale_motion_energy=0.26,
            medium_scale_motion_energy=0.23,
            coarse_scale_motion_energy=0.19,
            motion_persistence=0.97,
            motion_coherence=0.97,
            incoherence_avg=0.03,
            incoherence_scores=[0.03, 0.03],
        ),
    )

    assert _prefers_motion_blur_classification(
        measurements=boundary_measurements,
        raw_frames=context.raw_frames,
        sample_width=context.sample_width,
        sample_height=context.sample_height,
    ) is True


def test_practical_blur_alert_v2_detects_exact_threshold_score(
    monkeypatch, tmp_path: Path
) -> None:
    """The calibrated blur alert should treat its exact threshold as a positive detection."""
    analysis_slice = _fake_slice(tmp_path)
    context = _fake_blur_context(tmp_path)
    monkeypatch.setattr(
        "detector_lab.practical_alerts.analyze_video_metrics",
        lambda **kwargs: {
            "source_group": kwargs["source_group"],
            "source_name": kwargs["source_name"],
            "processing_sec": 0.02,
            "black_segment_count": 0,
            "total_black_sec": 0.0,
            "longest_black_sec": 0.0,
            "black_ratio": 0.0,
        },
    )
    monkeypatch.setattr(
        "detector_lab.practical_alerts.prepare_blur_analysis_context",
        lambda slice_: context,
    )
    monkeypatch.setattr(
        "detector_lab.practical_alerts._prefers_motion_blur_classification",
        lambda **kwargs: False,
    )
    monkeypatch.setattr(
        "detector_lab.practical_alerts._weighted_geometric_blur_core",
        lambda **kwargs: 0.955,
    )

    row = analyze_practical_blur_alert_v2(analysis_slice)

    assert row["practical_score"] == 0.955
    assert row["practical_detected"] is True
