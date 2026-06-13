"""Detector-local helper contracts for the blur detector package."""

from dataclasses import dataclass

import config


def _mean(values: list[float]) -> float:
    """Return the arithmetic mean for one numeric series."""
    if not values:
        return 0.0
    return sum(values) / len(values)


def _percentile(values: list[float] | list[int], percentile: float) -> float:
    """Compute a linear percentile without adding a numpy dependency."""
    if not values:
        return 0.0
    sorted_values = sorted(float(value) for value in values)
    if len(sorted_values) == 1:
        return sorted_values[0]

    rank = (len(sorted_values) - 1) * percentile / 100.0
    lower = int(rank)
    upper = min(lower + 1, len(sorted_values) - 1)
    weight = rank - lower
    return (
        sorted_values[lower] * (1.0 - weight) + sorted_values[upper] * weight
    )


@dataclass(frozen=True)
class BlurWindowMetrics:
    """Blur features derived once from one sampled grayscale window."""

    frame_scores: list[float]
    motion_scores: list[float]
    sharpness_p10: float
    sharpness_p90: float
    per_frame_blur_scores: list[float]

    @property
    def sample_count(self) -> int:
        """Return the number of usable frames in the analyzed window."""
        return len(self.frame_scores)

    @property
    def motion_mean(self) -> float:
        """Return the average frame-to-frame motion across the window."""
        return _mean(self.motion_scores)

    @property
    def motion_p90(self) -> float:
        """Return the upper-end motion level across the window."""
        return _percentile(self.motion_scores, 90) if self.motion_scores else 0.0


@dataclass(frozen=True)
class BlurScoreSummary:
    """Window-level blur summary ready for detector-row export."""

    window_size: int
    rolling_scores: list[float]
    blur_score: float
    consecutive_blurry_windows: int
    required_windows: int

    @property
    def detected(self) -> bool:
        """Return whether the summarized window crosses the blur entry threshold."""
        return (
            self.blur_score >= config.VIDEO_BLUR_ALERT_THRESHOLD
            and self.consecutive_blurry_windows >= self.required_windows
        )
