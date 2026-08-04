"""Detector-lab metric and experiment-algorithm contract tests.

These tests protect low-level blur, optical-flow, and motion-coherence facts.
Practical alert guardrails and thresholds intentionally remain in policy tests.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from detector_lab.blur_experiments import (
    MotionCoherenceMetrics,
    OpticalFlowTrace,
    _compute_dense_farneback_flow_trace,
    _compute_sparse_lk_flow_trace,
    _empty_flow_trace,
    _optical_flow_export_metrics,
    _optical_flow_motion_blur_score,
    agreement_soft_blend,
    analyze_video_blur_dense_farneback_motion,
    analyze_video_blur_motion_coherent_v1,
    analyze_video_blur_sparse_lk_motion,
    compression_robust_blend,
    consensus_core_blend,
    geometric_core_blend,
    rms_soft_blend,
    structure_relief_blend,
    weighted_soft_blend,
)
from tests.detector_lab_test_support import fake_blur_context


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


def test_sparse_lk_motion_blur_variant_emits_optical_flow_metrics(
    monkeypatch, tmp_path: Path
) -> None:
    """The sparse LK lab variant should export its optical-flow summaries."""
    context = fake_blur_context(tmp_path)
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
    context = fake_blur_context(tmp_path)
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
    context = fake_blur_context(tmp_path)
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
    context = fake_blur_context(tmp_path)
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
    baseline_window_score = round(
        sorted(per_frame_scores)[len(per_frame_scores) // 2], 3
    )

    assert row["blur_score"] == baseline_window_score
    assert "motion_incoherence_penalty" not in row
    assert "motion_coherence" not in row


def test_motion_coherent_variant_exports_zero_motion_baseline(
    monkeypatch, tmp_path: Path
) -> None:
    """Motion-coherent blur should export zero motion metrics and preserve baseline blur when motion is absent."""
    context = fake_blur_context(tmp_path)
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
    baseline_window_score = round(
        sorted(per_frame_scores)[len(per_frame_scores) // 2], 3
    )

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
    context = fake_blur_context(tmp_path)
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
