"""Detector-lab runner, CLI, and reporting contract tests.

These tests protect the experimental harness around detector algorithms: input
selection, batch execution, export shape, and alert presentation. Threshold
and detector-policy assertions intentionally remain in their dedicated modules.
"""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from analyzer_contract import AnalysisSlice
from detector_lab.algorithms import DEFAULT_ALGORITHM_IDS, LabAlgorithmSpec
from detector_lab.cli import (
    _resolve_fixture_set_output_profile,
    _resolve_fixture_set_paths,
    _resolve_split_output_dir,
    build_parser,
)
from detector_lab.contracts import field_names_for_output_profile
from detector_lab.practical_alerts import evaluate_practical_alerts
from detector_lab.reporting import build_eval_row, build_ground_truth_lookup
from detector_lab.runner import (
    DetectorLabBatchConfig,
    DetectorLabConfig,
    DetectorLabSplitBatchConfig,
    run_detector_lab,
    run_detector_lab_batch,
    run_detector_lab_batch_split,
)
from session_models import AlertEvent
from tests.detector_lab_test_support import fake_slice

REPO_ROOT = Path(__file__).resolve().parent.parent


def _patch_empty_ground_truth_lookup(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep runner-focused tests off the repo-local ground-truth cache path."""
    monkeypatch.setattr(
        "detector_lab.runner._ground_truth_lookup_for_inputs",
        lambda input_paths: {str(path): "" for path in input_paths},
    )


def test_run_detector_lab_writes_csv_rows(monkeypatch, tmp_path: Path) -> None:
    """Lab runs should write one comparable CSV row per detector and window."""
    analysis_slice = fake_slice(tmp_path)
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


def test_detector_lab_cli_accepts_normal_baseline_fixture_set_with_split_output() -> (
    None
):
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


def test_all_video_files_fixture_set_includes_detector_and_available_baseline_mp4_inputs() -> (
    None
):
    """The combined fixture set should include detector fixtures plus any local baseline clips."""
    paths = _resolve_fixture_set_paths("all_video_files")
    baseline_paths = _resolve_fixture_set_paths("normal_baseline_video_files")

    names = {path.name for path in paths}
    assert "clean_baseline_long.mp4" in names
    assert {path.name for path in baseline_paths}.issubset(names)


def test_run_detector_lab_can_start_after_given_window(
    monkeypatch, tmp_path: Path
) -> None:
    """Lab runs should be able to skip early windows and start later in a clip."""
    first_slice = fake_slice(tmp_path)
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


def test_run_detector_lab_supports_custom_rule_variants(
    monkeypatch, tmp_path: Path
) -> None:
    """Experimental rule variants should run without touching production rules."""
    analysis_slice = fake_slice(tmp_path)
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
    first_slice = fake_slice(tmp_path)
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
    assert {row["input_path"] for row in rows} == {
        str(first_slice.file_path),
        str(second_path),
    }


def test_run_detector_lab_batch_split_writes_one_csv_per_input(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Split fixture-set runs should write one output CSV per configured input."""
    first_slice = fake_slice(tmp_path)
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
    analysis_slice = fake_slice(tmp_path)
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


def test_fixture_set_output_profile_uses_full_export_for_duplicate_detector_algorithms() -> (
    None
):
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


def test_fixture_set_output_profile_keeps_compact_export_for_one_algorithm_per_detector() -> (
    None
):
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


def test_build_eval_row_includes_ground_truth_summary(tmp_path: Path) -> None:
    """Known checked-in fixtures should carry compact ground-truth context in CSV rows."""
    spec = LabAlgorithmSpec(
        algorithm_id="experimental.video_blur.example_v1",
        detector_id="video_blur",
        description="Example.",
        runner=lambda slice_: {},  # pragma: no cover - not used
    )
    fixture_path = REPO_ROOT / "tests/fixtures/media/video_files/blur_middle_long.mp4"
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
    assert '"expected_blur_true_count":10' in row["ground_truth_summary"]
    assert (
        '"per_second_label_legend":"0=normal,1=black,2=blur,3=motion_blur,9=unknown"'
        in row["ground_truth_summary"]
    )
    assert '"per_second_labels":"0,0,0,2,2,2,0,0,0,0"' in row["ground_truth_summary"]


def test_build_ground_truth_lookup_persists_stream_summary(tmp_path: Path) -> None:
    """Ground-truth summaries should be cached once per input path and reloaded later."""
    fixture_path = REPO_ROOT / "tests/fixtures/media/video_files/blur_middle_long.mp4"
    cache_path = tmp_path / "ground_truth_stream_cache.json"

    first_lookup = build_ground_truth_lookup((fixture_path,), cache_path=cache_path)
    second_lookup = build_ground_truth_lookup((fixture_path,), cache_path=cache_path)

    assert cache_path.exists()
    assert first_lookup[str(fixture_path)] == second_lookup[str(fixture_path)]
    assert "mp4_blur_middle_long_dual_detectors" in first_lookup[str(fixture_path)]
    assert '"schema_version": "ground_truth_summary_v4"' in cache_path.read_text(
        encoding="utf-8"
    )


def test_build_ground_truth_lookup_supports_label_only_baseline_clips(
    tmp_path: Path,
) -> None:
    """Baseline clips with only per-second labels should still export ground truth."""
    fixture_path = (
        REPO_ROOT
        / "tests/fixtures/media/election_clips/normal_baseline/010300111_20260419_202346_0000-0030.mp4"
    )
    cache_path = tmp_path / "ground_truth_stream_cache.json"

    lookup = build_ground_truth_lookup((fixture_path,), cache_path=cache_path)
    summary = lookup[str(fixture_path)]

    assert (
        '"per_second_label_legend":"0=normal,1=black,2=blur,3=motion_blur,9=unknown"'
        in summary
    )
    assert (
        '"per_second_labels":"3,3,3,3,3,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0"'
        in summary
    )
    assert "expected_alert_count" not in summary


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
    assert (
        alerts[0].message == "sample.mp4 @ 00:00 scored 0.000 against threshold 0.000."
    )
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
    assert (
        alerts[0].message == "sample.mp4 @ 00:00 scored 0.680 against threshold 0.680."
    )
