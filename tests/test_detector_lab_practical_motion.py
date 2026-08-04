"""Synthetic tests for practical motion-blur alert policy.

This module owns motion-specific guardrails, softness, coherence, persistence,
scoring, and threshold boundaries. Blur policy and low-level metric facts stay
in their dedicated detector-lab test modules.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from detector_lab.blur_experiments import (
    BlurAnalysisContext,
    BlurWindowMeasurements,
    MotionCoherenceMetrics,
)
from detector_lab.practical_alerts import (
    _prefers_motion_blur_classification,
    analyze_practical_motion_blur_alert,
)
from tests.detector_lab_test_support import (
    black_metrics_row,
)
from tests.detector_lab_test_support import (
    fake_blur_context as _fake_blur_context,
)
from tests.detector_lab_test_support import (
    fake_slice as _fake_slice,
)
from tests.detector_lab_test_support import (
    fresh_practical_evaluation_context as _fresh_practical_evaluation_context,
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
        incoherence_scores=[0.05, 0.05]
        if incoherence_scores is None
        else incoherence_scores,
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
        lambda **kwargs: black_metrics_row(
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
    assert (
        unsuppressed_row["practical_score"] >= unsuppressed_row["practical_threshold"]
    )
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
    ids=(
        "exact-mixed-boundary-suppressed",
        "both-values-below-boundary-accepted",
        "neighbor-below-boundary-accepted",
    ),
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
    ids=("exact-threshold-detected", "just-below-threshold-rejected"),
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

    assert (
        higher_softness_row["practical_score"] > lower_softness_row["practical_score"]
    )


@pytest.mark.parametrize(
    ("texture_energy", "expected_detected", "expected_guardrail_reason"),
    [
        (0.475, True, ""),
        (0.48, False, "softness_too_low"),
    ],
    ids=("exact-softness-boundary-accepted", "below-softness-boundary-rejected"),
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

    assert (
        _prefers_motion_blur_classification(
            measurements=boundary_measurements,
            raw_frames=context.raw_frames,
            sample_width=context.sample_width,
            sample_height=context.sample_height,
        )
        is True
    )
