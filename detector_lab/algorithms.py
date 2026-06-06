"""Algorithm registry for detector-lab evaluations.

This module is the selection boundary for the detector lab. It adapts
production detectors to ``AnalysisSlice`` inputs and exposes experimental
variants under stable CLI-facing ids.
"""

from __future__ import annotations

from functools import partial
from typing import Callable

from analyzer_contract import AnalysisSlice
from detector_lab.blur_experiments import (
    BLUR_BLEND_SPECS_BY_ID,
    analyze_video_blur_dense_farneback_motion,
    analyze_video_blur_compression_robust,
    analyze_video_blur_generalized_consensus,
    analyze_video_blur_generalized_geom,
    analyze_video_blur_motion_coherent_v1,
    analyze_video_blur_multiscale_structure,
    analyze_video_blur_sparse_lk_motion,
    analyze_video_blur_with_blend,
)
from detector_lab.contracts import DetectorMetricRow, LabAlgorithmSpec
from detector_lab.practical_alerts import (
    analyze_practical_black_alert,
    analyze_practical_blur_alert,
    analyze_practical_blur_alert_v2,
    analyze_practical_blur_alert_v3,
    analyze_practical_motion_blur_alert,
    evaluate_practical_alerts,
)
from detectors import analyze_video_blur, analyze_video_metrics


def run_production_video_blur(analysis_slice: AnalysisSlice) -> DetectorMetricRow:
    """Run the production blur detector for one analysis slice."""
    return _run_production_detector(analyze_video_blur, analysis_slice)


def run_production_video_metrics(analysis_slice: AnalysisSlice) -> DetectorMetricRow:
    """Run the production black-screen metrics detector for one analysis slice."""
    return _run_production_detector(analyze_video_metrics, analysis_slice)


def _run_production_detector(
    analyzer: Callable[..., DetectorMetricRow],
    analysis_slice: AnalysisSlice,
) -> DetectorMetricRow:
    """Adapt one production detector to the lab ``AnalysisSlice`` input shape."""
    return analyzer(
        file_path=analysis_slice.file_path,
        source_group=analysis_slice.source_group,
        source_name=analysis_slice.source_name,
        window_index=analysis_slice.window_index,
        window_start_sec=analysis_slice.window_start_sec,
        window_duration_sec=analysis_slice.window_duration_sec,
    )


def _build_algorithm_spec(
    *,
    algorithm_id: str,
    detector_id: str,
    description: str,
    runner: Callable[[AnalysisSlice], DetectorMetricRow],
    rule_detector_id: str | None = None,
    alert_rule_runner=None,
) -> LabAlgorithmSpec:
    """Build one registry entry with the current detector-lab defaults."""
    return LabAlgorithmSpec(
        algorithm_id=algorithm_id,
        detector_id=detector_id,
        description=description,
        runner=runner,
        rule_detector_id=rule_detector_id,
        alert_rule_runner=alert_rule_runner,
    )


def _build_blur_experiment_spec(blend_id: str) -> LabAlgorithmSpec:
    """Build one blend-based blur experiment from a registered blend id."""
    blend_spec = BLUR_BLEND_SPECS_BY_ID[blend_id]
    return _build_algorithm_spec(
        algorithm_id=f"experimental.video_blur.{blend_spec.blend_id}_v1",
        detector_id="video_blur",
        description=blend_spec.description,
        runner=partial(analyze_video_blur_with_blend, blend_spec=blend_spec),
        rule_detector_id="video_blur",
    )


LAB_ALGORITHMS: tuple[LabAlgorithmSpec, ...] = (
    _build_algorithm_spec(
        algorithm_id="production.video_blur.motion_guard_v1",
        detector_id="video_blur",
        description="Production blur detector with motion-aware alert guardrails.",
        runner=run_production_video_blur,
        rule_detector_id="video_blur",
    ),
    _build_blur_experiment_spec("weighted_soft"),
    _build_blur_experiment_spec("rms_soft"),
    _build_blur_experiment_spec("agreement_soft"),
    _build_algorithm_spec(
        algorithm_id="experimental.video_blur.compression_robust_v1",
        detector_id="video_blur",
        description="Softer blur blend with broad-structure relief for compressed footage.",
        runner=analyze_video_blur_compression_robust,
        rule_detector_id="video_blur",
    ),
    _build_algorithm_spec(
        algorithm_id="experimental.video_blur.generalized_geom_v1",
        detector_id="video_blur",
        description="Geometric blur core plus broad-structure relief for robust cross-source comparisons.",
        runner=analyze_video_blur_generalized_geom,
        rule_detector_id="video_blur",
    ),
    _build_algorithm_spec(
        algorithm_id="experimental.video_blur.generalized_consensus_v1",
        detector_id="video_blur",
        description="Consensus blur core plus broad-structure relief for adaptable blur scoring.",
        runner=analyze_video_blur_generalized_consensus,
        rule_detector_id="video_blur",
    ),
    _build_algorithm_spec(
        algorithm_id="experimental.video_blur.multiscale_structure_v1",
        detector_id="video_blur",
        description="Blur blend with coarse-scale structure persistence relief.",
        runner=analyze_video_blur_multiscale_structure,
        rule_detector_id="video_blur",
    ),
    _build_algorithm_spec(
        algorithm_id="experimental.video_blur.motion_coherent_v1",
        detector_id="video_blur",
        description="Blur detector using multiscale motion coherence to distinguish real motion from blur.",
        runner=analyze_video_blur_motion_coherent_v1,
        rule_detector_id="video_blur",
    ),
    _build_algorithm_spec(
        algorithm_id="experimental.video_blur.sparse_lk_motion_v1",
        detector_id="video_blur",
        description="Motion-blur candidate using sparse Lucas-Kanade optical flow support.",
        runner=analyze_video_blur_sparse_lk_motion,
        rule_detector_id="video_blur",
    ),
    _build_algorithm_spec(
        algorithm_id="experimental.video_blur.dense_farneback_motion_v1",
        detector_id="video_blur",
        description="Motion-blur candidate using dense Farneback optical flow support.",
        runner=analyze_video_blur_dense_farneback_motion,
        rule_detector_id="video_blur",
    ),
    _build_algorithm_spec(
        algorithm_id="production.video_metrics.black_screen_v1",
        detector_id="video_metrics",
        description="Production black-screen metrics detector and alert rule.",
        runner=run_production_video_metrics,
        rule_detector_id="video_metrics",
    ),
    _build_algorithm_spec(
        algorithm_id="practical.black_frame_alert_v1",
        detector_id="practical_black_alert",
        description="Simple black-frame alert with ratio-first scoring.",
        runner=analyze_practical_black_alert,
        alert_rule_runner=evaluate_practical_alerts,
    ),
    _build_algorithm_spec(
        algorithm_id="practical.blur_alert_v1",
        detector_id="practical_blur_alert",
        description="Simple blur alert with black-frame guardrails and motion penalty.",
        runner=analyze_practical_blur_alert,
        alert_rule_runner=evaluate_practical_alerts,
    ),
    _build_algorithm_spec(
        algorithm_id="practical.blur_alert_v2",
        detector_id="practical_blur_alert_v2",
        description="Calibrated blur alert using absolute blur, medium-scale texture, and edge density.",
        runner=analyze_practical_blur_alert_v2,
        alert_rule_runner=evaluate_practical_alerts,
    ),
    _build_algorithm_spec(
        algorithm_id="practical.blur_alert_v3",
        detector_id="practical_blur_alert_v3",
        description="Calibrated blur alert with a dark-frame guardrail on top of the v2 feature core.",
        runner=analyze_practical_blur_alert_v3,
        alert_rule_runner=evaluate_practical_alerts,
    ),
    _build_algorithm_spec(
        algorithm_id="practical.motion_blur_alert_v1",
        detector_id="practical_motion_blur_alert",
        description="Simple motion-blur alert with black and softness guardrails.",
        runner=analyze_practical_motion_blur_alert,
        alert_rule_runner=evaluate_practical_alerts,
    ),
)

DEFAULT_ALGORITHM_IDS: tuple[str, ...] = (
    "production.video_blur.motion_guard_v1",
    "production.video_metrics.black_screen_v1",
)
ALGORITHMS_BY_ID: dict[str, LabAlgorithmSpec] = {
    spec.algorithm_id: spec for spec in LAB_ALGORITHMS
}


def list_algorithm_ids() -> tuple[str, ...]:
    """Return known lab algorithm ids in stable display order."""
    return tuple(spec.algorithm_id for spec in LAB_ALGORITHMS)


def resolve_algorithm_specs(algorithm_ids: tuple[str, ...]) -> tuple[LabAlgorithmSpec, ...]:
    """Resolve configured ids and fail fast on unknown algorithm references."""
    unknown_ids = tuple(
        algorithm_id
        for algorithm_id in algorithm_ids
        if algorithm_id not in ALGORITHMS_BY_ID
    )
    if unknown_ids:
        joined_ids = ", ".join(unknown_ids)
        raise ValueError(f"Unknown detector_lab algorithm id(s): {joined_ids}")
    return tuple(ALGORITHMS_BY_ID[algorithm_id] for algorithm_id in algorithm_ids)


def algorithm_ids_for_detectors(detector_ids: tuple[str, ...]) -> tuple[str, ...]:
    """Return production baseline ids for the CLI ``--detectors`` shortcut."""
    return tuple(
        spec.algorithm_id
        for spec in LAB_ALGORITHMS
        if spec.algorithm_id.startswith("production.")
        and spec.detector_id in detector_ids
        and spec.rule_detector_id == spec.detector_id
    )
