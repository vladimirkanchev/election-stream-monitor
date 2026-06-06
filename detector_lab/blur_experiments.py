"""Blur-detector experiments built on top of production sampling helpers.

This module is the blur workbench for ``detector_lab``. The current structure
separates three experiment families so their intent stays visible:

- blur blends over the shared production-style measurements
- structure-relief variants that step back when broad structure survives
- motion/flow variants that add motion-specific evidence

Each experiment reuses the same extraction and base measurement pipeline and
changes mainly the scoring layer. That keeps comparisons fair and makes it
clear which pieces are production-adjacent versus exploratory.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import sqrt
from pathlib import Path
import time
from typing import Callable

import config
from analyzer_contract import AnalysisSlice
from detectors import (
    _clamp,
    _display_source_labels,
    _extract_sampled_gray_frames,
    _is_effectively_black_frame,
    _frame_sharpness_score,
    _frame_transition_motion_scores,
    _longest_threshold_run,
    _mean,
    _percentile,
    _resolve_blur_sample_fps,
    _resolve_blur_sample_size,
    _rolling_window_medians,
)
from detector_lab.contracts import DetectorMetricRow
from source_validation import validate_local_media_size


BlurBlend = Callable[[float, float], float]
BlurExperimentComputationBuilder = Callable[["BlurAnalysisContext"], "BlurExperimentComputation"]
EDGE_ACTIVE_THRESHOLD = 16
MIN_DOWNSAMPLED_DIMENSION = 8
_SUMMARY_PERCENTILE = 50


@dataclass(frozen=True)
class BlurBlendSpec:
    """Named two-signal blur combiner used by blend-driven experiments."""

    blend_id: str
    description: str
    combine: BlurBlend


@dataclass(frozen=True)
class StructureReliefVariantSpec:
    """Named structure-relief variant built on a shared base blur combiner."""

    variant_id: str
    base_blend: BlurBlend
    relief_scale: float = 0.35


@dataclass(frozen=True)
class MotionFlowVariantSpec:
    """Named motion/flow variant built on one optical-flow backend."""

    variant_id: str
    method: str


@dataclass(frozen=True)
class BlurWindowMeasurements:
    """Per-window features reused by multiple blur experiments."""

    frame_scores: list[float]
    motion_scores: list[float]
    sharpness_p10: float
    sharpness_p90: float
    absolute_blur_scores: list[float]
    dynamic_blur_scores: list[float]
    edge_density_scores: list[float]
    mean_edge_strength_scores: list[float]
    texture_energy_scores: list[float]
    medium_scale_edge_density_scores: list[float]
    coarse_scale_edge_density_scores: list[float]
    medium_scale_texture_energy_scores: list[float]
    coarse_scale_texture_energy_scores: list[float]
    edge_persistence_scores: list[float]
    texture_retention_scores: list[float]

    @property
    def motion_mean(self) -> float:
        return _mean(self.motion_scores)

    @property
    def motion_p90(self) -> float:
        return _percentile(self.motion_scores, 90) if self.motion_scores else 0.0

    @property
    def edge_density(self) -> float:
        return _median_score(self.edge_density_scores)

    @property
    def mean_edge_strength(self) -> float:
        return _median_score(self.mean_edge_strength_scores)

    @property
    def texture_energy(self) -> float:
        return _median_score(self.texture_energy_scores)

    @property
    def medium_scale_edge_density(self) -> float:
        return _median_score(self.medium_scale_edge_density_scores)

    @property
    def coarse_scale_edge_density(self) -> float:
        return _median_score(self.coarse_scale_edge_density_scores)

    @property
    def medium_scale_texture_energy(self) -> float:
        return _median_score(self.medium_scale_texture_energy_scores)

    @property
    def coarse_scale_texture_energy(self) -> float:
        return _median_score(self.coarse_scale_texture_energy_scores)

    @property
    def edge_persistence(self) -> float:
        return _median_score(self.edge_persistence_scores)

    @property
    def texture_retention(self) -> float:
        return _median_score(self.texture_retention_scores)


@dataclass(frozen=True)
class BlurAnalysisContext:
    """Prepared extraction and measurement context for one analysis slice.

    This is the supported shared input for experiment variants: one validated
    slice, one sampled grayscale frame set, and one reusable measurement pack.
    """

    analysis_slice: AnalysisSlice
    display_source_name: str
    display_source_group: str
    threshold: float
    start_time: float
    sample_width: int
    sample_height: int
    raw_frames: list[bytes]
    measurements: BlurWindowMeasurements


@dataclass(frozen=True)
class BlurExperimentComputation:
    """Computed per-frame experiment score payload ready for result finalization."""

    per_frame_blur_scores: list[float]
    extra_metrics: dict[str, object]


def analyze_video_blur_with_blend(
    analysis_slice: AnalysisSlice,
    *,
    blend_spec: BlurBlendSpec,
) -> DetectorMetricRow:
    """Run one blend-family blur experiment over shared window measurements."""
    return _run_blend_family_variant(
        analysis_slice,
        blend_spec=blend_spec,
    )


def _run_blend_family_variant(
    analysis_slice: AnalysisSlice,
    *,
    blend_spec: BlurBlendSpec,
) -> DetectorMetricRow:
    """Run one blend-family blur experiment variant."""
    return _run_blur_experiment(
        analysis_slice,
        blur_blend_id=blend_spec.blend_id,
        computation_builder=lambda context: BlurExperimentComputation(
            per_frame_blur_scores=_blend_absolute_and_dynamic_scores(
                context.measurements,
                blend_spec.combine,
            ),
            extra_metrics={},
        ),
    )


def prepare_blur_analysis_context(analysis_slice: AnalysisSlice) -> BlurAnalysisContext:
    """Validate input, sample frames, and collect shared measurements once.

    This is the public entry point that practical alerts and experiment runners
    should use when they need the shared blur-analysis context.
    """
    video_path = Path(analysis_slice.file_path)
    validate_local_media_size(video_path)
    start_time = time.time()
    threshold = config.VIDEO_BLUR_ALERT_THRESHOLD
    display_source_name, display_source_group = _display_source_labels(
        video_path,
        source_group=analysis_slice.source_group,
        source_name=analysis_slice.source_name,
    )

    sample_width, sample_height = _resolve_blur_sample_size(video_path)
    sample_fps = _resolve_blur_sample_fps(analysis_slice.window_duration_sec)
    raw_frames = _extract_sampled_gray_frames(
        file_path=video_path,
        width=sample_width,
        height=sample_height,
        fps=sample_fps,
        max_samples=config.VIDEO_BLUR_MAX_SAMPLES,
        window_start_sec=analysis_slice.window_start_sec,
        window_duration_sec=analysis_slice.window_duration_sec,
    )
    raw_frames = [
        pixels
        for pixels in raw_frames
        if not _is_effectively_black_frame(pixels)
    ]
    measurements = _measure_blur_window(
        width=sample_width,
        height=sample_height,
        raw_frames=raw_frames,
    )
    return BlurAnalysisContext(
        analysis_slice=analysis_slice,
        display_source_name=display_source_name,
        display_source_group=display_source_group,
        threshold=threshold,
        start_time=start_time,
        sample_width=sample_width,
        sample_height=sample_height,
        raw_frames=raw_frames,
        measurements=measurements,
    )


def compute_motion_coherence_multiscale(
    *,
    raw_frames: list[bytes],
    width: int,
    height: int,
):
    """Measure motion signal persistence and alignment across multiple scales.

    This stays public because both detector variants and practical alert
    experiments need the same motion-coherence view without re-implementing it.
    """
    if len(raw_frames) < 2:
        return MotionCoherenceMetrics(
            fine_scale_motion_energy=0.0,
            medium_scale_motion_energy=0.0,
            coarse_scale_motion_energy=0.0,
            motion_persistence=0.0,
            motion_coherence=0.0,
            incoherence_avg=0.0,
            incoherence_scores=[],
        )

    fine_motion_energies = _compute_frame_motion_energies(
        raw_frames=raw_frames,
        width=width,
        height=height,
    )
    medium_width, medium_height, medium_frames = _downsample_frame_sequence(
        raw_frames=raw_frames,
        width=width,
        height=height,
        downsample_factor=1,
    )
    medium_motion_energies = _compute_frame_motion_energies(
        raw_frames=medium_frames,
        width=medium_width,
        height=medium_height,
    )
    coarse_width, coarse_height, coarse_frames = _downsample_frame_sequence(
        raw_frames=raw_frames,
        width=width,
        height=height,
        downsample_factor=2,
    )
    coarse_motion_energies = _compute_frame_motion_energies(
        raw_frames=coarse_frames,
        width=coarse_width,
        height=coarse_height,
    )
    fine_energy_mean = _mean(fine_motion_energies) if fine_motion_energies else 0.0
    medium_energy_mean = _mean(medium_motion_energies) if medium_motion_energies else 0.0
    coarse_energy_mean = _mean(coarse_motion_energies) if coarse_motion_energies else 0.0
    motion_persistence = _safe_ratio(
        (medium_energy_mean * 0.4) + (coarse_energy_mean * 0.6),
        fine_energy_mean,
    )
    fine_norm = fine_energy_mean / (fine_energy_mean + 1e-6)
    medium_norm = medium_energy_mean / (fine_energy_mean + 1e-6)
    coherence_alignment = 1.0 - min(abs(fine_norm - medium_norm), 1.0)
    motion_coherence = (motion_persistence * 0.6) + (coherence_alignment * 0.4)
    incoherence_scores = [
        _clamp(1.0 - ((medium_energy * 0.5) + (coarse_energy * 0.5) / (fine_energy + 1e-6)))
        if fine_energy > 1e-6
        else 0.0
        for fine_energy, medium_energy, coarse_energy in zip(
            fine_motion_energies,
            medium_motion_energies,
            coarse_motion_energies,
            strict=False,
        )
    ]
    incoherence_avg = _mean(incoherence_scores) if incoherence_scores else 0.0

    return MotionCoherenceMetrics(
        fine_scale_motion_energy=round(fine_energy_mean, 6),
        medium_scale_motion_energy=round(medium_energy_mean, 6),
        coarse_scale_motion_energy=round(coarse_energy_mean, 6),
        motion_persistence=round(motion_persistence, 6),
        motion_coherence=round(motion_coherence, 6),
        incoherence_avg=round(incoherence_avg, 6),
        incoherence_scores=incoherence_scores,
    )


def analyze_video_blur_compression_robust(
    analysis_slice: AnalysisSlice,
) -> DetectorMetricRow:
    """Run a blur experiment that softens blur when broad structure survives."""
    return _run_structure_relief_family_variant(
        analysis_slice,
        variant=StructureReliefVariantSpec(
            variant_id="compression_robust",
            base_blend=agreement_soft_blend,
        ),
    )


def analyze_video_blur_generalized_geom(
    analysis_slice: AnalysisSlice,
) -> DetectorMetricRow:
    """Run a geometric blur core plus broad-structure relief."""
    return _run_structure_relief_family_variant(
        analysis_slice,
        variant=StructureReliefVariantSpec(
            variant_id="generalized_geom",
            base_blend=geometric_core_blend,
        ),
    )


def analyze_video_blur_generalized_consensus(
    analysis_slice: AnalysisSlice,
) -> DetectorMetricRow:
    """Run a consensus blur core plus broad-structure relief."""
    return _run_structure_relief_family_variant(
        analysis_slice,
        variant=StructureReliefVariantSpec(
            variant_id="generalized_consensus",
            base_blend=consensus_core_blend,
        ),
    )


def analyze_video_blur_multiscale_structure(
    analysis_slice: AnalysisSlice,
) -> DetectorMetricRow:
    """Run a blur experiment that rewards structure surviving coarse scales."""
    return _run_blur_experiment(
        analysis_slice,
        blur_blend_id="multiscale_structure",
        computation_builder=_compute_multiscale_structure_experiment,
    )


def analyze_video_blur_sparse_lk_motion(
    analysis_slice: AnalysisSlice,
) -> DetectorMetricRow:
    """Run a motion-blur experiment using sparse Lucas-Kanade optical flow."""
    return _run_motion_flow_family_variant(
        analysis_slice,
        variant=MotionFlowVariantSpec(
            variant_id="sparse_lk",
            method="sparse_lk",
        ),
    )


def analyze_video_blur_dense_farneback_motion(
    analysis_slice: AnalysisSlice,
) -> DetectorMetricRow:
    """Run a motion-blur experiment using dense Farneback optical flow."""
    return _run_motion_flow_family_variant(
        analysis_slice,
        variant=MotionFlowVariantSpec(
            variant_id="dense_farneback",
            method="dense_farneback",
        ),
    )


def analyze_video_blur_with_optical_flow(
    analysis_slice: AnalysisSlice,
    *,
    method: str,
) -> DetectorMetricRow:
    """Combine base blur with optical-flow evidence for motion-blur scoring."""
    return _run_motion_flow_family_variant(
        analysis_slice,
        variant=MotionFlowVariantSpec(
            variant_id=method,
            method=method,
        ),
    )


def _run_motion_flow_family_variant(
    analysis_slice: AnalysisSlice,
    *,
    variant: MotionFlowVariantSpec,
) -> DetectorMetricRow:
    """Run one motion/flow blur experiment variant."""
    return _run_blur_experiment(
        analysis_slice,
        blur_blend_id=variant.variant_id,
        computation_builder=lambda context: _compute_optical_flow_experiment(
            context,
            method=variant.method,
        ),
    )


def analyze_video_blur_with_structure_relief(
    analysis_slice: AnalysisSlice,
    *,
    base_blend: BlurBlend,
    blur_blend_id: str,
    relief_scale: float = 0.35,
) -> DetectorMetricRow:
    """Run a structure-relief experiment with a swappable base blur core."""
    return _run_structure_relief_family_variant(
        analysis_slice,
        variant=StructureReliefVariantSpec(
            variant_id=blur_blend_id,
            base_blend=base_blend,
            relief_scale=relief_scale,
        ),
    )


def _run_structure_relief_family_variant(
    analysis_slice: AnalysisSlice,
    *,
    variant: StructureReliefVariantSpec,
) -> DetectorMetricRow:
    """Run one structure-relief blur experiment variant."""
    return _run_blur_experiment(
        analysis_slice,
        blur_blend_id=variant.variant_id,
        computation_builder=lambda context: _compute_structure_relief_experiment(
            context,
            base_blend=variant.base_blend,
            relief_scale=variant.relief_scale,
        ),
    )


def _run_blur_experiment(
    analysis_slice: AnalysisSlice,
    *,
    blur_blend_id: str,
    computation_builder: BlurExperimentComputationBuilder,
) -> DetectorMetricRow:
    """Run one shared blur-experiment workflow from prepared context to final row."""
    context = _prepare_blur_analysis_context(analysis_slice)
    computation = computation_builder(context)
    return _finalize_blur_result_row(
        context=context,
        per_frame_blur_scores=computation.per_frame_blur_scores,
        blur_blend_id=blur_blend_id,
        extra_metrics=computation.extra_metrics,
    )


def _blend_absolute_and_dynamic_scores(
    measurements: BlurWindowMeasurements,
    blend: BlurBlend,
) -> list[float]:
    """Return one per-frame score series from absolute and dynamic blur inputs."""
    return [
        blend(absolute_blur, dynamic_blur)
        for absolute_blur, dynamic_blur in zip(
            measurements.absolute_blur_scores,
            measurements.dynamic_blur_scores,
            strict=False,
        )
    ]


def _compute_multiscale_structure_experiment(
    context: BlurAnalysisContext,
) -> BlurExperimentComputation:
    """Compute the multiscale-structure experiment score payload."""
    scores = [
        multiscale_structure_blend(
            absolute_blur=absolute_blur,
            dynamic_blur=dynamic_blur,
            edge_persistence=edge_persistence,
            texture_retention=texture_retention,
            coarse_scale_edge_density=coarse_scale_edge_density,
            coarse_scale_texture_energy=coarse_scale_texture_energy,
        )
        for (
            absolute_blur,
            dynamic_blur,
            edge_persistence,
            texture_retention,
            coarse_scale_edge_density,
            coarse_scale_texture_energy,
        ) in zip(
            context.measurements.absolute_blur_scores,
            context.measurements.dynamic_blur_scores,
            context.measurements.edge_persistence_scores,
            context.measurements.texture_retention_scores,
            context.measurements.coarse_scale_edge_density_scores,
            context.measurements.coarse_scale_texture_energy_scores,
            strict=False,
        )
    ]
    return BlurExperimentComputation(per_frame_blur_scores=scores, extra_metrics={})


def _compute_optical_flow_experiment(
    context: BlurAnalysisContext,
    *,
    method: str,
) -> BlurExperimentComputation:
    """Compute the optical-flow-backed motion-blur experiment score payload."""
    flow_trace = _coerce_optical_flow_trace(
        _compute_optical_flow_trace(
            method=method,
            width=context.sample_width,
            height=context.sample_height,
            raw_frames=context.raw_frames,
        )
    )
    scores = [
        _optical_flow_motion_blur_score(
            absolute_blur=absolute_blur,
            dynamic_blur=dynamic_blur,
            optical_flow_mean=optical_flow_mean,
            optical_flow_p90=optical_flow_p90,
            optical_flow_coherence=optical_flow_coherence,
        )
        for absolute_blur, dynamic_blur, optical_flow_mean, optical_flow_p90, optical_flow_coherence in zip(
            context.measurements.absolute_blur_scores,
            context.measurements.dynamic_blur_scores,
            flow_trace.flow_mean_scores,
            flow_trace.flow_p90_scores,
            flow_trace.flow_coherence_scores,
            strict=False,
        )
    ]
    return BlurExperimentComputation(
        per_frame_blur_scores=scores,
        extra_metrics=_optical_flow_export_metrics(method=method, flow_trace=flow_trace),
    )


def _compute_structure_relief_experiment(
    context: BlurAnalysisContext,
    *,
    base_blend: BlurBlend,
    relief_scale: float,
) -> BlurExperimentComputation:
    """Compute the structure-relief experiment score payload."""
    scores = [
        structure_relief_blend(
            absolute_blur=absolute_blur,
            dynamic_blur=dynamic_blur,
            edge_density=edge_density,
            mean_edge_strength=mean_edge_strength,
            texture_energy=texture_energy,
            base_blend=base_blend,
            relief_scale=relief_scale,
        )
        for absolute_blur, dynamic_blur, edge_density, mean_edge_strength, texture_energy in zip(
            context.measurements.absolute_blur_scores,
            context.measurements.dynamic_blur_scores,
            context.measurements.edge_density_scores,
            context.measurements.mean_edge_strength_scores,
            context.measurements.texture_energy_scores,
            strict=False,
        )
    ]
    return BlurExperimentComputation(per_frame_blur_scores=scores, extra_metrics={})


def _prepare_blur_analysis_context(analysis_slice: AnalysisSlice) -> BlurAnalysisContext:
    """Compatibility alias for callers still patching the older private helper."""
    return prepare_blur_analysis_context(analysis_slice)


def _finalize_blur_result_row(
    *,
    context: BlurAnalysisContext,
    per_frame_blur_scores: list[float],
    blur_blend_id: str,
    extra_metrics: dict[str, object] | None = None,
) -> DetectorMetricRow:
    """Collapse per-frame scores into one detector-style result row."""
    window_size = min(
        config.VIDEO_BLUR_WINDOW_SIZE,
        len(per_frame_blur_scores) if per_frame_blur_scores else 1,
    )
    rolling_window_scores = _rolling_window_medians(per_frame_blur_scores, window_size)
    blur_score = round(max(rolling_window_scores, default=0.0), 3)
    consecutive_blurry_windows = _longest_threshold_run(
        rolling_window_scores,
        context.threshold,
    )
    return _build_blur_result_row(
        analysis_slice=context.analysis_slice,
        display_source_group=context.display_source_group,
        display_source_name=context.display_source_name,
        start_time=context.start_time,
        threshold=context.threshold,
        measurements=context.measurements,
        per_frame_blur_scores=per_frame_blur_scores,
        window_size=window_size,
        consecutive_blurry_windows=consecutive_blurry_windows,
        blur_score=blur_score,
        blur_blend_id=blur_blend_id,
        extra_metrics=extra_metrics or {},
    )


def _build_blur_result_row(
    *,
    analysis_slice: AnalysisSlice,
    display_source_group: str,
    display_source_name: str,
    start_time: float,
    threshold: float,
    measurements: BlurWindowMeasurements,
    per_frame_blur_scores: list[float],
    window_size: int,
    consecutive_blurry_windows: int,
    blur_score: float,
    blur_blend_id: str,
    extra_metrics: dict[str, object],
) -> DetectorMetricRow:
    """Build one flat detector-style blur result row for export and rule input."""
    required_windows = min(
        config.VIDEO_BLUR_MIN_CONSECUTIVE_WINDOWS,
        len(per_frame_blur_scores) if per_frame_blur_scores else 1,
    )
    structure_strength = _structure_strength(
        edge_density=measurements.edge_density,
        mean_edge_strength=measurements.mean_edge_strength,
        texture_energy=measurements.texture_energy,
    )
    multiscale_structure_strength = _multiscale_structure_strength(
        edge_persistence=measurements.edge_persistence,
        texture_retention=measurements.texture_retention,
        coarse_scale_edge_density=measurements.coarse_scale_edge_density,
        coarse_scale_texture_energy=measurements.coarse_scale_texture_energy,
    )

    row: DetectorMetricRow = {
        "analyzer": "video_blur",
        "source_type": "video",
        "source_group": display_source_group,
        "source_name": display_source_name,
        "window_index": analysis_slice.window_index,
        "window_start_sec": analysis_slice.window_start_sec,
        "window_duration_sec": analysis_slice.window_duration_sec,
        "timestamp_utc": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()),
        "processing_sec": round(time.time() - start_time, 3),
        "sample_count": len(measurements.frame_scores),
        "sharpness_p10": round(measurements.sharpness_p10, 3),
        "sharpness_p90": round(measurements.sharpness_p90, 3),
        "motion_mean": round(measurements.motion_mean, 3),
        "motion_p90": round(measurements.motion_p90, 3),
        "absolute_blur": round(max(measurements.absolute_blur_scores, default=0.0), 3),
        "dynamic_blur": round(max(measurements.dynamic_blur_scores, default=0.0), 3),
        "edge_density": round(measurements.edge_density, 3),
        "mean_edge_strength": round(measurements.mean_edge_strength, 3),
        "texture_energy": round(measurements.texture_energy, 3),
        "structure_strength": round(structure_strength, 3),
        "medium_scale_edge_density": round(measurements.medium_scale_edge_density, 3),
        "coarse_scale_edge_density": round(measurements.coarse_scale_edge_density, 3),
        "medium_scale_texture_energy": round(measurements.medium_scale_texture_energy, 3),
        "coarse_scale_texture_energy": round(measurements.coarse_scale_texture_energy, 3),
        "edge_persistence": round(measurements.edge_persistence, 3),
        "texture_retention": round(measurements.texture_retention, 3),
        "multiscale_structure_strength": round(multiscale_structure_strength, 3),
        "blur_blend_id": blur_blend_id,
        "blur_score": blur_score,
        "blur_detected": blur_score >= threshold
        and consecutive_blurry_windows >= required_windows,
        "threshold_used": threshold,
        "window_size": window_size,
        "consecutive_blurry_windows": consecutive_blurry_windows,
    }
    row.update(extra_metrics)
    return row


def _import_cv2():
    """Import OpenCV lazily so detector-lab keeps a soft dependency boundary."""
    try:
        import cv2  # type: ignore
    except ModuleNotFoundError as exc:  # pragma: no cover - exercised by runtime
        raise RuntimeError(
            "Optical-flow detector_lab experiments require opencv-python-headless."
        ) from exc
    return cv2


def _compute_optical_flow_trace(
    *,
    method: str,
    width: int,
    height: int,
    raw_frames: list[bytes],
) -> OpticalFlowTrace:
    """Return the configured optical-flow trace for one sampled window."""
    if method == "sparse_lk":
        return _compute_sparse_lk_flow_trace(width=width, height=height, raw_frames=raw_frames)
    if method == "dense_farneback":
        return _compute_dense_farneback_flow_trace(
            width=width,
            height=height,
            raw_frames=raw_frames,
        )
    raise ValueError(f"Unknown optical-flow blur method: {method}")


def _coerce_optical_flow_trace(trace: OpticalFlowTrace | dict[str, list[float]]) -> OpticalFlowTrace:
    """Accept the current trace dataclass and the older dict-shaped test patches."""
    if isinstance(trace, OpticalFlowTrace):
        return trace
    return OpticalFlowTrace(
        flow_mean_scores=list(trace.get("flow_mean_scores", [])),
        flow_p90_scores=list(trace.get("flow_p90_scores", [])),
        flow_coherence_scores=list(trace.get("flow_coherence_scores", [])),
    )


def _compute_sparse_lk_flow_trace(
    *,
    width: int,
    height: int,
    raw_frames: list[bytes],
) -> OpticalFlowTrace:
    """Return sparse Lucas-Kanade optical-flow summaries per sampled frame."""
    cv2 = _import_cv2()
    frames = _frames_to_cv2_gray_arrays(width=width, height=height, raw_frames=raw_frames)
    if not frames:
        return _empty_flow_trace()

    flow_mean_scores = [0.0]
    flow_p90_scores = [0.0]
    flow_coherence_scores = [0.0]

    feature_params = dict(maxCorners=100, qualityLevel=0.03, minDistance=7, blockSize=7)
    lk_params = dict(
        winSize=(15, 15),
        maxLevel=2,
        criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 10, 0.03),
    )

    for previous, current in zip(frames, frames[1:], strict=False):
        previous_points = cv2.goodFeaturesToTrack(previous, mask=None, **feature_params)
        if previous_points is None or len(previous_points) == 0:
            flow_mean_scores.append(0.0)
            flow_p90_scores.append(0.0)
            flow_coherence_scores.append(0.0)
            continue

        next_points, status, _ = cv2.calcOpticalFlowPyrLK(
            previous,
            current,
            previous_points,
            None,
            **lk_params,
        )
        if next_points is None or status is None:
            flow_mean_scores.append(0.0)
            flow_p90_scores.append(0.0)
            flow_coherence_scores.append(0.0)
            continue

        valid_old = previous_points[status.flatten() == 1]
        valid_new = next_points[status.flatten() == 1]
        if len(valid_old) == 0 or len(valid_new) == 0:
            flow_mean_scores.append(0.0)
            flow_p90_scores.append(0.0)
            flow_coherence_scores.append(0.0)
            continue

        vectors = valid_new - valid_old
        metrics = _flow_vector_metrics(
            vectors=vectors.reshape(-1, 2),
            width=width,
            height=height,
        )
        flow_mean_scores.append(metrics["mean"])
        flow_p90_scores.append(metrics["p90"])
        flow_coherence_scores.append(metrics["coherence"])

    return _build_flow_trace(
        flow_mean_scores=flow_mean_scores,
        flow_p90_scores=flow_p90_scores,
        flow_coherence_scores=flow_coherence_scores,
    )


def _compute_dense_farneback_flow_trace(
    *,
    width: int,
    height: int,
    raw_frames: list[bytes],
) -> OpticalFlowTrace:
    """Return dense Farneback optical-flow summaries per sampled frame."""
    cv2 = _import_cv2()
    frames = _frames_to_cv2_gray_arrays(width=width, height=height, raw_frames=raw_frames)
    if not frames:
        return _empty_flow_trace()

    flow_mean_scores = [0.0]
    flow_p90_scores = [0.0]
    flow_coherence_scores = [0.0]

    for previous, current in zip(frames, frames[1:], strict=False):
        flow = cv2.calcOpticalFlowFarneback(
            previous,
            current,
            None,
            pyr_scale=0.5,
            levels=3,
            winsize=15,
            iterations=3,
            poly_n=5,
            poly_sigma=1.2,
            flags=0,
        )
        vectors = flow.reshape(-1, 2)
        metrics = _flow_vector_metrics(vectors=vectors, width=width, height=height)
        flow_mean_scores.append(metrics["mean"])
        flow_p90_scores.append(metrics["p90"])
        flow_coherence_scores.append(metrics["coherence"])

    return _build_flow_trace(
        flow_mean_scores=flow_mean_scores,
        flow_p90_scores=flow_p90_scores,
        flow_coherence_scores=flow_coherence_scores,
    )


def _empty_flow_trace() -> OpticalFlowTrace:
    """Return an empty per-frame optical-flow trace."""
    return _build_flow_trace(
        flow_mean_scores=[],
        flow_p90_scores=[],
        flow_coherence_scores=[],
    )


def _build_flow_trace(
    *,
    flow_mean_scores: list[float],
    flow_p90_scores: list[float],
    flow_coherence_scores: list[float],
) -> OpticalFlowTrace:
    """Return one consistently shaped optical-flow trace payload."""
    return OpticalFlowTrace(
        flow_mean_scores=flow_mean_scores,
        flow_p90_scores=flow_p90_scores,
        flow_coherence_scores=flow_coherence_scores,
    )


def _frames_to_cv2_gray_arrays(
    *,
    width: int,
    height: int,
    raw_frames: list[bytes],
):
    """Convert raw grayscale frame bytes into OpenCV-friendly 2D arrays."""
    import numpy as np

    frames = []
    for pixels in raw_frames:
        frames.append(np.frombuffer(pixels, dtype=np.uint8).reshape((height, width)))
    return frames


def _flow_vector_metrics(
    *,
    vectors,
    width: int,
    height: int,
) -> dict[str, float]:
    """Return normalized optical-flow magnitude and coherence metrics."""
    import numpy as np

    if len(vectors) == 0:
        return {"mean": 0.0, "p90": 0.0, "coherence": 0.0}

    magnitudes = np.linalg.norm(vectors, axis=1)
    diagonal = sqrt((width * width) + (height * height))
    normalization = max(diagonal * 0.04, 1.0)
    mean_magnitude = _clamp(float(np.mean(magnitudes)) / normalization)
    p90_magnitude = _clamp(float(np.percentile(magnitudes, 90)) / normalization)

    active_vectors = vectors[magnitudes > 1e-6]
    if len(active_vectors) == 0:
        coherence = 0.0
    else:
        unit_vectors = active_vectors / np.linalg.norm(active_vectors, axis=1, keepdims=True)
        coherence = _clamp(float(np.linalg.norm(np.mean(unit_vectors, axis=0))))

    return {
        "mean": round(mean_magnitude, 6),
        "p90": round(p90_magnitude, 6),
        "coherence": round(coherence, 6),
    }


def _optical_flow_motion_blur_score(
    *,
    absolute_blur: float,
    dynamic_blur: float,
    optical_flow_mean: float,
    optical_flow_p90: float,
    optical_flow_coherence: float,
) -> float:
    """Return a motion-blur score that requires both softness and flow support."""
    base_blur = agreement_soft_blend(absolute_blur, dynamic_blur)
    flow_strength = _clamp((optical_flow_mean * 0.65) + (optical_flow_p90 * 0.35))
    motion_support = _clamp(flow_strength * (0.5 + (0.5 * optical_flow_coherence)))
    return round(_clamp(base_blur * (0.5 + (0.5 * motion_support))), 6)


def _measure_blur_window(
    *,
    width: int,
    height: int,
    raw_frames: list[bytes],
) -> BlurWindowMeasurements:
    """Collect reusable blur, motion, and structure measurements for one window."""
    frame_scores = [
        _frame_sharpness_score(width, height, pixels)
        for pixels in raw_frames
    ]
    motion_scores = _frame_transition_motion_scores(raw_frames)
    sharpness_p10 = _percentile(frame_scores, 10) if frame_scores else 0.0
    sharpness_p90 = _percentile(frame_scores, 90) if frame_scores else 0.0
    absolute_blur_scores = [_absolute_blur(score) for score in frame_scores]
    dynamic_blur_scores = [
        _dynamic_blur(score, sharpness_p10, sharpness_p90)
        for score in frame_scores
    ]
    edge_density_scores = [
        _frame_edge_density(width, height, pixels)
        for pixels in raw_frames
    ]
    mean_edge_strength_scores = [
        _frame_mean_edge_strength(width, height, pixels)
        for pixels in raw_frames
    ]
    texture_energy_scores = [
        _frame_texture_energy(width, height, pixels)
        for pixels in raw_frames
    ]
    multiscale_metrics = [
        _frame_multiscale_structure_metrics(width, height, pixels)
        for pixels in raw_frames
    ]
    return BlurWindowMeasurements(
        frame_scores=frame_scores,
        motion_scores=motion_scores,
        sharpness_p10=sharpness_p10,
        sharpness_p90=sharpness_p90,
        absolute_blur_scores=absolute_blur_scores,
        dynamic_blur_scores=dynamic_blur_scores,
        edge_density_scores=edge_density_scores,
        mean_edge_strength_scores=mean_edge_strength_scores,
        texture_energy_scores=texture_energy_scores,
        medium_scale_edge_density_scores=_collect_metric(multiscale_metrics, "medium_scale_edge_density"),
        coarse_scale_edge_density_scores=_collect_metric(multiscale_metrics, "coarse_scale_edge_density"),
        medium_scale_texture_energy_scores=_collect_metric(multiscale_metrics, "medium_scale_texture_energy"),
        coarse_scale_texture_energy_scores=_collect_metric(multiscale_metrics, "coarse_scale_texture_energy"),
        edge_persistence_scores=_collect_metric(multiscale_metrics, "edge_persistence"),
        texture_retention_scores=_collect_metric(multiscale_metrics, "texture_retention"),
    )


def _collect_metric(
    metric_rows: list[dict[str, float]],
    key: str,
) -> list[float]:
    """Collect one metric column from a list of per-frame metric rows."""
    return [metrics[key] for metrics in metric_rows]


def _median_score(values: list[float]) -> float:
    """Return the default median-style summary used by lab feature properties."""
    return _percentile(values, _SUMMARY_PERCENTILE) if values else 0.0


def _optical_flow_export_metrics(
    *,
    method: str,
    flow_trace: OpticalFlowTrace,
) -> dict[str, object]:
    """Return flat detector-row metrics derived from one optical-flow trace."""
    return {
        "motion_blur_method": method,
        "optical_flow_mean": round(_mean(flow_trace.flow_mean_scores), 3),
        "optical_flow_p90": round(_percentile_or_zero(flow_trace.flow_p90_scores, 90), 3),
        "optical_flow_coherence": round(_median_score(flow_trace.flow_coherence_scores), 3),
    }


def _percentile_or_zero(values: list[float], percentile: int) -> float:
    """Return one percentile or ``0.0`` when the series is empty."""
    return _percentile(values, percentile) if values else 0.0


def weighted_soft_blend(absolute_blur: float, dynamic_blur: float) -> float:
    """Favor absolute softness, but let clip-relative evidence pull it down."""
    return round(_clamp((absolute_blur * 0.65) + (dynamic_blur * 0.35)), 6)


def rms_soft_blend(absolute_blur: float, dynamic_blur: float) -> float:
    """Use a smooth high-signal blend that is softer than a hard max."""
    rms_score = sqrt(((absolute_blur**2) + (dynamic_blur**2)) / 2.0)
    return round(_clamp(rms_score), 6)


def agreement_soft_blend(absolute_blur: float, dynamic_blur: float) -> float:
    """Penalize disagreement so globally soft but internally stable clips alert less."""
    base_score = (absolute_blur * 0.6) + (dynamic_blur * 0.4)
    disagreement_penalty = abs(absolute_blur - dynamic_blur) * 0.35
    return round(_clamp(base_score - disagreement_penalty), 6)


def geometric_core_blend(absolute_blur: float, dynamic_blur: float) -> float:
    """Favor mutual blur agreement with a low-tuning geometric core."""
    return round(_clamp(sqrt(max(absolute_blur, 0.0) * max(dynamic_blur, 0.0))), 6)


def consensus_core_blend(absolute_blur: float, dynamic_blur: float) -> float:
    """Use a balanced blur core with a modest disagreement penalty."""
    base_score = (absolute_blur + dynamic_blur) / 2.0
    disagreement_penalty = abs(absolute_blur - dynamic_blur) * 0.2
    return round(_clamp(base_score - disagreement_penalty), 6)


def structure_relief_blend(
    *,
    absolute_blur: float,
    dynamic_blur: float,
    edge_density: float,
    mean_edge_strength: float,
    texture_energy: float,
    base_blend: BlurBlend,
    relief_scale: float = 0.35,
) -> float:
    """Down-weight a blur core when broad image structure still looks healthy."""
    base_blur = base_blend(absolute_blur, dynamic_blur)
    relief = _structure_strength(
        edge_density=edge_density,
        mean_edge_strength=mean_edge_strength,
        texture_energy=texture_energy,
    )
    return round(_clamp(base_blur - (relief_scale * relief)), 6)


def compression_robust_blend(
    *,
    absolute_blur: float,
    dynamic_blur: float,
    edge_density: float,
    mean_edge_strength: float,
    texture_energy: float,
) -> float:
    """Return the original compression-focused structure-relief experiment blend."""
    return structure_relief_blend(
        absolute_blur=absolute_blur,
        dynamic_blur=dynamic_blur,
        edge_density=edge_density,
        mean_edge_strength=mean_edge_strength,
        texture_energy=texture_energy,
        base_blend=agreement_soft_blend,
    )


def multiscale_structure_blend(
    *,
    absolute_blur: float,
    dynamic_blur: float,
    edge_persistence: float,
    texture_retention: float,
    coarse_scale_edge_density: float,
    coarse_scale_texture_energy: float,
) -> float:
    """Down-weight blur when structure survives across multiple scales."""
    base_blur = agreement_soft_blend(absolute_blur, dynamic_blur)
    relief = _multiscale_structure_strength(
        edge_persistence=edge_persistence,
        texture_retention=texture_retention,
        coarse_scale_edge_density=coarse_scale_edge_density,
        coarse_scale_texture_energy=coarse_scale_texture_energy,
    )
    return round(_clamp(base_blur - (0.45 * relief)), 6)


def _absolute_blur(score: float) -> float:
    """Convert one sharpness score into detector-side absolute blur."""
    return round(1.0 - _clamp(score), 6)


def _dynamic_blur(score: float, p10: float, p90: float) -> float:
    """Convert one sharpness score into clip-relative blur."""
    dynamic_sharpness = _robust_normalize(score, p10, p90)
    return round(1.0 - dynamic_sharpness, 6)


def _robust_normalize(value: float, p10: float, p90: float) -> float:
    """Normalize one sharpness value into ``0..1`` using robust percentiles."""
    span = p90 - p10
    if span <= 1e-6:
        return _clamp(value)
    return _clamp((value - p10) / span)


def _frame_edge_density(width: int, height: int, pixels: bytes) -> float:
    """Return the share of local edges above the activity threshold."""
    diffs = _frame_edge_differences(width, height, pixels)
    if not diffs:
        return 0.0
    active_edges = sum(1 for diff in diffs if diff >= EDGE_ACTIVE_THRESHOLD)
    return round(active_edges / len(diffs), 6)


def _frame_mean_edge_strength(width: int, height: int, pixels: bytes) -> float:
    """Return the normalized mean local edge strength for one frame."""
    diffs = _frame_edge_differences(width, height, pixels)
    if not diffs:
        return 0.0
    return round((sum(diffs) / len(diffs)) / 255.0, 6)


def _frame_texture_energy(width: int, height: int, pixels: bytes) -> float:
    """Return a normalized local texture-energy estimate for one frame."""
    diffs = _frame_edge_differences(width, height, pixels)
    if not diffs:
        return 0.0
    squared_energy = sum((diff / 255.0) ** 2 for diff in diffs) / len(diffs)
    return round(squared_energy, 6)


def _frame_edge_differences(width: int, height: int, pixels: bytes) -> list[int]:
    """Return local horizontal and vertical edge differences for one frame."""
    if width < 2 or height < 2 or not pixels:
        return []

    diffs: list[int] = []
    row_stride = width
    for row in range(height - 1):
        base_index = row * row_stride
        next_row = (row + 1) * row_stride
        for col in range(width - 1):
            index = base_index + col
            diffs.append(abs(pixels[index] - pixels[index + 1]))
            diffs.append(abs(pixels[index] - pixels[next_row + col]))
    return diffs


def _frame_multiscale_structure_metrics(
    width: int,
    height: int,
    pixels: bytes,
) -> dict[str, float]:
    """Return cross-scale structure metrics for one sampled grayscale frame."""
    fine_edge_density = _frame_edge_density(width, height, pixels)
    fine_texture_energy = _frame_texture_energy(width, height, pixels)

    medium_width, medium_height, medium_pixels = _downsample_gray_frame(
        width=width,
        height=height,
        pixels=pixels,
    )
    coarse_width, coarse_height, coarse_pixels = _downsample_gray_frame(
        width=medium_width,
        height=medium_height,
        pixels=medium_pixels,
    )

    medium_edge_density = _frame_edge_density(
        medium_width,
        medium_height,
        medium_pixels,
    )
    coarse_edge_density = _frame_edge_density(
        coarse_width,
        coarse_height,
        coarse_pixels,
    )
    medium_texture_energy = _frame_texture_energy(
        medium_width,
        medium_height,
        medium_pixels,
    )
    coarse_texture_energy = _frame_texture_energy(
        coarse_width,
        coarse_height,
        coarse_pixels,
    )

    edge_persistence = _safe_ratio(
        (medium_edge_density * 0.4) + (coarse_edge_density * 0.6),
        fine_edge_density,
    )
    texture_retention = _safe_ratio(
        (medium_texture_energy * 0.4) + (coarse_texture_energy * 0.6),
        fine_texture_energy,
    )
    return {
        "medium_scale_edge_density": round(medium_edge_density, 6),
        "coarse_scale_edge_density": round(coarse_edge_density, 6),
        "medium_scale_texture_energy": round(medium_texture_energy, 6),
        "coarse_scale_texture_energy": round(coarse_texture_energy, 6),
        "edge_persistence": round(edge_persistence, 6),
        "texture_retention": round(texture_retention, 6),
    }


def _downsample_gray_frame(
    *,
    width: int,
    height: int,
    pixels: bytes,
) -> tuple[int, int, bytes]:
    """Downsample one grayscale frame by 2x2 averaging."""
    if (
        width < (MIN_DOWNSAMPLED_DIMENSION * 2)
        or height < (MIN_DOWNSAMPLED_DIMENSION * 2)
        or not pixels
    ):
        return (width, height, pixels)

    downsampled_width = width // 2
    downsampled_height = height // 2
    downsampled_pixels = bytearray(downsampled_width * downsampled_height)
    for row in range(downsampled_height):
        source_row = row * 2
        next_source_row = min(source_row + 1, height - 1)
        for col in range(downsampled_width):
            source_col = col * 2
            next_source_col = min(source_col + 1, width - 1)
            top_left = pixels[(source_row * width) + source_col]
            top_right = pixels[(source_row * width) + next_source_col]
            bottom_left = pixels[(next_source_row * width) + source_col]
            bottom_right = pixels[(next_source_row * width) + next_source_col]
            downsampled_pixels[(row * downsampled_width) + col] = (
                top_left + top_right + bottom_left + bottom_right
            ) // 4
    return (downsampled_width, downsampled_height, bytes(downsampled_pixels))


def _safe_ratio(numerator: float, denominator: float) -> float:
    """Return a bounded ratio that stays safe on near-zero denominators."""
    if denominator <= 1e-6:
        return 0.0
    return _clamp(numerator / denominator)


def _structure_strength(
    *,
    edge_density: float,
    mean_edge_strength: float,
    texture_energy: float,
) -> float:
    """Combine same-scale structure metrics into one normalized relief signal."""
    texture_strength = sqrt(max(texture_energy, 0.0))
    return _clamp(
        (edge_density * 0.4)
        + (mean_edge_strength * 0.4)
        + (texture_strength * 0.2)
    )


def _multiscale_structure_strength(
    *,
    edge_persistence: float,
    texture_retention: float,
    coarse_scale_edge_density: float,
    coarse_scale_texture_energy: float,
) -> float:
    """Combine cross-scale structure metrics into one normalized relief signal."""
    coarse_texture_strength = sqrt(max(coarse_scale_texture_energy, 0.0))
    return _clamp(
        (edge_persistence * 0.35)
        + (texture_retention * 0.35)
        + (coarse_scale_edge_density * 0.2)
        + (coarse_texture_strength * 0.1)
    )


def analyze_video_blur_motion_coherent_v1(
    analysis_slice: AnalysisSlice,
) -> DetectorMetricRow:
    """Use multiscale motion coherence to separate real motion from blur-like softness."""
    context = _prepare_blur_analysis_context(analysis_slice)
    per_frame_blur_scores = [
        geometric_core_blend(absolute_blur, dynamic_blur)
        for absolute_blur, dynamic_blur in zip(
            context.measurements.absolute_blur_scores,
            context.measurements.dynamic_blur_scores,
            strict=False,
        )
    ]
    motion_coherence_metrics = _compute_motion_coherence_multiscale(
        raw_frames=context.raw_frames,
        width=context.sample_width,
        height=context.sample_height,
    )
    motion_incoherence_scores = motion_coherence_metrics.incoherence_scores
    if not motion_incoherence_scores:
        return _finalize_blur_result_row(
            context=context,
            per_frame_blur_scores=per_frame_blur_scores,
            blur_blend_id="motion_coherent",
            extra_metrics={},
        )
    per_frame_final_blur = [
        blur_score * _clamp(1.0 - (0.4 * incoherence))
        for blur_score, incoherence in zip(
            per_frame_blur_scores,
            motion_incoherence_scores,
            strict=False,
        )
    ]
    extra_metrics = {
        "fine_scale_motion_energy": round(motion_coherence_metrics.fine_scale_motion_energy, 3),
        "medium_scale_motion_energy": round(motion_coherence_metrics.medium_scale_motion_energy, 3),
        "coarse_scale_motion_energy": round(motion_coherence_metrics.coarse_scale_motion_energy, 3),
        "motion_persistence": round(motion_coherence_metrics.motion_persistence, 3),
        "motion_coherence": round(motion_coherence_metrics.motion_coherence, 3),
        "motion_incoherence_penalty": round(motion_coherence_metrics.incoherence_avg, 3),
    }

    return _finalize_blur_result_row(
        context=context,
        per_frame_blur_scores=per_frame_final_blur,
        blur_blend_id="motion_coherent",
        extra_metrics=extra_metrics,
    )


def _compute_motion_coherence_multiscale(
    *,
    raw_frames: list[bytes],
    width: int,
    height: int,
) -> MotionCoherenceMetrics:
    """Compatibility alias for callers still patching the older private helper."""
    return compute_motion_coherence_multiscale(
        raw_frames=raw_frames,
        width=width,
        height=height,
    )


def _compute_frame_motion_energies(
    *,
    raw_frames: list[bytes],
    width: int,
    height: int,
) -> list[float]:
    """Return normalized frame-to-frame motion energy for each transition."""
    if len(raw_frames) < 2 or not raw_frames[0]:
        return []

    motion_energies: list[float] = [0.0]

    for prev_frame, curr_frame in zip(raw_frames, raw_frames[1:], strict=False):
        if len(prev_frame) < (width * height) or len(curr_frame) < (width * height):
            motion_energies.append(0.0)
            continue

        sad = 0.0
        for i in range(min(len(prev_frame), len(curr_frame))):
            sad += abs(int(prev_frame[i]) - int(curr_frame[i]))

        total_pixels = width * height
        max_possible_sad = total_pixels * 255.0
        motion_energy = _clamp(sad / max(max_possible_sad, 1.0))
        motion_energies.append(motion_energy)

    return motion_energies


def _downsample_frame_sequence(
    *,
    raw_frames: list[bytes],
    width: int,
    height: int,
    downsample_factor: int,
) -> tuple[int, int, list[bytes]]:
    """Downsample all frames by repeated 2x2 averaging."""
    current_width, current_height = width, height
    current_frames = raw_frames

    for _ in range(downsample_factor):
        if current_width < (MIN_DOWNSAMPLED_DIMENSION * 2):
            break
        downsampled = []
        for pixels in current_frames:
            _, _, downsampled_pixels = _downsample_gray_frame(
                width=current_width,
                height=current_height,
                pixels=pixels,
            )
            downsampled.append(downsampled_pixels)
        current_frames = downsampled
        current_width //= 2
        current_height //= 2

    return current_width, current_height, current_frames


BLUR_BLEND_SPECS: tuple[BlurBlendSpec, ...] = (
    BlurBlendSpec(
        blend_id="production_max",
        description="Current production hard max of absolute and dynamic blur.",
        combine=max,
    ),
    BlurBlendSpec(
        blend_id="weighted_soft",
        description="Weighted blend that still trusts absolute softness most.",
        combine=weighted_soft_blend,
    ),
    BlurBlendSpec(
        blend_id="rms_soft",
        description="Smooth high-signal blend that stays closer to the larger input.",
        combine=rms_soft_blend,
    ),
    BlurBlendSpec(
        blend_id="agreement_soft",
        description="Weighted blend with disagreement penalty for soft moving footage.",
        combine=agreement_soft_blend,
    ),
)
BLUR_BLEND_SPECS_BY_ID: dict[str, BlurBlendSpec] = {
    spec.blend_id: spec for spec in BLUR_BLEND_SPECS
}


@dataclass(frozen=True)
class OpticalFlowTrace:
    """Per-frame optical-flow summaries for one sampled window."""

    flow_mean_scores: list[float]
    flow_p90_scores: list[float]
    flow_coherence_scores: list[float]


@dataclass(frozen=True)
class MotionCoherenceMetrics:
    """Cross-scale motion summaries used by the motion-coherent blur experiment."""

    fine_scale_motion_energy: float
    medium_scale_motion_energy: float
    coarse_scale_motion_energy: float
    motion_persistence: float
    motion_coherence: float
    incoherence_avg: float
    incoherence_scores: list[float]
