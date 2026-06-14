"""Canonical production detector package.

The package keeps detector ownership explicit:

- ``black_screen.py`` owns black-screen extraction
- ``blur.py`` owns blur and motion extraction
- ``registry.py`` owns runtime registration metadata

It re-exports the current runtime entrypoints and a small set of focused test
helpers. A few legacy helper names also stay here for ``detector_lab``
compatibility while the production refactor settles.
"""

from . import black_screen, blur
from ._shared import display_source_labels as _display_source_labels
from .black_screen import analyze_video_metrics
from .blur import (
    _bounded_sample_size,
    _clamp,
    _extract_sampled_gray_frames,
    _frame_transition_motion_scores,
    _frame_sharpness_score,
    _is_short_tail_window_without_samples,
    _is_effectively_black_frame,
    _longest_threshold_run,
    _measure_blur_window,
    _mean,
    _percentile,
    _resolve_blur_sample_fps,
    _resolve_blur_sample_size,
    _rolling_window_medians,
    _select_blur_analysis_frames,
    _summarize_blur_scores,
    analyze_video_blur,
)
from .contracts import BlurScoreSummary, BlurWindowMetrics

__all__ = [
    "BlurScoreSummary",
    "BlurWindowMetrics",
    "_bounded_sample_size",
    "_clamp",
    "_display_source_labels",
    "_extract_sampled_gray_frames",
    "_frame_transition_motion_scores",
    "_frame_sharpness_score",
    "_is_short_tail_window_without_samples",
    "_is_effectively_black_frame",
    "_longest_threshold_run",
    "_measure_blur_window",
    "_mean",
    "_percentile",
    "_resolve_blur_sample_fps",
    "_resolve_blur_sample_size",
    "_rolling_window_medians",
    "_select_blur_analysis_frames",
    "_summarize_blur_scores",
    "analyze_video_blur",
    "analyze_video_metrics",
    "black_screen",
    "blur",
]
