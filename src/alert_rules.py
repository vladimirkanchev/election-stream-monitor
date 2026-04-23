"""Small rule layer for converting analyzer results into alert events."""

from collections import defaultdict, deque
from dataclasses import dataclass
from statistics import median
from typing import Callable

from analyzer_contract import AlertRuleCatalogEntry, DetectorOrigin, DetectorStatus
import config
from logger import format_log_context, get_logger
from session_models import AlertEvent, EventSeverity


Predicate = Callable[[dict[str, object]], bool]
MessageBuilder = Callable[[dict[str, object]], str]
RuleStateKey = tuple[str, str, str]
logger = get_logger(__name__)


@dataclass
class BlackSample:
    """One recent black-screen sample used for rolling-window evaluation."""

    duration_sec: float
    black_ratio: float


@dataclass(frozen=True)
class BlurSample:
    """One recent blur sample used for rolling-window evaluation."""

    blur_score: float


@dataclass(frozen=True)
class AlertRule:
    """Readable rule definition for one detector's alert behavior."""

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


_video_black_windows: dict[RuleStateKey, deque[BlackSample]] = defaultdict(deque)
_video_black_active: dict[RuleStateKey, bool] = {}
_video_blur_windows: dict[RuleStateKey, deque[BlurSample]] = defaultdict(deque)
_video_blur_active: dict[RuleStateKey, bool] = {}


VIDEO_BLACK_RULE = AlertRule(
    id="video_metrics.default_rule",
    detector_id="video_metrics",
    display_name="Default Black Screen Rule",
    description="Built-in black-screen alert policy with rolling state and recovery hysteresis.",
    title="Black screen detected",
    should_alert=lambda row: bool(row.get("black_detected")),
    message_builder=lambda row: build_video_black_message(row),
)

VIDEO_BLUR_RULE = AlertRule(
    id="video_blur.default_rule",
    detector_id="video_blur",
    display_name="Default Blur Rule",
    description="Built-in rolling blur alert policy with entry, recovery, and no-repeat behavior.",
    title="Blur warning",
    should_alert=lambda row: bool(row.get("blur_detected")),
    message_builder=lambda row: build_video_blur_message(row),
    status="optional",
)

REGISTERED_ALERT_RULES = (VIDEO_BLACK_RULE, VIDEO_BLUR_RULE)
RULES_BY_DETECTOR = {
    rule.detector_id: rule
    for rule in REGISTERED_ALERT_RULES
}
RULES_BY_ID = {rule.id: rule for rule in REGISTERED_ALERT_RULES}


def list_available_alert_rules() -> list[AlertRuleCatalogEntry]:
    """Return lightweight metadata for built-in alert rules.

    This prepares the rule layer for future plugin-style override and bundled
    default-rule linking without introducing dynamic rule loading yet.
    """
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
    row: dict[str, object],
) -> list[AlertEvent]:
    """Evaluate the configured alert rule for one analyzer result row."""
    rule = RULES_BY_DETECTOR.get(detector_id)
    if rule is None:
        return []

    row_for_rules = dict(row)
    try:
        if not _should_emit_alert(session_id, detector_id, rule, row_for_rules):
            return []

        return [_build_alert_event(session_id, detector_id, rule, row_for_rules)]
    except Exception as error:
        logger.exception(
            "Alert rule evaluation failed [%s]",
            format_log_context(
                session_id=session_id,
                current_item=_source_name_from_row(row_for_rules),
                detector_id=detector_id,
                rule_id=rule.id,
            ),
        )
        raise ValueError(f"Alert rule evaluation failed for {rule.id}") from error


def reset_session_rule_state(session_id: str) -> None:
    """Clear any rolling-rule state kept for one session."""
    for windows, active_states in _rolling_rule_state():
        _clear_session_state(
            session_id,
            windows=windows,
            active_states=active_states,
        )


def should_alert_video_black(session_id: str, row: dict[str, object]) -> bool:
    """Apply a rolling black-screen rule with one alert on entry and hysteresis.

    Entry:
        - immediate when a continuous black interval is long enough
        - or when the recent weighted black ratio stays high enough

    While active:
        - do not repeat alerts on every following black slice

    Recovery:
        - only recover after the recent rolling black ratio clearly drops
    """
    source_group = _source_group_from_row(row)
    key = _build_rule_key(session_id, "video_metrics", source_group)
    longest_black_sec = _coerce_float(row.get("longest_black_sec"), 0.0)

    rolling_ratio, observed_window_sec = update_video_black_window(
        session_id=session_id,
        source_group=source_group,
        duration_sec=_coerce_float(row.get("duration_sec"), 0.0),
        black_ratio=_coerce_float(row.get("black_ratio"), 0.0),
    )
    _record_black_window_metrics(row, rolling_ratio, observed_window_sec)

    entered_by_continuous_black = _entered_by_continuous_black(longest_black_sec)
    entered_by_rolling_ratio = _entered_by_rolling_black_ratio(
        rolling_ratio, observed_window_sec
    )
    black_active = _video_black_active.get(key, False)

    if black_active:
        if _has_black_rule_recovered(
            rolling_ratio=rolling_ratio,
            observed_window_sec=observed_window_sec,
            longest_black_sec=longest_black_sec,
        ):
            _video_black_active[key] = False
            _set_black_rule_state(row, reason="recovered", state="recovered")
        else:
            _set_black_rule_state(row, reason="active", state="black_active")
        return False

    if entered_by_continuous_black:
        _video_black_active[key] = True
        _set_black_rule_state(row, reason="continuous_black", state="entered_black")
        return True

    if entered_by_rolling_ratio:
        _video_black_active[key] = True
        _set_black_rule_state(row, reason="rolling_ratio", state="entered_black")
        return True

    _set_black_rule_state(row, reason="none", state="normal")
    return False


def build_video_black_message(row: dict[str, object]) -> str:
    """Build a readable message for the video black-screen rule."""
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


def should_alert_video_blur(session_id: str, row: dict[str, object]) -> bool:
    """Apply a rolling blur rule with one alert on entry and recovery hysteresis."""
    key = _build_rule_key(session_id, "video_blur", _source_group_from_row(row))
    scores = _update_blur_window(
        key,
        _coerce_float(row.get("blur_score"), 0.0),
    )
    median_score = median(scores) if scores else 0.0
    high_count = _count_blur_scores_above_threshold(scores)
    window_is_full = _is_blur_window_full(scores)
    entered_blurry_state = _entered_blurry_state(
        window_is_full=window_is_full,
        median_score=median_score,
        high_count=high_count,
    )
    blur_active = _video_blur_active.get(key, False)

    _record_blur_window_metrics(row, scores, median_score, high_count)

    if blur_active:
        if _has_blur_rule_recovered(
            window_is_full=window_is_full,
            median_score=median_score,
        ):
            _video_blur_active[key] = False
            _set_blur_rule_state(row, "recovered")
        else:
            _set_blur_rule_state(row, "blur_active")
        return False

    if entered_blurry_state:
        _video_blur_active[key] = True
        _set_blur_rule_state(row, "entered_blur")
        return True

    _set_blur_rule_state(row, "normal")
    return False


def build_video_blur_message(row: dict[str, object]) -> str:
    """Build a readable message for the rolling blur rule."""
    source_name = row.get("source_name", "Video")
    rolling_median = row.get("rolling_blur_median", row.get("blur_score", 0.0))
    threshold = row.get("threshold_used", config.VIDEO_BLUR_ALERT_THRESHOLD)
    high_count = row.get("rolling_blur_high_count", 0)

    return (
        f"{source_name} entered a blurry state. "
        f"Median blur across the last {config.VIDEO_BLUR_WINDOW_SIZE} slices was {rolling_median} "
        f"with {high_count} of {config.VIDEO_BLUR_WINDOW_SIZE} slices above the threshold {threshold}."
    )


def _source_group_from_row(row: dict[str, object]) -> str:
    return str(row.get("source_group") or row.get("source_name", ""))


def _coerce_float(value: object, default: float) -> float:
    try:
        return float(value or default)
    except (TypeError, ValueError):
        return default


def _source_name_from_row(row: dict[str, object]) -> str:
    return str(row.get("source_name", ""))


def _should_emit_alert(
    session_id: str,
    detector_id: str,
    rule: AlertRule,
    row: dict[str, object],
) -> bool:
    evaluator = _rule_evaluators().get(detector_id)
    if evaluator is not None:
        return evaluator(session_id, row)
    return rule.should_alert(row)


def _rule_evaluators() -> dict[str, Callable[[str, dict[str, object]], bool]]:
    return {
        "video_metrics": should_alert_video_black,
        "video_blur": should_alert_video_blur,
    }


def _rolling_rule_state() -> tuple[
    tuple[dict[RuleStateKey, deque[BlackSample]], dict[RuleStateKey, bool]],
    tuple[dict[RuleStateKey, deque[BlurSample]], dict[RuleStateKey, bool]],
]:
    return (
        (_video_black_windows, _video_black_active),
        (_video_blur_windows, _video_blur_active),
    )


def _build_alert_event(
    session_id: str,
    detector_id: str,
    rule: AlertRule,
    row: dict[str, object],
) -> AlertEvent:
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
    return (session_id, detector_id, source_group)


def _set_black_rule_state(
    row: dict[str, object],
    *,
    reason: str,
    state: str,
) -> None:
    row["black_rule_reason"] = reason
    row["black_rule_state"] = state


def _set_blur_rule_state(row: dict[str, object], state: str) -> None:
    row["blur_rule_state"] = state


def _record_black_window_metrics(
    row: dict[str, object],
    rolling_ratio: float,
    observed_window_sec: float,
) -> None:
    row["rolling_black_ratio"] = round(rolling_ratio, 3)
    row["rolling_window_sec"] = round(observed_window_sec, 3)
    row["black_recovery_ratio_threshold"] = config.VIDEO_BLACK_RECOVERY_RATIO_THRESHOLD


def _entered_by_continuous_black(longest_black_sec: float) -> bool:
    return longest_black_sec >= config.VIDEO_BLACK_ALERT_DURATION_SEC


def _entered_by_rolling_black_ratio(
    rolling_ratio: float,
    observed_window_sec: float,
) -> bool:
    return (
        observed_window_sec >= config.VIDEO_BLACK_SAMPLE_WINDOW_SEC
        and rolling_ratio >= config.VIDEO_BLACK_SAMPLE_RATIO_THRESHOLD
    )


def _has_black_rule_recovered(
    *,
    rolling_ratio: float,
    observed_window_sec: float,
    longest_black_sec: float,
) -> bool:
    return (
        observed_window_sec >= config.VIDEO_BLACK_SAMPLE_WINDOW_SEC
        and rolling_ratio <= config.VIDEO_BLACK_RECOVERY_RATIO_THRESHOLD
        and longest_black_sec < config.VIDEO_BLACK_ALERT_DURATION_SEC
    )


def _record_blur_window_metrics(
    row: dict[str, object],
    scores: list[float],
    median_score: float,
    high_count: int,
) -> None:
    row["rolling_blur_scores"] = [round(score, 3) for score in scores]
    row["rolling_blur_median"] = round(median_score, 3)
    row["rolling_blur_high_count"] = high_count
    row["blur_recovery_threshold"] = config.VIDEO_BLUR_RECOVERY_THRESHOLD


def _is_blur_window_full(scores: list[float]) -> bool:
    return len(scores) >= config.VIDEO_BLUR_WINDOW_SIZE


def _count_blur_scores_above_threshold(scores: list[float]) -> int:
    threshold = config.VIDEO_BLUR_ALERT_THRESHOLD
    return sum(score >= threshold for score in scores)


def _entered_blurry_state(
    *,
    window_is_full: bool,
    median_score: float,
    high_count: int,
) -> bool:
    return (
        window_is_full
        and median_score >= config.VIDEO_BLUR_ALERT_THRESHOLD
        and high_count >= config.VIDEO_BLUR_MIN_CONSECUTIVE_WINDOWS
    )


def _has_blur_rule_recovered(
    *,
    window_is_full: bool,
    median_score: float,
) -> bool:
    return (
        window_is_full
        and median_score <= config.VIDEO_BLUR_RECOVERY_THRESHOLD
    )


def _clear_session_state(
    session_id: str,
    windows: dict[RuleStateKey, deque[object]],
    active_states: dict[RuleStateKey, bool],
) -> None:
    stale_keys = [key for key in windows if key[0] == session_id]
    for key in stale_keys:
        windows.pop(key, None)
        active_states.pop(key, None)


def _update_blur_window(key: RuleStateKey, blur_score: float) -> list[float]:
    window = _video_blur_windows[key]
    window.append(
        BlurSample(blur_score=max(0.0, min(1.0, blur_score))),
    )
    _trim_blur_window(window, config.VIDEO_BLUR_WINDOW_SIZE)
    return [sample.blur_score for sample in window]


def update_video_black_window(
    session_id: str,
    source_group: str,
    duration_sec: float,
    black_ratio: float,
) -> tuple[float, float]:
    """Update the recent black-sample window and return weighted ratio."""
    key = _build_rule_key(session_id, "video_metrics", source_group)
    window = _video_black_windows[key]
    sample_duration = max(0.001, min(duration_sec or 1.0, config.VIDEO_BLACK_SAMPLE_WINDOW_SEC))
    window.append(
        BlackSample(
            duration_sec=sample_duration,
            black_ratio=max(0.0, min(1.0, black_ratio)),
        )
    )
    _trim_black_window(window, config.VIDEO_BLACK_SAMPLE_WINDOW_SEC)
    total_duration = sum(sample.duration_sec for sample in window)
    return _weighted_black_ratio(window), total_duration


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


def _maybe_int(value: object) -> int | None:
    """Return an integer value when the payload contains one."""
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _maybe_float(value: object) -> float | None:
    """Return a float value when the payload contains one."""
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
