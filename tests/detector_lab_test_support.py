"""Small synthetic data constructors shared by detector-lab test modules.

Keep policy thresholds, assertions, and monkeypatch behavior with the test
module that owns the corresponding detector decision.
"""

from pathlib import Path

from analyzer_contract import AnalysisSlice
from detector_lab.blur_experiments import BlurAnalysisContext, BlurWindowMeasurements
from detector_lab.practical_alerts import PracticalEvaluationContext


def black_metrics_row(
    *,
    source_group: str,
    source_name: str,
    black_segment_count: int = 0,
    total_black_sec: float = 0.0,
    longest_black_sec: float = 0.0,
    black_ratio: float = 0.0,
    processing_sec: float = 0.02,
    **_: object,
) -> dict[str, object]:
    """Build the stable black-detector row consumed by practical policies."""
    return {
        "source_group": source_group,
        "source_name": source_name,
        "processing_sec": processing_sec,
        "black_segment_count": black_segment_count,
        "total_black_sec": total_black_sec,
        "longest_black_sec": longest_black_sec,
        "black_ratio": black_ratio,
    }


def fake_slice(tmp_path: Path) -> AnalysisSlice:
    """Build one minimal slice that behaves like a one-second lab window."""
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


def fake_blur_context(tmp_path: Path) -> BlurAnalysisContext:
    """Build controlled blur facts shared by metric and practical-policy tests."""
    analysis_slice = fake_slice(tmp_path)
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


def fresh_practical_evaluation_context() -> PracticalEvaluationContext:
    """Return an isolated context for practical-policy score comparisons."""
    return PracticalEvaluationContext(
        black_window_rows={},
        blur_analysis_contexts={},
        experiment_window_facts={},
    )


__all__ = [
    "black_metrics_row",
    "fake_blur_context",
    "fake_slice",
    "fresh_practical_evaluation_context",
]
