"""Calibration settings for detector-lab practical alert experiments.

These settings are intentionally lab-only. They group thresholds by policy
family so ``practical_alerts.py`` can stay focused on readable scoring and
guardrails instead of a long flat list of constants.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class PracticalBlackAlertSettings:
    """Calibration settings for the simple practical black-frame alert."""

    alert_ratio: float = 0.60
    score_threshold: float = 0.55


@dataclass(frozen=True)
class DarkFrameGuardrailSettings:
    """Calibration settings for dark-frame suppression in blur policies."""

    mean_luma_threshold: float = 60.0
    contrast_threshold: float = 30.0
    hard_window_ratio_threshold: float = 0.30


@dataclass(frozen=True)
class BlackTransitionGuardrailSettings:
    """Calibration settings for black-transition suppression and penalties."""

    black_dominant_ratio: float = 0.40
    black_dark_mix_black_ratio: float = 0.15
    black_dark_mix_dark_ratio: float = 0.20
    neighbor_black_hard_ratio: float = 0.70
    neighbor_black_mix_ratio: float = 0.40
    current_black_mix_ratio: float = 0.10
    neighbor_black_hard_max_blur_score: float = 0.965
    neighbor_black_mix_max_blur_score: float = 0.975
    neighbor_black_hard_penalty: float = 0.88
    neighbor_black_mix_penalty: float = 0.92
    structure_escape_edge_density: float = 0.075
    structure_escape_medium_texture: float = 0.004


@dataclass(frozen=True)
class BlurMotionPenaltySettings:
    """Calibration settings for the v1 blur motion ambiguity penalty."""

    moderate_motion_mean_threshold: float = 0.03
    moderate_motion_p90_threshold: float = 0.06
    high_motion_mean_threshold: float = 0.08
    high_motion_p90_threshold: float = 0.12
    moderate_penalty: float = 0.10
    high_penalty: float = 0.25


@dataclass(frozen=True)
class MotionPreferenceSettings:
    """Calibration settings for preferring motion-blur classification over blur."""

    motion_mean_threshold: float = 0.10
    motion_p90_threshold: float = 0.18
    persistence_threshold: float = 0.97
    coherence_threshold: float = 0.97


@dataclass(frozen=True)
class PracticalBlurAlertSettings:
    """Calibration settings shared by practical blur alert variants."""

    threshold: float
    transition: BlackTransitionGuardrailSettings = field(
        default_factory=BlackTransitionGuardrailSettings
    )


@dataclass(frozen=True)
class PracticalMotionBlurAlertSettings:
    """Calibration settings for the practical motion-blur alert."""

    threshold: float = 0.68
    min_softness: float = 0.55
    min_coherence: float = 0.30
    transition: BlackTransitionGuardrailSettings = field(
        default_factory=BlackTransitionGuardrailSettings
    )
