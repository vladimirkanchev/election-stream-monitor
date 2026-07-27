"""Detector-lab practical black and blur-policy contract tests.

These tests own black, dark-frame, neighbor, structure, and calibrated-blur
decisions. Metric formulas and practical motion-blur policy remain separate.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from analyzer_contract import AnalysisSlice
from detector_lab.blur_experiments import (
    BlurAnalysisContext,
    BlurWindowMeasurements,
    MotionCoherenceMetrics,
)
from detector_lab.practical_alerts import (
    _BLACK_WINDOW_ROW_CACHE,
    _dark_frame_ratio,
    PracticalEvaluationContext,
    analyze_practical_black_alert,
    analyze_practical_blur_alert,
    analyze_practical_blur_alert_v2,
    analyze_practical_blur_alert_v3,
    build_experiment_window_facts,
)
from tests.detector_lab_test_support import (
    black_metrics_row,
    fake_blur_context,
    fake_slice,
    fresh_practical_evaluation_context,
)


def _patch_black_metrics(
    monkeypatch: pytest.MonkeyPatch,
    **overrides: object,
) -> None:
    """Patch the black-detector seam while keeping case-specific facts visible."""
    monkeypatch.setattr(
        "detector_lab.practical_alerts.analyze_video_metrics",
        lambda **kwargs: black_metrics_row(**kwargs, **overrides),
    )


def _patch_v3_neighbor_case(
    monkeypatch: pytest.MonkeyPatch,
    *,
    context: BlurAnalysisContext,
    neighbor_black_ratio: float,
    blur_core_score: float | None,
) -> None:
    """Set only the common v3 neighbor-black inputs for boundary cases."""
    _patch_black_metrics(monkeypatch)
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
        lambda analysis_slice: (0.0, neighbor_black_ratio),
    )
    if blur_core_score is not None:
        monkeypatch.setattr(
            "detector_lab.practical_alerts._weighted_geometric_blur_core",
            lambda **kwargs: blur_core_score,
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
    context = fake_blur_context(tmp_path)
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

    monkeypatch.setattr(
        "detector_lab.practical_alerts.analyze_video_metrics", fake_black
    )
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
    analysis_slice = fake_slice(tmp_path)
    blur_context = fake_blur_context(tmp_path)
    call_count = 0
    evaluation_context = PracticalEvaluationContext(
        black_window_rows={},
        blur_analysis_contexts={},
        experiment_window_facts={},
    )

    _patch_black_metrics(monkeypatch)

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


def test_practical_black_alert_uses_ratio_first_black_score(
    monkeypatch, tmp_path: Path
) -> None:
    """The practical black alert should trigger on a black-dominant window."""
    analysis_slice = fake_slice(tmp_path)
    _patch_black_metrics(
        monkeypatch,
        black_segment_count=1,
        total_black_sec=0.8,
        longest_black_sec=0.8,
        black_ratio=0.8,
    )

    row = analyze_practical_black_alert(analysis_slice)

    assert row["practical_detected"] is True
    assert row["practical_score"] >= 0.55
    assert row["black_detected"] is True


def test_practical_blur_alert_skips_black_dominant_windows(
    monkeypatch, tmp_path: Path
) -> None:
    """The practical blur alert should stay quiet when the black guardrail trips."""
    analysis_slice = fake_slice(tmp_path)
    _patch_black_metrics(
        monkeypatch,
        black_segment_count=1,
        total_black_sec=0.5,
        longest_black_sec=0.5,
        black_ratio=0.5,
    )
    monkeypatch.setattr(
        "detector_lab.practical_alerts.prepare_blur_analysis_context",
        lambda slice_: fake_blur_context(tmp_path),
    )

    row = analyze_practical_blur_alert(analysis_slice)

    assert row["practical_detected"] is False
    assert row["guardrail_reason"] == "black_dominant"
    assert row["blur_score"] == 0.0


def test_practical_blur_alert_v2_uses_v2_analyzer_name(
    monkeypatch, tmp_path: Path
) -> None:
    """The calibrated practical blur alert should export a distinct analyzer id."""
    analysis_slice = fake_slice(tmp_path)
    _patch_black_metrics(monkeypatch)
    monkeypatch.setattr(
        "detector_lab.practical_alerts.prepare_blur_analysis_context",
        lambda slice_: fake_blur_context(tmp_path),
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
    analysis_slice = fake_slice(tmp_path)
    _patch_black_metrics(monkeypatch)
    monkeypatch.setattr(
        "detector_lab.practical_alerts.prepare_blur_analysis_context",
        lambda slice_: fake_blur_context(tmp_path),
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
    analysis_slice = fake_slice(tmp_path)
    context = fake_blur_context(tmp_path)
    dark_frame = bytes([18] * 16)
    _patch_black_metrics(monkeypatch)
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
    analysis_slice = fake_slice(tmp_path)
    context = fake_blur_context(tmp_path)
    _patch_black_metrics(monkeypatch)
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
    analysis_slice = fake_slice(tmp_path)
    context = fake_blur_context(tmp_path)
    _patch_black_metrics(
        monkeypatch,
        black_segment_count=1,
        total_black_sec=0.2,
        longest_black_sec=0.2,
        black_ratio=0.2,
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
    analysis_slice = fake_slice(tmp_path)
    context = fake_blur_context(tmp_path)
    _patch_black_metrics(
        monkeypatch,
        black_segment_count=1,
        total_black_sec=0.15,
        longest_black_sec=0.15,
        black_ratio=0.15,
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


@pytest.mark.parametrize(
    (
        "neighbor_black_ratio",
        "blur_core_score",
        "expected_guardrail_reason",
        "expected_detected",
        "score_field",
        "expected_score",
    ),
    [
        pytest.param(
            0.8,
            None,
            "black_neighbor_transition",
            False,
            "blur_score",
            None,
            id="strong-neighbor-transition-suppressed",
        ),
        pytest.param(
            0.70,
            None,
            "black_neighbor_transition",
            False,
            "practical_score",
            None,
            id="exact-hard-boundary-penalized",
        ),
        pytest.param(
            0.699,
            0.96,
            "",
            True,
            "practical_score",
            0.96,
            id="just-below-hard-boundary-accepted",
        ),
        pytest.param(
            0.70,
            0.96,
            "black_neighbor_transition",
            False,
            "practical_score",
            0.845,
            id="exact-boundary-demotes-alerting-score",
        ),
        pytest.param(
            0.70,
            0.97,
            "",
            True,
            "practical_score",
            0.97,
            id="strong-score-escapes-neighbor-penalty",
        ),
    ],
)
def test_practical_blur_alert_v3_neighbor_threshold_behavior(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    neighbor_black_ratio: float,
    blur_core_score: float | None,
    expected_guardrail_reason: str,
    expected_detected: bool,
    score_field: str,
    expected_score: float | None,
) -> None:
    """Neighbor-black boundaries should retain their distinct suppression outcomes."""
    analysis_slice = fake_slice(tmp_path)
    context = fake_blur_context(tmp_path)
    _patch_v3_neighbor_case(
        monkeypatch,
        context=context,
        neighbor_black_ratio=neighbor_black_ratio,
        blur_core_score=blur_core_score,
    )

    row = analyze_practical_blur_alert_v3(analysis_slice)

    assert row["guardrail_reason"] == expected_guardrail_reason
    assert row["practical_detected"] is expected_detected
    if expected_score is None:
        assert 0.0 < row[score_field] < row["practical_threshold"]
    else:
        assert row[score_field] == expected_score


def test_practical_blur_alert_v3_applies_mixed_neighbor_penalty(
    monkeypatch, tmp_path: Path
) -> None:
    """The v3 blur alert should soften scores for mixed current-plus-neighbor black context."""
    analysis_slice = fake_slice(tmp_path)
    context = fake_blur_context(tmp_path)
    _patch_black_metrics(monkeypatch, black_ratio=0.1)
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
    analysis_slice = fake_slice(tmp_path)
    context = fake_blur_context(tmp_path)
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
    _patch_black_metrics(monkeypatch)
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
    analysis_slice = fake_slice(tmp_path)
    context = fake_blur_context(tmp_path)
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
    _patch_black_metrics(monkeypatch)
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
    analysis_slice = fake_slice(tmp_path)
    context = fake_blur_context(tmp_path)

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
            medium_scale_texture_energy_scores=[
                texture_value,
                texture_value,
                texture_value,
            ],
            coarse_scale_texture_energy_scores=context.measurements.coarse_scale_texture_energy_scores,
            edge_persistence_scores=context.measurements.edge_persistence_scores,
            texture_retention_scores=context.measurements.texture_retention_scores,
        )

    _patch_black_metrics(monkeypatch)
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
        evaluation_context=fresh_practical_evaluation_context(),
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
        evaluation_context=fresh_practical_evaluation_context(),
    )

    assert lower_texture_row["practical_score"] > higher_texture_row["practical_score"]


def test_practical_blur_alert_v2_score_increases_when_edge_density_drops(
    monkeypatch, tmp_path: Path
) -> None:
    """The calibrated blur score should rise as edge density collapses."""
    analysis_slice = fake_slice(tmp_path)
    context = fake_blur_context(tmp_path)

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

    _patch_black_metrics(monkeypatch)
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
        evaluation_context=fresh_practical_evaluation_context(),
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
        evaluation_context=fresh_practical_evaluation_context(),
    )

    assert sparse_edges_row["practical_score"] > denser_edges_row["practical_score"]


def test_practical_blur_alert_v2_detects_exact_threshold_score(
    monkeypatch, tmp_path: Path
) -> None:
    """The calibrated blur alert should treat its exact threshold as a positive detection."""
    analysis_slice = fake_slice(tmp_path)
    context = fake_blur_context(tmp_path)
    _patch_black_metrics(monkeypatch)
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
