"""Practical detector-lab alert experiments built from current detector signals.

This module is intentionally experimental and intentionally readable. It lives
between two boundaries:

- production detectors and blur-experiment measurements provide facts
- practical policies score those facts into lab-only alert rows

The goal at the current project stage is to compare a few operationally
plausible policies without pretending they are production runtime rules yet.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from functools import partial
from math import sqrt
from time import gmtime, strftime
from typing import Callable

from analyzer_contract import AnalysisSlice
from detector_lab.blur_experiments import (
    BlurAnalysisContext,
    compute_motion_coherence_multiscale,
    prepare_blur_analysis_context,
)
from detector_lab.contracts import (
    ExperimentBlackFacts,
    ExperimentBlurFacts,
    ExperimentMotionFacts,
    ExperimentWindowFacts,
)
from detector_lab.practical_alert_settings import (
    BlurMotionPenaltySettings,
    DarkFrameGuardrailSettings,
    MotionPreferenceSettings,
    PracticalBlackAlertSettings,
    PracticalBlurAlertSettings,
    PracticalMotionBlurAlertSettings,
)
from detectors import _clamp, analyze_video_metrics
from session_models import AlertEvent


_BLACK_ALERT_SETTINGS = PracticalBlackAlertSettings()
_DARK_FRAME_SETTINGS = DarkFrameGuardrailSettings()
_BLUR_V1_SETTINGS = PracticalBlurAlertSettings(threshold=0.70)
_BLUR_V2_SETTINGS = PracticalBlurAlertSettings(threshold=0.955)
_BLUR_V3_SETTINGS = PracticalBlurAlertSettings(threshold=0.955)
_MOTION_BLUR_SETTINGS = PracticalMotionBlurAlertSettings()
_BLUR_MOTION_PENALTY_SETTINGS = BlurMotionPenaltySettings()
_MOTION_PREFERENCE_SETTINGS = MotionPreferenceSettings()
_BLACK_WINDOW_CACHE_MAX_ENTRIES = 256

PracticalScoreEvaluator = Callable[[ExperimentWindowFacts], "PolicyScoreResult"]
PracticalRowBuilder = Callable[
    [AnalysisSlice, ExperimentWindowFacts, "PracticalDecision"],
    dict[str, object],
]


@dataclass(frozen=True)
class PracticalDecision:
    """One detector-lab practical decision plus its export metadata."""

    score: float
    threshold: float
    detected: bool
    guardrail_reason: str


@dataclass(frozen=True)
class PolicyScoreResult:
    """One practical policy score plus the guardrail reason behind it."""

    score: float
    guardrail_reason: str = ""


@dataclass
class PracticalEvaluationContext:
    """Small per-run cache for practical detector-lab evaluation reuse.

    The context keeps practical experiments efficient without turning the lab
    into a framework. One evaluation pass can reuse black-window rows, prepared
    blur contexts, and already-built fact payloads across neighboring slices.
    """

    black_window_rows: dict[tuple[object, ...], dict[str, object]]
    blur_analysis_contexts: dict[tuple[object, ...], BlurAnalysisContext]
    experiment_window_facts: dict[tuple[object, ...], ExperimentWindowFacts]
    max_black_window_rows: int = _BLACK_WINDOW_CACHE_MAX_ENTRIES

    def remember_black_window_row(
        self,
        cache_key: tuple[object, ...],
        row: dict[str, object],
    ) -> None:
        """Store one black-window detector row in the small practical cache."""
        if len(self.black_window_rows) >= self.max_black_window_rows:
            self.black_window_rows.clear()
        self.black_window_rows[cache_key] = dict(row)


_DEFAULT_EVALUATION_CONTEXT = PracticalEvaluationContext(
    black_window_rows={},
    blur_analysis_contexts={},
    experiment_window_facts={},
)
_ACTIVE_EVALUATION_CONTEXT: PracticalEvaluationContext | None = None
_BLACK_WINDOW_ROW_CACHE = _DEFAULT_EVALUATION_CONTEXT.black_window_rows


def _prepare_blur_analysis_context(analysis_slice: AnalysisSlice) -> BlurAnalysisContext:
    """Compatibility seam over the supported experiment blur-context API.

    Tests still patch this local name heavily, so practical-alert code keeps
    calling it even though the underlying supported API now lives in
    ``blur_experiments.py``.
    """
    return prepare_blur_analysis_context(analysis_slice)


def _compute_motion_coherence_multiscale(
    *,
    raw_frames: list[bytes],
    width: int,
    height: int,
):
    """Compatibility seam over the supported experiment motion API."""
    return compute_motion_coherence_multiscale(
        raw_frames=raw_frames,
        width=width,
        height=height,
    )


def analyze_practical_black_alert(
    analysis_slice: AnalysisSlice,
    *,
    evaluation_context: PracticalEvaluationContext | None = None,
) -> dict[str, object]:
    """Run the lab's simple black-frame alert policy on one slice."""
    settings = _BLACK_ALERT_SETTINGS
    context = _evaluation_context_or_default(evaluation_context)
    black_row = _analyze_black_window(analysis_slice, evaluation_context=context)
    window_duration = _window_duration_or_default(analysis_slice.window_duration_sec)
    black_ratio = _float_metric(black_row, "black_ratio")
    longest_black_sec = _float_metric(black_row, "longest_black_sec")
    total_black_sec = _float_metric(black_row, "total_black_sec")
    black_segment_count = _float_metric(black_row, "black_segment_count")

    black_score = _clamp(
        (0.45 * black_ratio)
        + (0.30 * _clamp(longest_black_sec / window_duration))
        + (0.15 * _clamp(total_black_sec / window_duration))
        + (0.10 * _clamp(black_segment_count / 2.0))
    )
    immediate_trigger = black_ratio >= settings.alert_ratio or (
        longest_black_sec / window_duration
    ) >= 0.80
    decision = PracticalDecision(
        score=round(black_score, 3),
        threshold=settings.score_threshold,
        detected=immediate_trigger or black_score >= settings.score_threshold,
        guardrail_reason="",
    )
    return _build_practical_black_row(
        analysis_slice=analysis_slice,
        black_row=black_row,
        decision=decision,
    )


def analyze_practical_blur_alert(
    analysis_slice: AnalysisSlice,
    *,
    evaluation_context: PracticalEvaluationContext | None = None,
) -> dict[str, object]:
    """Run the lab's first blur policy with only a black-frame guardrail."""
    return _run_fact_based_practical_alert(
        analysis_slice,
        include_motion=False,
        threshold=_BLUR_V1_SETTINGS.threshold,
        score_evaluator=_score_practical_blur_v1,
        row_builder=partial(_build_practical_blur_row, algorithm_version="v1"),
        evaluation_context=evaluation_context,
    )


def analyze_practical_blur_alert_v2(
    analysis_slice: AnalysisSlice,
    *,
    evaluation_context: PracticalEvaluationContext | None = None,
) -> dict[str, object]:
    """Run the second calibrated lab blur policy.

    This version intentionally leans on three low-redundancy signals:
    - absolute softness
    - medium-scale texture loss
    - reduced edge density

    It keeps the black-frame guardrail, removes the direct motion penalty, and
    only steps aside when a stricter motion-blur preference check succeeds.
    """
    return _run_fact_based_practical_alert(
        analysis_slice,
        include_motion=True,
        threshold=_BLUR_V2_SETTINGS.threshold,
        score_evaluator=_score_practical_blur_v2,
        row_builder=partial(_build_practical_blur_row, algorithm_version="v2"),
        evaluation_context=evaluation_context,
    )


def analyze_practical_blur_alert_v3(
    analysis_slice: AnalysisSlice,
    *,
    evaluation_context: PracticalEvaluationContext | None = None,
) -> dict[str, object]:
    """Run the third calibrated lab blur policy with extra transition skepticism.

    This keeps the v2 feature core and adds one more fast policy layer:
    when too much of the sampled window is very dark and low-contrast, the
    blur result is suppressed before alerting. That targets black-transition
    false positives without changing the blur feature set itself.
    """
    return _run_fact_based_practical_alert(
        analysis_slice,
        include_motion=True,
        threshold=_BLUR_V3_SETTINGS.threshold,
        score_evaluator=_score_practical_blur_v3,
        row_builder=partial(_build_practical_blur_row, algorithm_version="v3"),
        evaluation_context=evaluation_context,
    )


def analyze_practical_motion_blur_alert(
    analysis_slice: AnalysisSlice,
    *,
    evaluation_context: PracticalEvaluationContext | None = None,
) -> dict[str, object]:
    """Run the lab's motion-blur policy with black and softness guardrails."""
    return _run_fact_based_practical_alert(
        analysis_slice,
        include_motion=True,
        threshold=_MOTION_BLUR_SETTINGS.threshold,
        score_evaluator=_score_practical_motion_blur,
        row_builder=_build_practical_motion_blur_row,
        evaluation_context=evaluation_context,
    )


def build_experiment_window_facts(
    analysis_slice: AnalysisSlice,
    *,
    include_motion: bool = False,
    evaluation_context: PracticalEvaluationContext | None = None,
) -> ExperimentWindowFacts:
    """Build the stable practical-alert fact contract for one analyzed window.

    Practical alert experiments should depend on this supported seam instead of
    wiring together production rows, blur-analysis internals, and neighboring
    window lookups on their own.
    """
    cache_context = _evaluation_context_or_default(evaluation_context)
    cache_key = _experiment_window_facts_cache_key(
        analysis_slice,
        include_motion=include_motion,
    )
    cached_facts = cache_context.experiment_window_facts.get(cache_key)
    if cached_facts is not None:
        return cached_facts

    with _using_evaluation_context(cache_context):
        blur_context = _get_or_build_blur_analysis_context(
            analysis_slice,
            evaluation_context=cache_context,
        )
        previous_black_ratio, next_black_ratio = _neighbor_black_ratios(analysis_slice)
        facts = ExperimentWindowFacts(
            black=_build_experiment_black_facts(
                analysis_slice,
                evaluation_context=cache_context,
            ),
            blur=_build_experiment_blur_facts(blur_context),
            dark_frame_ratio=_dark_frame_ratio(blur_context.raw_frames),
            previous_black_ratio=previous_black_ratio,
            next_black_ratio=next_black_ratio,
            motion=_build_experiment_motion_facts(blur_context) if include_motion else None,
        )
    cache_context.experiment_window_facts[cache_key] = facts
    return facts


def _run_fact_based_practical_alert(
    analysis_slice: AnalysisSlice,
    *,
    include_motion: bool,
    threshold: float,
    score_evaluator: PracticalScoreEvaluator,
    row_builder: PracticalRowBuilder,
    evaluation_context: PracticalEvaluationContext | None = None,
) -> dict[str, object]:
    """Run one fact-based practical alert from facts, policy score, and row builder."""
    facts = build_experiment_window_facts(
        analysis_slice,
        include_motion=include_motion,
        evaluation_context=evaluation_context,
    )
    score_result = score_evaluator(facts)
    decision = _build_practical_decision(
        score=score_result.score,
        threshold=threshold,
        guardrail_reason=score_result.guardrail_reason,
    )
    return row_builder(
        analysis_slice=analysis_slice,
        facts=facts,
        decision=decision,
    )


def _build_practical_decision(
    *,
    score: float,
    threshold: float,
    guardrail_reason: str,
) -> PracticalDecision:
    """Return one normalized practical alert decision."""
    rounded_score = round(score, 3)
    return PracticalDecision(
        score=rounded_score,
        threshold=threshold,
        detected=score >= threshold,
        guardrail_reason=guardrail_reason,
    )


def _score_practical_blur_v1(facts: ExperimentWindowFacts) -> PolicyScoreResult:
    """Return the practical blur-v1 score and guardrail reason."""
    guardrail_reason = _blur_v1_guardrail_reason(facts)
    if guardrail_reason:
        return PolicyScoreResult(score=0.0, guardrail_reason=guardrail_reason)

    blur_evidence = _blur_v1_core_score(facts)
    motion_penalty = _blur_motion_penalty(
        motion_mean=facts.blur.motion_mean,
        motion_p90=facts.blur.motion_p90,
    )
    return PolicyScoreResult(score=_clamp(blur_evidence - motion_penalty))


def _score_practical_blur_v2(facts: ExperimentWindowFacts) -> PolicyScoreResult:
    """Return the practical blur-v2 score and guardrail reason."""
    return _score_calibrated_blur_policy(
        facts,
        allow_dark_transition_guardrails=False,
        allow_neighbor_black_penalty=False,
    )

def _score_practical_blur_v3(facts: ExperimentWindowFacts) -> PolicyScoreResult:
    """Return the practical blur-v3 score and guardrail reason."""
    return _score_calibrated_blur_policy(
        facts,
        allow_dark_transition_guardrails=True,
        allow_neighbor_black_penalty=True,
    )


def _score_practical_motion_blur(facts: ExperimentWindowFacts) -> PolicyScoreResult:
    """Return the practical motion-blur score and guardrail reason."""
    motion_metrics = facts.motion
    assert motion_metrics is not None

    base_softness = _motion_blur_base_softness(facts)
    motion_support = _motion_blur_support_score(facts, motion_metrics)
    guardrail_reason = _motion_blur_guardrail_reason(
        black_ratio=facts.black.black_ratio,
        neighbor_black_ratio=_neighbor_black_ratio(facts),
        base_softness=base_softness,
        motion_coherence=motion_metrics.motion_coherence,
        settings=_MOTION_BLUR_SETTINGS,
    )
    if guardrail_reason:
        return PolicyScoreResult(score=0.0, guardrail_reason=guardrail_reason)
    return PolicyScoreResult(score=_clamp((0.45 * base_softness) + (0.55 * motion_support)))


def evaluate_practical_alerts(session_id: str, row: dict[str, object]) -> list[AlertEvent]:
    """Emit one lab-only alert event when a practical row is already in alert state."""
    if not row.get("practical_detected"):
        return []
    detector_id = str(row.get("analyzer", ""))
    source_name = str(row.get("source_name", ""))
    title = _alert_title_for_detector(detector_id)
    score = _float_metric(row, "practical_score")
    threshold = _float_metric(row, "practical_threshold")
    message = f"{source_name} scored {score:.3f} against threshold {threshold:.3f}."
    return [
        AlertEvent(
            session_id=session_id,
            timestamp_utc=_timestamp_utc_now(),
            detector_id=detector_id,
            title=title,
            message=message,
            severity="warning",
            source_name=source_name,
            window_index=_int_metric(row, "window_index"),
            window_start_sec=_optional_float_metric(row, "window_start_sec"),
        )
    ]


def _evaluation_context_or_default(
    evaluation_context: PracticalEvaluationContext | None,
) -> PracticalEvaluationContext:
    """Return the provided practical evaluation context or the module default."""
    return evaluation_context if evaluation_context is not None else _DEFAULT_EVALUATION_CONTEXT


@contextmanager
def _using_evaluation_context(evaluation_context: PracticalEvaluationContext):
    """Temporarily expose one evaluation context to helper seams that stay monkeypatchable."""
    global _ACTIVE_EVALUATION_CONTEXT
    previous_context = _ACTIVE_EVALUATION_CONTEXT
    _ACTIVE_EVALUATION_CONTEXT = evaluation_context
    try:
        yield
    finally:
        _ACTIVE_EVALUATION_CONTEXT = previous_context


def _analyze_black_window(
    analysis_slice: AnalysisSlice,
    *,
    evaluation_context: PracticalEvaluationContext | None = None,
) -> dict[str, object]:
    """Run the production black detector on one analysis slice with per-run caching."""
    context = _evaluation_context_or_default(evaluation_context)
    cache_key = _black_window_cache_key(analysis_slice)
    cached_row = context.black_window_rows.get(cache_key)
    if cached_row is not None:
        return dict(cached_row)

    row = analyze_video_metrics(
        file_path=analysis_slice.file_path,
        source_group=analysis_slice.source_group,
        source_name=analysis_slice.source_name,
        window_index=analysis_slice.window_index,
        window_start_sec=analysis_slice.window_start_sec,
        window_duration_sec=analysis_slice.window_duration_sec,
    )
    materialized_row = _materialize_metric_row(row)
    context.remember_black_window_row(cache_key, materialized_row)
    return dict(materialized_row)


def _black_window_cache_key(analysis_slice: AnalysisSlice) -> tuple[object, ...]:
    """Return a stable cache key for one black-window detector lookup."""
    return (
        str(analysis_slice.file_path),
        analysis_slice.source_group,
        analysis_slice.source_name,
        analysis_slice.window_index,
        analysis_slice.window_start_sec,
        analysis_slice.window_duration_sec,
        id(analyze_video_metrics),
    )


def _materialize_metric_row(row: object) -> dict[str, object]:
    """Return one detector result row as a mutable plain dictionary."""
    if isinstance(row, dict):
        return dict(row)
    to_dict = getattr(row, "to_dict", None)
    if callable(to_dict):
        materialized = to_dict()
        if isinstance(materialized, dict):
            return dict(materialized)
    raise TypeError("Expected analyze_video_metrics to return a dict-like row")


def _blur_analysis_context_cache_key(
    analysis_slice: AnalysisSlice,
) -> tuple[object, ...]:
    """Return a stable cache key for prepared blur-analysis context reuse."""
    return (
        str(analysis_slice.file_path),
        analysis_slice.source_group,
        analysis_slice.source_name,
        analysis_slice.window_index,
        analysis_slice.window_start_sec,
        analysis_slice.window_duration_sec,
        id(_prepare_blur_analysis_context),
    )


def _experiment_window_facts_cache_key(
    analysis_slice: AnalysisSlice,
    *,
    include_motion: bool,
) -> tuple[object, ...]:
    """Return a stable cache key for one built experiment-window facts payload."""
    return (
        *_black_window_cache_key(analysis_slice),
        include_motion,
        id(_prepare_blur_analysis_context),
        id(_neighbor_black_ratios),
        id(_dark_frame_ratio),
        id(_compute_motion_coherence_multiscale),
    )


def _get_or_build_blur_analysis_context(
    analysis_slice: AnalysisSlice,
    *,
    evaluation_context: PracticalEvaluationContext | None = None,
) -> BlurAnalysisContext:
    """Return one prepared blur-analysis context, reusing cached work when possible."""
    context = _evaluation_context_or_default(evaluation_context)
    cache_key = _blur_analysis_context_cache_key(analysis_slice)
    cached_context = context.blur_analysis_contexts.get(cache_key)
    if cached_context is not None:
        return cached_context
    blur_context = _prepare_blur_analysis_context(analysis_slice)
    context.blur_analysis_contexts[cache_key] = blur_context
    return blur_context


def _build_experiment_black_facts(
    analysis_slice: AnalysisSlice,
    *,
    evaluation_context: PracticalEvaluationContext | None = None,
) -> ExperimentBlackFacts:
    """Return black-lane facts for one practical-alert analysis slice."""
    black_row = _analyze_black_window(
        analysis_slice,
        evaluation_context=evaluation_context,
    )
    return ExperimentBlackFacts(
        processing_sec=_float_metric(black_row, "processing_sec"),
        black_segment_count=int(_float_metric(black_row, "black_segment_count")),
        total_black_sec=_float_metric(black_row, "total_black_sec"),
        longest_black_sec=_float_metric(black_row, "longest_black_sec"),
        black_ratio=_float_metric(black_row, "black_ratio"),
    )


def _build_experiment_blur_facts(context: BlurAnalysisContext) -> ExperimentBlurFacts:
    """Return blur-lane facts from one shared blur-analysis context."""
    measurements = context.measurements
    return ExperimentBlurFacts(
        sample_count=len(getattr(measurements, "frame_scores", [])),
        sharpness_p10=_measurement_float(measurements, "sharpness_p10"),
        sharpness_p90=_measurement_float(measurements, "sharpness_p90"),
        motion_mean=_measurement_float(measurements, "motion_mean"),
        motion_p90=_measurement_float(measurements, "motion_p90"),
        absolute_blur=max(getattr(measurements, "absolute_blur_scores", []), default=0.0),
        dynamic_blur=max(getattr(measurements, "dynamic_blur_scores", []), default=0.0),
        edge_density=_measurement_float(measurements, "edge_density"),
        texture_energy=_measurement_float(measurements, "texture_energy"),
        medium_scale_texture_energy=_measurement_float(
            measurements,
            "medium_scale_texture_energy",
        ),
        structure_strength=_structure_strength_from_measurements(measurements),
    )


def _build_experiment_motion_facts(context: BlurAnalysisContext) -> ExperimentMotionFacts:
    """Return motion facts from one shared blur-analysis context."""
    motion_metrics = _compute_motion_coherence_multiscale(
        raw_frames=context.raw_frames,
        width=context.sample_width,
        height=context.sample_height,
    )
    return ExperimentMotionFacts(
        fine_scale_motion_energy=motion_metrics.fine_scale_motion_energy,
        medium_scale_motion_energy=motion_metrics.medium_scale_motion_energy,
        coarse_scale_motion_energy=motion_metrics.coarse_scale_motion_energy,
        motion_persistence=motion_metrics.motion_persistence,
        motion_coherence=motion_metrics.motion_coherence,
        motion_incoherence_penalty=motion_metrics.incoherence_avg,
    )


def _neighbor_black_ratios(
    analysis_slice: AnalysisSlice,
) -> tuple[float, float]:
    """Return previous and next black ratios for one fixed-duration local window."""
    return _neighbor_black_ratios_for_context(
        analysis_slice,
        evaluation_context=_ACTIVE_EVALUATION_CONTEXT,
    )


def _neighbor_black_ratios_for_context(
    analysis_slice: AnalysisSlice,
    *,
    evaluation_context: PracticalEvaluationContext | None,
) -> tuple[float, float]:
    """Return previous and next black ratios for one fixed-duration local window."""
    if (
        analysis_slice.window_start_sec is None
        or analysis_slice.window_duration_sec is None
        or analysis_slice.window_duration_sec <= 0
    ):
        return (0.0, 0.0)

    return (
        _previous_black_ratio(
            analysis_slice,
            evaluation_context=evaluation_context,
        ),
        _next_black_ratio(
            analysis_slice,
            evaluation_context=evaluation_context,
        ),
    )


def _previous_black_ratio(
    analysis_slice: AnalysisSlice,
    *,
    evaluation_context: PracticalEvaluationContext | None = None,
) -> float:
    """Return the black ratio for the previous fixed-duration window."""
    adjacent_slice = _adjacent_analysis_slice(analysis_slice, offset=-1)
    if adjacent_slice is None:
        return 0.0
    return _black_ratio_for_slice(
        adjacent_slice,
        evaluation_context=evaluation_context,
    )


def _next_black_ratio(
    analysis_slice: AnalysisSlice,
    *,
    evaluation_context: PracticalEvaluationContext | None = None,
) -> float:
    """Return the black ratio for the next fixed-duration window."""
    adjacent_slice = _adjacent_analysis_slice(analysis_slice, offset=1)
    if adjacent_slice is None:
        return 0.0
    return _black_ratio_for_slice(
        adjacent_slice,
        evaluation_context=evaluation_context,
    )


def _adjacent_analysis_slice(
    analysis_slice: AnalysisSlice,
    *,
    offset: int,
) -> AnalysisSlice | None:
    """Return the neighboring fixed-duration slice at the requested offset."""
    if (
        analysis_slice.window_start_sec is None
        or analysis_slice.window_duration_sec is None
        or analysis_slice.window_duration_sec <= 0
    ):
        return None
    target_start = analysis_slice.window_start_sec + (offset * analysis_slice.window_duration_sec)
    if target_start < 0:
        return None
    target_index = (
        analysis_slice.window_index + offset
        if analysis_slice.window_index is not None
        else None
    )
    return AnalysisSlice(
        file_path=analysis_slice.file_path,
        source_group=analysis_slice.source_group,
        source_name=analysis_slice.source_name,
        window_index=target_index,
        window_start_sec=target_start,
        window_duration_sec=analysis_slice.window_duration_sec,
    )


def _black_ratio_for_slice(
    analysis_slice: AnalysisSlice,
    *,
    evaluation_context: PracticalEvaluationContext | None = None,
) -> float:
    """Return the production black ratio for one neighboring analysis slice."""
    return _float_metric(
        _analyze_black_window(
            analysis_slice,
            evaluation_context=evaluation_context,
        ),
        "black_ratio",
    )


def _build_practical_black_row(
    *,
    analysis_slice: AnalysisSlice,
    black_row: dict[str, object],
    decision: PracticalDecision,
) -> dict[str, object]:
    """Build one export row for the practical black alert."""
    return {
        **_practical_row_base(
            analyzer="practical_black_alert",
            analysis_slice=analysis_slice,
            source_group=str(black_row.get("source_group", analysis_slice.source_group)),
            source_name=str(black_row.get("source_name", analysis_slice.source_name)),
            processing_sec=_float_metric(black_row, "processing_sec"),
        ),
        "black_detected": decision.detected,
        "black_segment_count": black_row.get("black_segment_count", 0),
        "total_black_sec": black_row.get("total_black_sec", 0.0),
        "longest_black_sec": black_row.get("longest_black_sec", 0.0),
        "black_ratio": black_row.get("black_ratio", 0.0),
        **_decision_fields(decision),
    }


def _build_practical_blur_row(
    *,
    analysis_slice: AnalysisSlice,
    facts: ExperimentWindowFacts,
    decision: PracticalDecision,
    algorithm_version: str,
) -> dict[str, object]:
    """Build one export row for the practical blur alert."""
    return {
        **_practical_row_base(
            analyzer=f"practical_blur_alert_{algorithm_version}",
            analysis_slice=analysis_slice,
            source_group=analysis_slice.source_group,
            source_name=analysis_slice.source_name,
            processing_sec=facts.black.processing_sec,
        ),
        **_blur_metric_fields(facts),
        "blur_score": decision.score,
        "blur_detected": decision.detected,
        "threshold_used": decision.threshold,
        "black_ratio": facts.black.black_ratio,
        **_decision_fields(decision),
    }


def _build_practical_motion_blur_row(
    *,
    analysis_slice: AnalysisSlice,
    facts: ExperimentWindowFacts,
    decision: PracticalDecision,
) -> dict[str, object]:
    """Build one export row for the practical motion-blur alert."""
    motion_metrics = facts.motion
    assert motion_metrics is not None
    return {
        **_practical_row_base(
            analyzer="practical_motion_blur_alert",
            analysis_slice=analysis_slice,
            source_group=analysis_slice.source_group,
            source_name=analysis_slice.source_name,
            processing_sec=facts.black.processing_sec,
        ),
        **_blur_metric_fields(facts),
        "dynamic_blur": round(facts.blur.dynamic_blur, 3),
        **_motion_metric_fields(motion_metrics),
        "blur_score": decision.score,
        "blur_detected": decision.detected,
        "threshold_used": decision.threshold,
        "black_ratio": facts.black.black_ratio,
        **_decision_fields(decision),
    }


def _practical_row_base(
    *,
    analyzer: str,
    analysis_slice: AnalysisSlice,
    source_group: str,
    source_name: str,
    processing_sec: float,
) -> dict[str, object]:
    """Return the common export fields shared by practical detector rows."""
    return {
        "analyzer": analyzer,
        "source_type": "video",
        "source_group": source_group,
        "source_name": source_name,
        "window_index": analysis_slice.window_index,
        "window_start_sec": analysis_slice.window_start_sec,
        "window_duration_sec": analysis_slice.window_duration_sec,
        "processing_sec": round(processing_sec, 3),
    }


def _decision_fields(decision: PracticalDecision) -> dict[str, object]:
    """Return shared practical-decision export fields."""
    return {
        "practical_score": decision.score,
        "practical_threshold": decision.threshold,
        "practical_detected": decision.detected,
        "guardrail_reason": decision.guardrail_reason,
    }


def _blur_metric_fields(facts: ExperimentWindowFacts) -> dict[str, object]:
    """Return the rounded blur metrics shared by practical blur lanes."""
    return {
        "sample_count": facts.blur.sample_count,
        "sharpness_p10": round(facts.blur.sharpness_p10, 3),
        "sharpness_p90": round(facts.blur.sharpness_p90, 3),
        "motion_mean": round(facts.blur.motion_mean, 3),
        "motion_p90": round(facts.blur.motion_p90, 3),
        "absolute_blur": round(facts.blur.absolute_blur, 3),
        "edge_density": round(facts.blur.edge_density, 3),
        "texture_energy": round(facts.blur.texture_energy, 3),
        "medium_scale_texture_energy": round(facts.blur.medium_scale_texture_energy, 3),
        "structure_strength": round(facts.blur.structure_strength, 3),
    }


def _motion_metric_fields(motion_metrics: ExperimentMotionFacts) -> dict[str, object]:
    """Return the rounded motion metrics shared by motion-blur rows."""
    return {
        "fine_scale_motion_energy": round(motion_metrics.fine_scale_motion_energy, 3),
        "medium_scale_motion_energy": round(motion_metrics.medium_scale_motion_energy, 3),
        "coarse_scale_motion_energy": round(motion_metrics.coarse_scale_motion_energy, 3),
        "motion_persistence": round(motion_metrics.motion_persistence, 3),
        "motion_coherence": round(motion_metrics.motion_coherence, 3),
        "motion_incoherence_penalty": round(motion_metrics.motion_incoherence_penalty, 3),
    }


def _structure_strength_from_measurements(measurements) -> float:
    """Return the same-scale structure summary used by the practical blur rule."""
    return _clamp(
        (_measurement_float(measurements, "edge_density") * 0.4)
        + (_measurement_float(measurements, "mean_edge_strength") * 0.4)
        + ((max(_measurement_float(measurements, "texture_energy"), 0.0) ** 0.5) * 0.2)
    )


def _blur_v1_guardrail_reason(facts: ExperimentWindowFacts) -> str:
    """Return the early suppression reason for the practical blur-v1 policy."""
    settings = _BLUR_V1_SETTINGS
    if facts.black.black_ratio >= settings.transition.black_dominant_ratio:
        return "black_dominant"
    return ""


def _blur_v1_core_score(facts: ExperimentWindowFacts) -> float:
    """Return the pre-penalty blur evidence score for the practical blur-v1 policy."""
    return _clamp(
        (0.30 * facts.blur.absolute_blur)
        + (0.20 * (1.0 - facts.blur.texture_energy))
        + (0.15 * (1.0 - facts.blur.medium_scale_texture_energy))
        + (0.15 * (1.0 - facts.blur.edge_density))
        + (0.10 * (1.0 - _clamp(facts.blur.sharpness_p90)))
        + (0.10 * (1.0 - facts.blur.structure_strength))
    )


def _weighted_geometric_blur_core(
    *,
    absolute_blur: float,
    inverse_medium_texture: float,
    inverse_edge_density: float,
) -> float:
    """Return a compact blur core from the strongest low-redundancy metrics."""
    return _clamp(
        (absolute_blur ** 0.30)
        * (inverse_medium_texture ** 0.40)
        * (inverse_edge_density ** 0.30)
    )


def _calibrated_blur_core_score(facts: ExperimentWindowFacts) -> float:
    """Return the calibrated practical blur core for v2/v3 policies."""
    return _weighted_geometric_blur_core(
        absolute_blur=facts.blur.absolute_blur,
        inverse_medium_texture=1.0 - facts.blur.medium_scale_texture_energy,
        inverse_edge_density=1.0 - facts.blur.edge_density,
    )


def _score_calibrated_blur_policy(
    facts: ExperimentWindowFacts,
    *,
    allow_dark_transition_guardrails: bool,
    allow_neighbor_black_penalty: bool,
) -> PolicyScoreResult:
    """Return one calibrated blur-policy result with grouped guardrail handling."""
    if allow_dark_transition_guardrails:
        guardrail_reason = _blur_v3_guardrail_reason(
            facts,
            settings=_BLUR_V3_SETTINGS,
        )
    else:
        guardrail_reason = _calibrated_blur_guardrail_reason(
            facts,
            settings=_BLUR_V2_SETTINGS,
        )
    if guardrail_reason:
        return PolicyScoreResult(score=0.0, guardrail_reason=guardrail_reason)

    blur_evidence = _calibrated_blur_core_score(facts)
    if _prefers_motion_blur_classification(facts=facts):
        return PolicyScoreResult(score=0.0, guardrail_reason="prefer_motion_blur")

    if not allow_neighbor_black_penalty:
        return PolicyScoreResult(score=blur_evidence)

    final_score = _neighbor_black_adjusted_blur_score(
        blur_score=blur_evidence,
        black_ratio=facts.black.black_ratio,
        neighbor_black_ratio=_neighbor_black_ratio(facts),
        edge_density=facts.blur.edge_density,
        medium_scale_texture_energy=facts.blur.medium_scale_texture_energy,
    )
    if final_score < blur_evidence:
        return PolicyScoreResult(
            score=final_score,
            guardrail_reason="black_neighbor_transition",
        )
    return PolicyScoreResult(score=final_score)


def _neighbor_black_ratio(facts: ExperimentWindowFacts) -> float:
    """Return the strongest adjacent black-ratio context for one window."""
    return max(facts.previous_black_ratio, facts.next_black_ratio)


def _calibrated_blur_guardrail_reason(
    facts: ExperimentWindowFacts,
    *,
    settings: PracticalBlurAlertSettings,
) -> str:
    """Return the early suppression reason for calibrated blur policies."""
    if facts.black.black_ratio >= settings.transition.black_dominant_ratio:
        return "black_dominant"
    return ""


def _blur_v3_guardrail_reason(
    facts: ExperimentWindowFacts,
    *,
    settings: PracticalBlurAlertSettings,
) -> str:
    """Return the hard-suppression reason for blur v3 before score shaping."""
    black_ratio = facts.black.black_ratio
    dark_frame_ratio = facts.dark_frame_ratio
    if black_ratio >= settings.transition.black_dominant_ratio:
        return "black_dominant"
    if dark_frame_ratio >= _DARK_FRAME_SETTINGS.hard_window_ratio_threshold:
        return "dark_frame_dominant"
    if (
        black_ratio >= settings.transition.black_dark_mix_black_ratio
        and dark_frame_ratio >= settings.transition.black_dark_mix_dark_ratio
    ):
        return "black_dark_transition"
    return ""


def _neighbor_black_adjusted_blur_score(
    *,
    blur_score: float,
    black_ratio: float,
    neighbor_black_ratio: float,
    edge_density: float,
    medium_scale_texture_energy: float,
) -> float:
    """Return a blur score softened by black-neighbor context.

    Strongly blur-like windows are allowed to bypass the neighbor penalty so we
    do not lose obvious positives near black transitions.
    """
    settings = _BLUR_V3_SETTINGS.transition
    if _is_strong_structure_collapse(
        edge_density=edge_density,
        medium_scale_texture_energy=medium_scale_texture_energy,
    ):
        return blur_score
    if (
        neighbor_black_ratio >= settings.neighbor_black_hard_ratio
        and blur_score < settings.neighbor_black_hard_max_blur_score
    ):
        return _clamp(blur_score * settings.neighbor_black_hard_penalty)
    if (
        black_ratio >= settings.current_black_mix_ratio
        and neighbor_black_ratio >= settings.neighbor_black_mix_ratio
        and blur_score < settings.neighbor_black_mix_max_blur_score
    ):
        return _clamp(blur_score * settings.neighbor_black_mix_penalty)
    return blur_score


def _motion_blur_guardrail_reason(
    *,
    black_ratio: float,
    neighbor_black_ratio: float,
    base_softness: float,
    motion_coherence: float,
    settings: PracticalMotionBlurAlertSettings,
) -> str:
    """Return the first motion-blur guardrail reason that suppresses detection."""
    transition = settings.transition
    if black_ratio >= transition.black_dominant_ratio:
        return "black_dominant"
    if neighbor_black_ratio >= transition.neighbor_black_hard_ratio:
        return "black_transition_motion"
    if (
        black_ratio >= transition.current_black_mix_ratio
        and neighbor_black_ratio >= transition.neighbor_black_mix_ratio
    ):
        return "black_transition_motion"
    if base_softness < settings.min_softness:
        return "softness_too_low"
    if motion_coherence < settings.min_coherence:
        return "motion_incoherent"
    return ""


def _motion_blur_base_softness(facts: ExperimentWindowFacts) -> float:
    """Return the softness half of the practical motion-blur policy."""
    return _clamp(
        (0.45 * facts.blur.absolute_blur)
        + (0.35 * facts.blur.dynamic_blur)
        + (0.20 * (1.0 - facts.blur.texture_energy))
    )


def _motion_blur_support_score(
    facts: ExperimentWindowFacts,
    motion_metrics: ExperimentMotionFacts,
) -> float:
    """Return the motion-support half of the practical motion-blur policy."""
    return _clamp(
        (0.35 * motion_metrics.motion_coherence)
        + (0.35 * motion_metrics.motion_persistence)
        + (0.20 * facts.blur.motion_p90)
        + (0.10 * facts.blur.motion_mean)
    )


def _is_strong_structure_collapse(
    *,
    edge_density: float,
    medium_scale_texture_energy: float,
) -> bool:
    """Return whether the window already looks strongly blur-positive."""
    settings = _BLUR_V3_SETTINGS.transition
    return (
        edge_density <= settings.structure_escape_edge_density
        and medium_scale_texture_energy <= settings.structure_escape_medium_texture
    )


def _dark_frame_ratio(raw_frames: list[bytes]) -> float:
    """Return the share of sampled frames that are dark and low-contrast."""
    if not raw_frames:
        return 0.0
    dark_count = sum(1 for frame in raw_frames if _is_dark_frame(frame))
    return dark_count / len(raw_frames)


def _is_dark_frame(pixels: bytes) -> bool:
    """Return whether one grayscale frame is too dark for reliable blur scoring."""
    settings = _DARK_FRAME_SETTINGS
    if not pixels:
        return False
    mean_luma = sum(pixels) / len(pixels)
    variance = sum((pixel - mean_luma) ** 2 for pixel in pixels) / len(pixels)
    contrast = sqrt(variance)
    return (
        mean_luma < settings.mean_luma_threshold
        and contrast < settings.contrast_threshold
    )


def _blur_motion_penalty(*, motion_mean: float, motion_p90: float) -> float:
    """Return the motion ambiguity penalty used by the practical blur rule."""
    settings = _BLUR_MOTION_PENALTY_SETTINGS
    if (
        motion_p90 >= settings.high_motion_p90_threshold
        or motion_mean >= settings.high_motion_mean_threshold
    ):
        return settings.high_penalty
    if (
        motion_p90 >= settings.moderate_motion_p90_threshold
        or motion_mean >= settings.moderate_motion_mean_threshold
    ):
        return settings.moderate_penalty
    return 0.0


def _prefers_motion_blur_classification(
    *,
    facts: ExperimentWindowFacts | None = None,
    measurements=None,
    raw_frames: list[bytes] | None = None,
    sample_width: int | None = None,
    sample_height: int | None = None,
) -> bool:
    """Return whether a blur-positive window looks strongly motion-blur-like.

    This is intentionally much stricter than the current practical motion-blur
    alert. It acts as a classification preference, not a general motion veto.
    """
    settings = _MOTION_PREFERENCE_SETTINGS
    if facts is not None:
        motion_mean = facts.blur.motion_mean
        motion_p90 = facts.blur.motion_p90
        motion_metrics = facts.motion
        assert motion_metrics is not None
        motion_persistence = motion_metrics.motion_persistence
        motion_coherence = motion_metrics.motion_coherence
    else:
        assert measurements is not None
        assert raw_frames is not None
        assert sample_width is not None
        assert sample_height is not None
        motion_metrics = _compute_motion_coherence_multiscale(
            raw_frames=raw_frames,
            width=sample_width,
            height=sample_height,
        )
        motion_mean = _measurement_float(measurements, "motion_mean")
        motion_p90 = _measurement_float(measurements, "motion_p90")
        motion_persistence = motion_metrics.motion_persistence
        motion_coherence = motion_metrics.motion_coherence
    return (
        motion_mean >= settings.motion_mean_threshold
        and motion_p90 >= settings.motion_p90_threshold
        and motion_persistence >= settings.persistence_threshold
        and motion_coherence >= settings.coherence_threshold
    )


def _window_duration_or_default(window_duration_sec: float | None) -> float:
    """Return a safe positive window duration for score normalization."""
    return max(window_duration_sec or 1.0, 1.0)


def _float_metric(row: dict[str, object], key: str) -> float:
    """Return one numeric detector-row value as ``float``."""
    value = row.get(key, 0.0)
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _optional_float_metric(row: dict[str, object], key: str) -> float | None:
    """Return one optional numeric detector-row value as ``float``."""
    value = row.get(key)
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int_metric(row: dict[str, object], key: str) -> int | None:
    """Return one optional integer detector-row value."""
    value = row.get(key)
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _measurement_float(measurements, attribute: str, default: float = 0.0) -> float:
    """Return one measurement attribute as ``float`` with a safe default."""
    value = getattr(measurements, attribute, default)
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _alert_title_for_detector(detector_id: str) -> str:
    """Return the stable operator-facing title for one practical alert lane."""
    if detector_id == "practical_black_alert":
        return "Practical black frame alert"
    if detector_id == "practical_motion_blur_alert":
        return "Practical motion blur alert"
    if detector_id == "practical_blur_alert_v2":
        return "Practical blur alert v2"
    if detector_id == "practical_blur_alert_v3":
        return "Practical blur alert v3"
    return "Practical blur alert"


def _timestamp_utc_now() -> str:
    """Return the detector-lab timestamp format used by alert rows."""
    return strftime("%Y-%m-%d %H:%M:%S", gmtime())
