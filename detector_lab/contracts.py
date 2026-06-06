"""Shared contracts for the detector-lab package.

``detector_lab`` is the project workbench for detector variants, practical
alert ideas, and side-by-side evaluation on fixture slices. This module keeps
that work readable by defining a small set of contracts for:

- lab algorithm runners
- CSV/export rows
- the stable fact seam used by practical alert policies
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Literal, TypedDict

from analyzer_contract import AnalysisSlice
from session_models import AlertEvent


DetectorMetricRow = dict[str, object]
LabAlgorithmRunner = Callable[[AnalysisSlice], DetectorMetricRow]
LabAlertRuleRunner = Callable[[str, DetectorMetricRow], list[AlertEvent]]


class LabEvaluationRow(TypedDict):
    """Flat CSV row for one algorithm evaluated on one analysis slice."""

    algorithm_id: str
    detector_id: str
    rule_detector_id: str
    input_path: str
    ground_truth_summary: str
    source_group: str
    source_name: str
    window_index: int | str
    window_start_sec: float | str
    window_duration_sec: float | str
    sample_count: int | str
    sharpness_p10: float | str
    sharpness_p90: float | str
    motion_mean: float | str
    motion_p90: float | str
    absolute_blur: float | str
    dynamic_blur: float | str
    edge_density: float | str
    mean_edge_strength: float | str
    texture_energy: float | str
    structure_strength: float | str
    medium_scale_edge_density: float | str
    coarse_scale_edge_density: float | str
    medium_scale_texture_energy: float | str
    coarse_scale_texture_energy: float | str
    edge_persistence: float | str
    texture_retention: float | str
    multiscale_structure_strength: float | str
    motion_blur_method: str
    optical_flow_mean: float | str
    optical_flow_p90: float | str
    optical_flow_coherence: float | str
    fine_scale_motion_energy: float | str
    medium_scale_motion_energy: float | str
    coarse_scale_motion_energy: float | str
    motion_persistence: float | str
    motion_coherence: float | str
    motion_incoherence_penalty: float | str
    blur_blend_id: str
    blur_score: float | str
    blur_detected: bool | str
    threshold_used: float | str
    black_detected: bool | str
    black_segment_count: int | str
    total_black_sec: float | str
    longest_black_sec: float | str
    black_ratio: float | str
    alert_count: int
    alert_titles: str
    alert_messages: str
    processing_sec: float | str
    practical_score: float | str
    practical_threshold: float | str
    practical_detected: bool | str
    guardrail_reason: str


@dataclass(frozen=True)
class ExperimentBlackFacts:
    """Black-screen facts reused by detector-lab alert experiments."""

    processing_sec: float
    black_segment_count: int
    total_black_sec: float
    longest_black_sec: float
    black_ratio: float


@dataclass(frozen=True)
class ExperimentBlurFacts:
    """Blur and structure facts reused by detector-lab alert experiments."""

    sample_count: int
    sharpness_p10: float
    sharpness_p90: float
    motion_mean: float
    motion_p90: float
    absolute_blur: float
    dynamic_blur: float
    edge_density: float
    texture_energy: float
    medium_scale_texture_energy: float
    structure_strength: float


@dataclass(frozen=True)
class ExperimentMotionFacts:
    """Motion-coherence facts reused by motion-aware detector-lab alerts."""

    fine_scale_motion_energy: float
    medium_scale_motion_energy: float
    coarse_scale_motion_energy: float
    motion_persistence: float
    motion_coherence: float
    motion_incoherence_penalty: float


@dataclass(frozen=True)
class ExperimentWindowFacts:
    """Stable detector-lab policy contract for one analyzed window.

    Practical alert experiments should depend on this value object rather than
    wiring together raw production rows, blur-experiment internals, and
    neighboring-window lookups themselves.
    """

    black: ExperimentBlackFacts
    blur: ExperimentBlurFacts
    dark_frame_ratio: float
    previous_black_ratio: float
    next_black_ratio: float
    motion: ExperimentMotionFacts | None = None


LAB_EVALUATION_FIELD_NAMES: tuple[str, ...] = (
    "algorithm_id",
    "detector_id",
    "rule_detector_id",
    "input_path",
    "ground_truth_summary",
    "source_group",
    "source_name",
    "window_index",
    "window_start_sec",
    "window_duration_sec",
    "sample_count",
    "sharpness_p10",
    "sharpness_p90",
    "motion_mean",
    "motion_p90",
    "absolute_blur",
    "dynamic_blur",
    "edge_density",
    "mean_edge_strength",
    "texture_energy",
    "structure_strength",
    "medium_scale_edge_density",
    "coarse_scale_edge_density",
    "medium_scale_texture_energy",
    "coarse_scale_texture_energy",
    "edge_persistence",
    "texture_retention",
    "multiscale_structure_strength",
    "motion_blur_method",
    "optical_flow_mean",
    "optical_flow_p90",
    "optical_flow_coherence",
    "fine_scale_motion_energy",
    "medium_scale_motion_energy",
    "coarse_scale_motion_energy",
    "motion_persistence",
    "motion_coherence",
    "motion_incoherence_penalty",
    "blur_blend_id",
    "blur_score",
    "blur_detected",
    "threshold_used",
    "black_detected",
    "black_segment_count",
    "total_black_sec",
    "longest_black_sec",
    "black_ratio",
    "alert_count",
    "alert_titles",
    "alert_messages",
    "processing_sec",
    "practical_score",
    "practical_threshold",
    "practical_detected",
    "guardrail_reason",
)

PRODUCTION_FIXTURE_EVALUATION_FIELD_NAMES: tuple[str, ...] = (
    "row_index",
    "input_path",
    "ground_truth_summary",
    "source_name",
    "window_index",
    "window_start_sec",
    "window_duration_sec",
    "blur_algorithm_id",
    "blur_sample_count",
    "blur_sharpness_p10",
    "blur_sharpness_p90",
    "blur_motion_mean",
    "blur_motion_p90",
    "blur_absolute_blur",
    "blur_dynamic_blur",
    "blur_edge_density",
    "blur_mean_edge_strength",
    "blur_texture_energy",
    "blur_structure_strength",
    "blur_medium_scale_edge_density",
    "blur_coarse_scale_edge_density",
    "blur_medium_scale_texture_energy",
    "blur_coarse_scale_texture_energy",
    "blur_edge_persistence",
    "blur_texture_retention",
    "blur_multiscale_structure_strength",
    "blur_motion_blur_method",
    "blur_optical_flow_mean",
    "blur_optical_flow_p90",
    "blur_optical_flow_coherence",
    "blur_fine_scale_motion_energy",
    "blur_medium_scale_motion_energy",
    "blur_coarse_scale_motion_energy",
    "blur_motion_persistence",
    "blur_motion_coherence",
    "blur_motion_incoherence_penalty",
    "blur_blend_id",
    "blur_score",
    "blur_detected",
    "blur_threshold_used",
    "blur_alert_count",
    "blur_alert_titles",
    "blur_processing_sec",
    "black_algorithm_id",
    "black_detected",
    "black_segment_count",
    "black_total_sec",
    "black_longest_sec",
    "black_ratio",
    "black_alert_count",
    "black_alert_titles",
    "black_processing_sec",
)

LabEvaluationOutputProfile = Literal["full", "production_fixture_compact"]


def field_names_for_output_profile(output_profile: LabEvaluationOutputProfile) -> tuple[str, ...]:
    """Return the CSV field order for one detector-lab export profile."""
    if output_profile == "full":
        return LAB_EVALUATION_FIELD_NAMES
    if output_profile == "production_fixture_compact":
        return PRODUCTION_FIXTURE_EVALUATION_FIELD_NAMES
    raise ValueError(f"Unknown detector-lab output profile: {output_profile}")


@dataclass(frozen=True)
class LabAlgorithmSpec:
    """Registry entry for one detector-lab algorithm."""

    algorithm_id: str
    detector_id: str
    description: str
    runner: LabAlgorithmRunner
    rule_detector_id: str | None = None
    alert_rule_runner: LabAlertRuleRunner | None = None

    @property
    def evaluates_alerts(self) -> bool:
        """Return whether this algorithm declares an alert-evaluation path."""
        return self.rule_detector_id is not None or self.alert_rule_runner is not None


def build_algorithm_session_id(session_id: str, spec: LabAlgorithmSpec) -> str:
    """Return a session id namespaced to one compared algorithm variant."""
    return f"{session_id}:{spec.algorithm_id}"


def normalize_input_path(input_path: Path) -> str:
    """Return the serialized media path used in detector-lab exports."""
    return str(input_path)
