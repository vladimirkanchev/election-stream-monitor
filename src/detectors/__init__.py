"""Canonical production detector package.

The package keeps detector ownership explicit:

- ``black_screen.py`` owns black-screen extraction
- ``blur.py`` owns blur and motion extraction
- ``registry.py`` owns runtime registration metadata

It re-exports the current runtime entrypoints and a small set of focused test
helpers.
"""

from . import black_screen, blur
from .black_screen import analyze_video_metrics
from .blur import (
    _bounded_sample_size,
    _extract_sampled_gray_frames,
    _frame_transition_motion_scores,
    _is_short_tail_window_without_samples,
    _measure_blur_window,
    _resolve_blur_sample_fps,
    _resolve_blur_sample_size,
    _select_blur_analysis_frames,
    _summarize_blur_scores,
    analyze_video_blur,
)
from .contracts import BlurScoreSummary, BlurWindowMetrics

__all__ = [
    "BlurScoreSummary",
    "BlurWindowMetrics",
    "_bounded_sample_size",
    "_extract_sampled_gray_frames",
    "_frame_transition_motion_scores",
    "_is_short_tail_window_without_samples",
    "_measure_blur_window",
    "_resolve_blur_sample_fps",
    "_resolve_blur_sample_size",
    "_select_blur_analysis_frames",
    "_summarize_blur_scores",
    "analyze_video_blur",
    "analyze_video_metrics",
    "black_screen",
    "blur",
]
