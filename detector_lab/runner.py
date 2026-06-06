"""Execution runner for local detector-lab evaluations.

The runner is intentionally thin. It discovers slices, resolves algorithms,
resets per-run alert state, and forwards rows to the reporting layer. Detector
logic, experiment math, and CSV shaping stay outside this module.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from alert_rules import evaluate_alerts, reset_session_rule_state
from analyzer_contract import AnalysisSlice, InputMode
from detector_lab.algorithms import DEFAULT_ALGORITHM_IDS, resolve_algorithm_specs
from detector_lab.contracts import (
    LabEvaluationOutputProfile,
    LabAlgorithmSpec,
    LabEvaluationRow,
    build_algorithm_session_id,
    normalize_input_path,
)
from detector_lab.reporting import (
    build_eval_row,
    build_ground_truth_lookup,
    write_eval_csv,
)
from session_runner_discovery import discover_input_slices, probe_video_duration


@dataclass(frozen=True)
class DetectorLabConfig:
    """Configuration for one detector-lab evaluation run."""

    input_path: Path
    mode: InputMode
    output_csv: Path
    algorithm_ids: tuple[str, ...] = DEFAULT_ALGORITHM_IDS
    start_window: int = 0
    max_windows: int | None = None
    session_id: str = "detector-lab"
    output_profile: LabEvaluationOutputProfile = "full"


@dataclass(frozen=True)
class DetectorLabBatchConfig:
    """Configuration for one multi-input run that writes one combined CSV."""

    input_paths: tuple[Path, ...]
    mode: InputMode
    output_csv: Path
    algorithm_ids: tuple[str, ...] = DEFAULT_ALGORITHM_IDS
    start_window: int = 0
    max_windows: int | None = None
    session_id: str = "detector-lab"
    output_profile: LabEvaluationOutputProfile = "full"


@dataclass(frozen=True)
class DetectorLabSplitBatchConfig:
    """Configuration for one multi-input run that writes one CSV per input."""

    input_paths: tuple[Path, ...]
    mode: InputMode
    output_dir: Path
    algorithm_ids: tuple[str, ...] = DEFAULT_ALGORITHM_IDS
    start_window: int = 0
    max_windows: int | None = None
    session_id: str = "detector-lab"
    output_profile: LabEvaluationOutputProfile = "full"


@dataclass(frozen=True)
class DetectorLabWrittenOutput:
    """Summary of one CSV written by a split detector-lab batch run."""

    input_path: Path
    output_csv: Path
    raw_row_count: int


def run_detector_lab(config: DetectorLabConfig) -> list[LabEvaluationRow]:
    """Run one configured detector-lab evaluation and write its CSV output."""
    ground_truth_lookup = _ground_truth_lookup_for_inputs((config.input_path,))
    rows = _collect_eval_rows(
        config,
        ground_truth_summary=ground_truth_lookup.get(
            normalize_input_path(config.input_path),
            "",
        ),
    )
    write_eval_csv(config.output_csv, rows, output_profile=config.output_profile)
    return rows


def run_detector_lab_batch(config: DetectorLabBatchConfig) -> list[LabEvaluationRow]:
    """Run one multi-input detector-lab evaluation and write one combined CSV."""
    ground_truth_lookup = _ground_truth_lookup_for_inputs(config.input_paths)
    rows: list[LabEvaluationRow] = []
    for input_path in config.input_paths:
        rows.extend(
            _collect_eval_rows(
                _build_input_config(
                    input_path=input_path,
                    mode=config.mode,
                    output_csv=config.output_csv,
                    algorithm_ids=config.algorithm_ids,
                    start_window=config.start_window,
                    max_windows=config.max_windows,
                    session_id=config.session_id,
                    output_profile=config.output_profile,
                ),
                ground_truth_summary=ground_truth_lookup.get(
                    normalize_input_path(input_path),
                    "",
                ),
            )
        )

    write_eval_csv(config.output_csv, rows, output_profile=config.output_profile)
    return rows


def run_detector_lab_batch_split(
    config: DetectorLabSplitBatchConfig,
) -> list[DetectorLabWrittenOutput]:
    """Run the configured algorithms and write one CSV per input path."""
    outputs: list[DetectorLabWrittenOutput] = []
    ground_truth_lookup = _ground_truth_lookup_for_inputs(config.input_paths)
    for input_path in config.input_paths:
        output_csv = config.output_dir / f"{input_path.stem}_eval.csv"
        input_config = _build_input_config(
            input_path=input_path,
            mode=config.mode,
            output_csv=output_csv,
            algorithm_ids=config.algorithm_ids,
            start_window=config.start_window,
            max_windows=config.max_windows,
            session_id=config.session_id,
            output_profile=config.output_profile,
        )
        rows = _collect_eval_rows(
            input_config,
            ground_truth_summary=ground_truth_lookup.get(
                normalize_input_path(input_path),
                "",
            ),
        )
        write_eval_csv(output_csv, rows, output_profile=config.output_profile)
        outputs.append(
            DetectorLabWrittenOutput(
                input_path=input_path,
                output_csv=output_csv,
                raw_row_count=len(rows),
            )
        )
    return outputs


def _collect_eval_rows(
    config: DetectorLabConfig,
    *,
    ground_truth_summary: str,
) -> list[LabEvaluationRow]:
    """Collect evaluation rows for one input path without writing CSV yet."""
    algorithm_specs = resolve_algorithm_specs(config.algorithm_ids)
    _reset_algorithm_rule_state(config.session_id, algorithm_specs)

    slices = _limit_slices(
        _discover_lab_slices(config.mode, config.input_path),
        start_window=config.start_window,
        max_windows=config.max_windows,
    )
    rows: list[LabEvaluationRow] = []
    for analysis_slice in slices:
        for spec in algorithm_specs:
            detector_row = spec.runner(analysis_slice)
            alerts = _evaluate_algorithm_alerts(config.session_id, spec, detector_row)
            rows.append(
                build_eval_row(
                    spec=spec,
                    input_path=config.input_path,
                    ground_truth_summary=ground_truth_summary,
                    row=detector_row,
                    alerts=alerts,
                )
            )

    return rows


def _discover_lab_slices(mode: InputMode, input_path: Path) -> list[AnalysisSlice]:
    """Discover local slices with the same helper family used by production."""
    if mode == "api_stream":
        raise ValueError("detector_lab currently supports local video_files and video_segments only")
    return discover_input_slices(
        mode,
        input_path,
        supported_patterns={
            "video_segments": ("*.ts",),
            "video_files": ("*.mp4",),
            "api_stream": (),
        },
        duration_probe=probe_video_duration,
        api_stream_slice_discoverer=_unsupported_api_stream_discovery,
    )


def _unsupported_api_stream_discovery(*args, **kwargs):  # noqa: ANN002, ANN003
    """Raise the detector-lab restriction for unsupported ``api_stream`` inputs."""
    _ = (args, kwargs)
    raise ValueError("detector_lab does not evaluate api_stream sources yet")


def _limit_slices(
    slices: Iterable[AnalysisSlice],
    *,
    start_window: int,
    max_windows: int | None,
) -> list[AnalysisSlice]:
    """Apply optional start-window skipping and max-window truncation."""
    limited_slices = list(slices)[max(0, start_window) :]
    if max_windows is None:
        return limited_slices
    return limited_slices[: max(0, max_windows)]


def _evaluate_algorithm_alerts(
    session_id: str,
    spec: LabAlgorithmSpec,
    row: dict[str, object],
):
    """Evaluate the alert path declared by one lab algorithm spec."""
    scoped_session_id = build_algorithm_session_id(session_id, spec)
    if spec.alert_rule_runner is not None:
        return spec.alert_rule_runner(scoped_session_id, row)
    if spec.rule_detector_id is None:
        return []
    return evaluate_alerts(
        scoped_session_id,
        spec.rule_detector_id,
        row,
    )


def _build_input_config(
    *,
    input_path: Path,
    mode: InputMode,
    output_csv: Path,
    algorithm_ids: tuple[str, ...],
    start_window: int,
    max_windows: int | None,
    session_id: str,
    output_profile: LabEvaluationOutputProfile,
) -> DetectorLabConfig:
    """Build a single-input config derived from a batch-oriented request."""
    return DetectorLabConfig(
        input_path=input_path,
        mode=mode,
        output_csv=output_csv,
        algorithm_ids=algorithm_ids,
        start_window=start_window,
        max_windows=max_windows,
        session_id=f"{session_id}:{input_path.stem}",
        output_profile=output_profile,
    )


def _ground_truth_lookup_for_inputs(input_paths: Iterable[Path]) -> dict[str, str]:
    """Return cached ground-truth summaries for a set of input paths."""
    return build_ground_truth_lookup(tuple(input_paths))


def _reset_algorithm_rule_state(
    session_id: str,
    algorithm_specs: Iterable[LabAlgorithmSpec],
) -> None:
    """Reset rolling alert-rule state for each algorithm before a comparison run."""
    for spec in algorithm_specs:
        reset_session_rule_state(build_algorithm_session_id(session_id, spec))
