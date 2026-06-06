"""Production alert policy for detector result rows.

The current runtime keeps alerting intentionally small and explicit:

- black-screen policy on top of ``video_metrics``
- blur policy on top of ``video_blur``

Detectors own signal extraction. This module owns rule decisions, rolling
state, recovery hysteresis, and operator-facing message text. The processor
normalizes detector output into ``RuntimeResultRow`` objects before it reaches
this file, so rule code can stay focused on policy rather than raw payload
plumbing.
"""

from collections import defaultdict, deque
from dataclasses import dataclass, field
from statistics import median
from typing import Callable

from analyzer_contract import AlertRuleCatalogEntry, DetectorOrigin, DetectorStatus, RuntimeResultRow
import config
from logger import format_log_context, get_logger
from session_models import AlertEvent, EventSeverity


RuleRowLike = RuntimeResultRow | dict[str, object]
Predicate = Callable[[RuntimeResultRow], bool]
MessageBuilder = Callable[[RuntimeResultRow], str]
RuleStateKey = tuple[str, str, str]
logger = get_logger(__name__)


@dataclass
class BlackSample:
    """One black-screen sample stored in the rolling evaluation window."""

    duration_sec: float
    black_ratio: float


@dataclass(frozen=True)
class BlackWindowSummary:
    """Aggregated black-screen facts for one source group's current window."""

    rolling_ratio: float
    observed_window_sec: float


@dataclass(frozen=True)
class BlurSample:
    """One blur sample stored in the rolling evaluation window."""

    blur_score: float
    motion_mean: float
    motion_p90: float


@dataclass(frozen=True)
class BlurWindowSummary:
    """Aggregated blur and motion facts for one source group's current window."""

    scores: tuple[float, ...]
    motion_means: tuple[float, ...]
    motion_p90s: tuple[float, ...]
    median_score: float
    high_count: int
    motion_median: float
    motion_peak: float
    window_is_full: bool


@dataclass(frozen=True)
class BlurEntryDecision:
    """Blur-rule entry decision for one rolling evaluation step."""

    should_alert: bool
    state: str


@dataclass(frozen=True)
class RuleDecision:
    """One rule decision separated from any row-facing export metadata."""

    should_alert: bool
    state: str
    reason: str = ""


@dataclass(frozen=True)
class RuleRowAnnotation:
    """Row-facing export metadata produced after one rule evaluation."""

    metrics: dict[str, object]
    state_fields: dict[str, object]


@dataclass(frozen=True)
class BlackRuleEvaluationResult:
    """Final black-rule decision plus row-facing export metadata."""

    decision: RuleDecision
    annotation: RuleRowAnnotation


@dataclass(frozen=True)
class BlurRuleEvaluationResult:
    """Final blur-rule decision plus row-facing export metadata."""

    decision: RuleDecision
    annotation: RuleRowAnnotation


@dataclass(frozen=True)
class BlackRuleFacts:
    """Typed black-rule inputs derived from one detector row."""

    source_group: str
    duration_sec: float
    black_ratio: float
    longest_black_sec: float


@dataclass(frozen=True)
class BlurRuleFacts:
    """Typed blur-rule inputs derived from one detector row."""

    source_group: str
    blur_score: float
    motion_mean: float
    motion_p90: float


@dataclass
class RuleStateStore:
    """All rolling alert-rule state kept by the production runtime.

    The state stays module-local and small on purpose. At the current project
    stage we only need per-session, per-detector, per-source-group memory for
    the built-in black and blur rules.
    """

    black_windows: dict[RuleStateKey, deque[BlackSample]] = field(
        default_factory=lambda: defaultdict(deque)
    )
    black_active: dict[RuleStateKey, bool] = field(default_factory=dict)
    blur_windows: dict[RuleStateKey, deque[BlurSample]] = field(
        default_factory=lambda: defaultdict(deque)
    )
    blur_active: dict[RuleStateKey, bool] = field(default_factory=dict)
    blur_sample_counts: dict[RuleStateKey, int] = field(default_factory=lambda: defaultdict(int))


@dataclass(frozen=True)
class AlertRule:
    """Rule metadata plus the callables used to evaluate and format alerts.

    The catalog is intentionally lightweight: each entry ties a detector id to
    one production policy, one message builder, and one event severity.
    """

    id: str
    detector_id: str
    display_name: str
    description: str
    title: str
    message_builder: MessageBuilder
    should_alert: Predicate
    origin: DetectorOrigin = "built_in"
    status: DetectorStatus = "core"
    severity: EventSeverity = "warning"
    evaluator: Callable[[str, RuntimeResultRow], bool] | None = None


_RULE_STATE = RuleStateStore()


def _video_black_should_alert(row: RuntimeResultRow) -> bool:
    """Return whether the detector row claims black content is present."""
    return bool(row.get("black_detected"))


def _video_blur_should_alert(row: RuntimeResultRow) -> bool:
    """Return whether the detector row claims blur content is present."""
    return bool(row.get("blur_detected"))


def _video_black_evaluator(session_id: str, row: RuntimeResultRow) -> bool:
    """Evaluate the default production black-screen rule for one row."""
    return should_alert_video_black(session_id, row)


def _video_blur_evaluator(session_id: str, row: RuntimeResultRow) -> bool:
    """Evaluate the default production blur rule for one row."""
    return should_alert_video_blur(session_id, row)


def _video_black_message(row: RuntimeResultRow) -> str:
    """Build the default black-screen alert message for one row."""
    return build_video_black_message(row)


def _video_blur_message(row: RuntimeResultRow) -> str:
    """Build the default blur alert message for one row."""
    return build_video_blur_message(row)


VIDEO_BLACK_RULE = AlertRule(
    id="video_metrics.default_rule",
    detector_id="video_metrics",
    display_name="Default Black Screen Rule",
    description="Built-in black-screen alert policy with rolling state and recovery hysteresis.",
    title="Black screen detected",
    should_alert=_video_black_should_alert,
    message_builder=_video_black_message,
    evaluator=_video_black_evaluator,
)

VIDEO_BLUR_RULE = AlertRule(
    id="video_blur.default_rule",
    detector_id="video_blur",
    display_name="Default Blur Rule",
    description="Built-in rolling blur alert policy with entry, recovery, and no-repeat behavior.",
    title="Blur warning",
    should_alert=_video_blur_should_alert,
    message_builder=_video_blur_message,
    status="optional",
    evaluator=_video_blur_evaluator,
)

REGISTERED_ALERT_RULES = (VIDEO_BLACK_RULE, VIDEO_BLUR_RULE)
RULES_BY_DETECTOR = {
    rule.detector_id: rule
    for rule in REGISTERED_ALERT_RULES
}
RULES_BY_ID = {rule.id: rule for rule in REGISTERED_ALERT_RULES}


def list_available_alert_rules() -> list[AlertRuleCatalogEntry]:
    """Return lightweight metadata for the built-in rules."""
    return [
        {
            "id": rule.id,
            "detector_id": rule.detector_id,
            "display_name": rule.display_name,
            "description": rule.description,
            "origin": rule.origin,
            "status": rule.status,
        }
        for rule in REGISTERED_ALERT_RULES
    ]


def evaluate_alerts(
    session_id: str,
    detector_id: str,
    row: RuleRowLike,
) -> list[AlertEvent]:
    """Evaluate the configured production rule for one detector result row.

    The flow is intentionally straightforward:

    1. resolve the rule for the detector id
    2. normalize the row into the runtime rule contract
    3. evaluate the stateful policy
    4. build an alert event only on fresh entry
    """
    rule = _resolve_alert_rule(detector_id)
    if rule is None:
        return []

    row_for_rules = (
        row.clone()
        if isinstance(row, RuntimeResultRow)
        else _coerce_runtime_rule_row(row, detector_id=detector_id)
    )
    try:
        should_emit = _evaluate_rule(session_id, rule, row_for_rules)
        if not should_emit:
            return []

        return [_build_alert_event(session_id, detector_id, rule, row_for_rules)]
    except Exception as error:
        _log_rule_evaluation_failure(
            session_id=session_id,
            detector_id=detector_id,
            row=row_for_rules,
            rule=rule,
        )
        raise ValueError(f"Alert rule evaluation failed for {rule.id}") from error


def reset_session_rule_state(session_id: str) -> None:
    """Drop all rolling rule state for one session."""
    _clear_black_rule_state(session_id)
    _clear_blur_rule_state(session_id)


def should_alert_video_black(session_id: str, row: RuleRowLike) -> bool:
    """Return whether the black-screen rule should emit an alert for this row.

    Entry is driven either by a long continuous black interval or by a rolling
    black ratio that stays high enough for long enough. Once active, the rule
    suppresses duplicates until the rolling state clearly recovers.
    """
    runtime_row = _coerce_runtime_rule_row(row, detector_id="video_metrics")
    facts = _black_rule_facts_from_row(runtime_row)
    evaluation = _evaluate_video_black_rule(session_id, facts)
    _apply_rule_annotation(runtime_row, evaluation.annotation)
    if isinstance(row, dict):
        row.update(runtime_row.to_dict())
    return evaluation.decision.should_alert


def build_video_black_message(row: RuntimeResultRow) -> str:
    """Build the operator-facing black-screen message."""
    source_name = row.get("source_name", "Video")
    longest_black = row.get("longest_black_sec", 0.0)
    black_ratio = row.get("black_ratio", 0.0)
    rolling_ratio = row.get("rolling_black_ratio", black_ratio)
    reason = row.get("black_rule_reason")

    if reason == "continuous_black":
        return (
            f"{source_name} entered a black-screen state. "
            f"Longest black interval {longest_black} sec."
        )

    return (
        f"{source_name} entered a black-screen state. "
        f"Rolling black ratio across the last {config.VIDEO_BLACK_SAMPLE_WINDOW_SEC:.0f} sec was "
        f"{rolling_ratio}, current slice ratio {black_ratio}."
    )


def should_alert_video_blur(session_id: str, row: RuleRowLike) -> bool:
    """Return whether the blur rule should emit an alert for this row.

    Entry requires enough history, enough above-threshold blur evidence in the
    current rolling window, and motion metrics that do not explain the
    softness as ordinary camera movement.
    """
    runtime_row = _coerce_runtime_rule_row(row, detector_id="video_blur")
    facts = _blur_rule_facts_from_row(runtime_row)
    evaluation = _evaluate_video_blur_rule(session_id, facts)
    _apply_rule_annotation(runtime_row, evaluation.annotation)
    if isinstance(row, dict):
        row.update(runtime_row.to_dict())
    return evaluation.decision.should_alert


def build_video_blur_message(row: RuntimeResultRow) -> str:
    """Build the operator-facing blur message."""
    source_name = row.get("source_name", "Video")
    rolling_median = row.get("rolling_blur_median", row.get("blur_score", 0.0))
    threshold = row.get("threshold_used", config.VIDEO_BLUR_ALERT_THRESHOLD)
    high_count = row.get("rolling_blur_high_count", 0)

    return (
        f"{source_name} entered a blurry state. "
        f"Median blur across the last {config.VIDEO_BLUR_WINDOW_SIZE} slices was {rolling_median} "
        f"with {high_count} of {config.VIDEO_BLUR_WINDOW_SIZE} slices above the threshold {threshold}."
    )


def _source_group_from_row(row: RuntimeResultRow) -> str:
    """Return the rule state grouping key for one detector row."""
    return str(row.get("source_group") or row.get("source_name", ""))


def _coerce_float(value: object, default: float) -> float:
    """Coerce a payload value to ``float`` and fall back safely on malformed data."""
    if value is None:
        return default
    try:
        if isinstance(value, (int, float, str)):
            return float(value)
        return default
    except (TypeError, ValueError):
        return default


def _source_name_from_row(row: RuntimeResultRow) -> str:
    """Return a human-readable source label from one detector row."""
    return str(row.get("source_name", ""))


def _optional_str(value: object) -> str | None:
    """Return one optional string field or ``None`` when it is blank-like."""
    if value in (None, ""):
        return None
    return str(value)


def _coerce_runtime_rule_row(
    row: RuleRowLike,
    *,
    detector_id: str,
) -> RuntimeResultRow:
    """Normalize one rule input row into the typed runtime row contract.

    Production callers increasingly pass ``RuntimeResultRow`` directly, but the
    public helpers still accept dict-like rows so tests and compatibility call
    sites stay simple.
    """
    if isinstance(row, RuntimeResultRow):
        return row
    runtime_row = RuntimeResultRow.from_mapping(row)
    if runtime_row is not None:
        return runtime_row
    return RuntimeResultRow(
        analyzer=str(row.get("analyzer", detector_id)),
        source_type=str(row.get("source_type", "video")),
        source_group=_optional_str(row.get("source_group")),
        source_name=str(row.get("source_name", "")),
        window_index=_maybe_int(row.get("window_index")),
        window_start_sec=_maybe_float(row.get("window_start_sec")),
        window_duration_sec=_maybe_float(row.get("window_duration_sec")),
        timestamp_utc=str(row.get("timestamp_utc", "")),
        processing_sec=_coerce_float(row.get("processing_sec"), 0.0),
        extra_fields={
            key: value
            for key, value in row.items()
            if key
            not in {
                "analyzer",
                "source_type",
                "source_group",
                "source_name",
                "window_index",
                "window_start_sec",
                "window_duration_sec",
                "timestamp_utc",
                "processing_sec",
            }
        },
    )


def _resolve_alert_rule(detector_id: str) -> AlertRule | None:
    """Return the registered runtime alert rule for one detector id."""
    return RULES_BY_DETECTOR.get(detector_id)


def _evaluate_rule(
    session_id: str,
    rule: AlertRule,
    row: RuntimeResultRow,
) -> bool:
    """Evaluate one resolved rule against one detector row."""
    if rule.evaluator is not None:
        return rule.evaluator(session_id, row)
    return rule.should_alert(row)


def _evaluate_video_black_rule(
    session_id: str,
    facts: BlackRuleFacts,
) -> BlackRuleEvaluationResult:
    """Return the full black-rule evaluation for one detector row."""
    key = _build_rule_key(session_id, "video_metrics", facts.source_group)
    summary = _update_black_window(
        session_id=session_id,
        source_group=facts.source_group,
        duration_sec=facts.duration_sec,
        black_ratio=facts.black_ratio,
    )
    black_active = _RULE_STATE.black_active.get(key, False)

    if black_active:
        if _has_black_rule_recovered(
            summary=summary,
            longest_black_sec=facts.longest_black_sec,
        ):
            _RULE_STATE.black_active[key] = False
            return BlackRuleEvaluationResult(
                decision=RuleDecision(
                    should_alert=False,
                    state="recovered",
                    reason="recovered",
                ),
                annotation=_black_rule_annotation(
                    summary=summary,
                    state="recovered",
                    reason="recovered",
                ),
            )
        return BlackRuleEvaluationResult(
            decision=RuleDecision(
                should_alert=False,
                state="black_active",
                reason="active",
            ),
            annotation=_black_rule_annotation(
                summary=summary,
                state="black_active",
                reason="active",
            ),
        )

    if _entered_by_continuous_black(facts.longest_black_sec):
        _RULE_STATE.black_active[key] = True
        return BlackRuleEvaluationResult(
            decision=RuleDecision(
                should_alert=True,
                state="entered_black",
                reason="continuous_black",
            ),
            annotation=_black_rule_annotation(
                summary=summary,
                state="entered_black",
                reason="continuous_black",
            ),
        )

    if _entered_by_rolling_black_ratio(summary):
        _RULE_STATE.black_active[key] = True
        return BlackRuleEvaluationResult(
            decision=RuleDecision(
                should_alert=True,
                state="entered_black",
                reason="rolling_ratio",
            ),
            annotation=_black_rule_annotation(
                summary=summary,
                state="entered_black",
                reason="rolling_ratio",
            ),
        )

    return BlackRuleEvaluationResult(
        decision=RuleDecision(
            should_alert=False,
            state="normal",
            reason="none",
        ),
        annotation=_black_rule_annotation(
            summary=summary,
            state="normal",
            reason="none",
        ),
    )


def _evaluate_video_blur_rule(
    session_id: str,
    facts: BlurRuleFacts,
) -> BlurRuleEvaluationResult:
    """Return the full blur-rule evaluation for one detector row."""
    key = _build_rule_key(session_id, "video_blur", facts.source_group)
    window, total_samples_seen = _update_blur_window(
        key,
        facts.blur_score,
        facts.motion_mean,
        facts.motion_p90,
    )
    summary = _summarize_blur_window(window)
    blur_active = _RULE_STATE.blur_active.get(key, False)

    if blur_active:
        if _has_blur_rule_recovered(summary=summary):
            _RULE_STATE.blur_active[key] = False
            return BlurRuleEvaluationResult(
                decision=RuleDecision(
                    should_alert=False,
                    state="recovered",
                ),
                annotation=_blur_rule_annotation(
                    summary=summary,
                    total_samples_seen=total_samples_seen,
                    state="recovered",
                ),
            )
        return BlurRuleEvaluationResult(
            decision=RuleDecision(
                should_alert=False,
                state="blur_active",
            ),
            annotation=_blur_rule_annotation(
                summary=summary,
                total_samples_seen=total_samples_seen,
                state="blur_active",
            ),
        )

    entry_decision = _decide_blur_entry(
        total_samples_seen=total_samples_seen,
        summary=summary,
    )
    if entry_decision.should_alert:
        _RULE_STATE.blur_active[key] = True

    return BlurRuleEvaluationResult(
        decision=RuleDecision(
            should_alert=entry_decision.should_alert,
            state=entry_decision.state,
        ),
        annotation=_blur_rule_annotation(
            summary=summary,
            total_samples_seen=total_samples_seen,
            state=entry_decision.state,
        ),
    )


def _log_rule_evaluation_failure(
    *,
    session_id: str,
    detector_id: str,
    row: RuntimeResultRow,
    rule: AlertRule,
) -> None:
    """Log one alert-rule evaluation failure with consistent context."""
    logger.exception(
        "Alert rule evaluation failed [%s]",
        format_log_context(
            session_id=session_id,
            current_item=_source_name_from_row(row),
            detector_id=detector_id,
            rule_id=rule.id,
        ),
    )


def _black_rule_facts_from_row(row: RuntimeResultRow) -> BlackRuleFacts:
    """Return typed black-rule inputs extracted from one detector row."""
    return BlackRuleFacts(
        source_group=_source_group_from_row(row),
        duration_sec=_coerce_float(row.get("duration_sec"), 0.0),
        black_ratio=_coerce_float(row.get("black_ratio"), 0.0),
        longest_black_sec=_coerce_float(row.get("longest_black_sec"), 0.0),
    )


def _blur_rule_facts_from_row(row: RuntimeResultRow) -> BlurRuleFacts:
    """Return typed blur-rule inputs extracted from one detector row."""
    return BlurRuleFacts(
        source_group=_source_group_from_row(row),
        blur_score=_coerce_float(row.get("blur_score"), 0.0),
        motion_mean=_coerce_float(row.get("motion_mean"), 0.0),
        motion_p90=_coerce_float(row.get("motion_p90"), 0.0),
    )


def _build_alert_event(
    session_id: str,
    detector_id: str,
    rule: AlertRule,
    row: RuntimeResultRow,
) -> AlertEvent:
    """Build one alert event from a rule definition and annotated row."""
    return AlertEvent(
        session_id=session_id,
        timestamp_utc=str(row["timestamp_utc"]),
        detector_id=detector_id,
        title=rule.title,
        message=rule.message_builder(row),
        severity=rule.severity,
        source_name=str(row["source_name"]),
        window_index=_maybe_int(row.get("window_index")),
        window_start_sec=_maybe_float(row.get("window_start_sec")),
    )


def _build_rule_key(
    session_id: str,
    detector_id: str,
    source_group: str,
) -> RuleStateKey:
    """Return the compound key used for per-session rolling rule state."""
    return (session_id, detector_id, source_group)


def _black_rule_annotation(
    *,
    summary: BlackWindowSummary,
    state: str,
    reason: str,
) -> RuleRowAnnotation:
    """Return black-rule export metadata detached from the rule decision itself."""
    return RuleRowAnnotation(
        metrics=_black_window_metrics_payload(summary),
        state_fields={
            "black_rule_reason": reason,
            "black_rule_state": state,
        },
    )


def _blur_rule_annotation(
    *,
    summary: BlurWindowSummary,
    total_samples_seen: int,
    state: str,
) -> RuleRowAnnotation:
    """Return blur-rule export metadata detached from the rule decision itself."""
    return RuleRowAnnotation(
        metrics=_blur_window_metrics_payload(summary, total_samples_seen),
        state_fields={"blur_rule_state": state},
    )


def _apply_rule_annotation(
    row: RuntimeResultRow,
    annotation: RuleRowAnnotation,
) -> None:
    """Apply one prepared rule annotation payload back onto a detector row."""
    row.update(annotation.metrics)
    row.update(annotation.state_fields)


def _entered_by_continuous_black(longest_black_sec: float) -> bool:
    """Return whether continuous black duration alone should trigger entry."""
    return longest_black_sec >= config.VIDEO_BLACK_ALERT_DURATION_SEC


def _entered_by_rolling_black_ratio(summary: BlackWindowSummary) -> bool:
    """Return whether rolling black-ratio state should trigger entry."""
    return (
        summary.observed_window_sec >= config.VIDEO_BLACK_SAMPLE_WINDOW_SEC
        and summary.rolling_ratio >= config.VIDEO_BLACK_SAMPLE_RATIO_THRESHOLD
    )


def _has_black_rule_recovered(
    *,
    summary: BlackWindowSummary,
    longest_black_sec: float,
) -> bool:
    """Return whether the black-screen rule has enough recovery evidence."""
    return (
        summary.observed_window_sec >= config.VIDEO_BLACK_SAMPLE_WINDOW_SEC
        and summary.rolling_ratio <= config.VIDEO_BLACK_RECOVERY_RATIO_THRESHOLD
        and longest_black_sec < config.VIDEO_BLACK_ALERT_DURATION_SEC
    )


def _black_window_metrics_payload(summary: BlackWindowSummary) -> dict[str, object]:
    """Return the black-rule rolling metrics export payload."""
    return {
        "rolling_black_ratio": round(summary.rolling_ratio, 3),
        "rolling_window_sec": round(summary.observed_window_sec, 3),
        "black_recovery_ratio_threshold": config.VIDEO_BLACK_RECOVERY_RATIO_THRESHOLD,
    }


def _blur_window_metrics_payload(
    summary: BlurWindowSummary,
    total_samples_seen: int,
) -> dict[str, object]:
    """Return the blur-rule rolling metrics export payload."""
    return {
        "rolling_blur_scores": [round(score, 3) for score in summary.scores],
        "rolling_blur_median": round(summary.median_score, 3),
        "rolling_blur_high_count": summary.high_count,
        "rolling_motion_means": [round(score, 3) for score in summary.motion_means],
        "rolling_motion_median": round(summary.motion_median, 3),
        "rolling_motion_peak": round(summary.motion_peak, 3),
        "blur_total_samples_seen": total_samples_seen,
        "blur_recovery_threshold": config.VIDEO_BLUR_RECOVERY_THRESHOLD,
    }


def _summarize_blur_window(window: deque[BlurSample]) -> BlurWindowSummary:
    """Return blur and motion summary facts for the current rolling window."""
    scores = tuple(sample.blur_score for sample in window)
    motion_means = tuple(sample.motion_mean for sample in window)
    motion_p90s = tuple(sample.motion_p90 for sample in window)
    median_score = median(scores) if scores else 0.0
    motion_median = median(motion_means) if motion_means else 0.0
    motion_peak = max(motion_p90s, default=0.0)
    return BlurWindowSummary(
        scores=scores,
        motion_means=motion_means,
        motion_p90s=motion_p90s,
        median_score=median_score,
        high_count=_count_blur_scores_above_threshold(scores),
        motion_median=motion_median,
        motion_peak=motion_peak,
        window_is_full=len(scores) >= config.VIDEO_BLUR_WINDOW_SIZE,
    )


def _count_blur_scores_above_threshold(scores: tuple[float, ...]) -> int:
    """Return the number of scores in the current window above the blur threshold."""
    threshold = config.VIDEO_BLUR_ALERT_THRESHOLD
    return sum(score >= threshold for score in scores)


def _decide_blur_entry(
    *,
    total_samples_seen: int,
    summary: BlurWindowSummary,
) -> BlurEntryDecision:
    """Return the blur-rule entry decision for the current rolling window."""
    if not _blur_window_is_ready(summary, total_samples_seen):
        return BlurEntryDecision(should_alert=False, state="not_ready")

    if _has_high_motion(summary):
        return BlurEntryDecision(should_alert=False, state="motion_suppressed")

    if _requires_stricter_blur_entry(summary):
        ambiguous_entry = _meets_ambiguous_motion_blur_entry(summary)
        return BlurEntryDecision(
            should_alert=ambiguous_entry,
            state="entered_blur" if ambiguous_entry else "ambiguous_motion",
        )

    standard_entry = _meets_standard_blur_entry(summary)
    return BlurEntryDecision(
        should_alert=standard_entry,
        state="entered_blur" if standard_entry else "normal",
    )


def _blur_window_is_ready(
    summary: BlurWindowSummary,
    total_samples_seen: int,
) -> bool:
    """Return whether blur entry has enough history to trust the current window."""
    return (
        summary.window_is_full
        and total_samples_seen >= config.VIDEO_BLUR_MIN_TOTAL_SAMPLES
    )


def _has_high_motion(summary: BlurWindowSummary) -> bool:
    """Return whether recent motion is strong enough to suppress blur entry."""
    return (
        summary.motion_median >= config.VIDEO_BLUR_MOTION_GUARD_MEDIAN_THRESHOLD
        or summary.motion_peak >= config.VIDEO_BLUR_MOTION_GUARD_PEAK_THRESHOLD
    )


def _requires_stricter_blur_entry(summary: BlurWindowSummary) -> bool:
    """Return whether moderate motion should require stronger blur evidence."""
    return (
        summary.motion_median >= config.VIDEO_BLUR_MOTION_AMBIGUOUS_MEDIAN_THRESHOLD
    )


def _meets_standard_blur_entry(summary: BlurWindowSummary) -> bool:
    """Return whether the default blur-entry thresholds are satisfied."""
    return (
        summary.median_score >= config.VIDEO_BLUR_ALERT_THRESHOLD
        and summary.high_count >= config.VIDEO_BLUR_MIN_CONSECUTIVE_WINDOWS
    )


def _meets_ambiguous_motion_blur_entry(summary: BlurWindowSummary) -> bool:
    """Return whether the stricter ambiguous-motion blur thresholds are satisfied."""
    return (
        summary.median_score >= config.VIDEO_BLUR_MOTION_AMBIGUOUS_ALERT_THRESHOLD
        and summary.high_count >= config.VIDEO_BLUR_WINDOW_SIZE
    )


def _has_blur_rule_recovered(
    *,
    summary: BlurWindowSummary,
) -> bool:
    """Return whether the blur rule has enough recovery evidence."""
    return (
        summary.window_is_full
        and summary.median_score <= config.VIDEO_BLUR_RECOVERY_THRESHOLD
    )


def _clear_black_rule_state(session_id: str) -> None:
    """Remove all black-rule rolling state entries for one session."""
    stale_keys = [key for key in _RULE_STATE.black_windows if key[0] == session_id]
    for key in stale_keys:
        _RULE_STATE.black_windows.pop(key, None)
        _RULE_STATE.black_active.pop(key, None)


def _clear_blur_rule_state(session_id: str) -> None:
    """Remove all blur-rule rolling state entries for one session."""
    stale_keys = [key for key in _RULE_STATE.blur_windows if key[0] == session_id]
    for key in stale_keys:
        _RULE_STATE.blur_windows.pop(key, None)
        _RULE_STATE.blur_active.pop(key, None)
        _RULE_STATE.blur_sample_counts.pop(key, None)


def _update_blur_window(
    key: RuleStateKey,
    blur_score: float,
    motion_mean: float,
    motion_p90: float,
) -> tuple[deque[BlurSample], int]:
    """Append one blur sample and return the updated rolling window and sample count."""
    window = _RULE_STATE.blur_windows[key]
    _RULE_STATE.blur_sample_counts[key] += 1
    window.append(
        BlurSample(
            blur_score=_clamp_unit_interval(blur_score),
            motion_mean=_clamp_unit_interval(motion_mean),
            motion_p90=_clamp_unit_interval(motion_p90),
        )
    )
    _trim_blur_window(window, config.VIDEO_BLUR_WINDOW_SIZE)
    return (window, _RULE_STATE.blur_sample_counts[key])


def _update_black_window(
    session_id: str,
    source_group: str,
    duration_sec: float,
    black_ratio: float,
) -> BlackWindowSummary:
    """Append one black sample and return the updated rolling window summary."""
    key = _build_rule_key(session_id, "video_metrics", source_group)
    window = _RULE_STATE.black_windows[key]
    sample_duration = max(0.001, min(duration_sec or 1.0, config.VIDEO_BLACK_SAMPLE_WINDOW_SEC))
    window.append(
        BlackSample(
            duration_sec=sample_duration,
            black_ratio=_clamp_unit_interval(black_ratio),
        )
    )
    _trim_black_window(window, config.VIDEO_BLACK_SAMPLE_WINDOW_SEC)
    total_duration = sum(sample.duration_sec for sample in window)
    return BlackWindowSummary(
        rolling_ratio=_weighted_black_ratio(window),
        observed_window_sec=total_duration,
    )


def _trim_black_window(window: deque[BlackSample], max_duration_sec: float) -> None:
    """Trim the oldest samples so the rolling window duration stays bounded."""
    total_duration = sum(sample.duration_sec for sample in window)
    while window and total_duration > max_duration_sec:
        overflow = total_duration - max_duration_sec
        head = window[0]
        if head.duration_sec <= overflow + 1e-9:
            total_duration -= head.duration_sec
            window.popleft()
            continue

        head.duration_sec -= overflow
        total_duration -= overflow


def _weighted_black_ratio(window: deque[BlackSample]) -> float:
    """Return the weighted black ratio across the current rolling window."""
    total_duration = sum(sample.duration_sec for sample in window)
    if total_duration <= 0:
        return 0.0
    return sum(sample.duration_sec * sample.black_ratio for sample in window) / total_duration


def _trim_blur_window(window: deque[BlurSample], max_items: int) -> None:
    """Trim the oldest blur samples so the rolling window size stays bounded."""
    while len(window) > max_items:
        window.popleft()


def _clamp_unit_interval(value: float) -> float:
    """Clamp numeric detector metrics into the normalized ``0..1`` range."""
    return max(0.0, min(1.0, value))


def _maybe_int(value: object) -> int | None:
    """Return an integer value when the payload contains one."""
    if value is None:
        return None
    try:
        if isinstance(value, int):
            return value
        if isinstance(value, (float, str)):
            return int(value)
        return None
    except (TypeError, ValueError):
        return None


def _maybe_float(value: object) -> float | None:
    """Return a float value when the payload contains one."""
    if value is None:
        return None
    try:
        if isinstance(value, (int, float, str)):
            return float(value)
        return None
    except (TypeError, ValueError):
        return None
