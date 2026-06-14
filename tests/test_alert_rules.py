"""Production alert-rule tests that are shared across black and blur detectors.

This file covers rule discovery, failure wrapping, and row-annotation behavior
that should stay stable regardless of the detector-specific policy details.
"""

import pytest

import alert_rules
from analyzer_contract import RuleEvaluationContext, RuntimeResultRow
from alert_rules import evaluate_alerts, list_available_alert_rules, reset_session_rule_state
from tests.alert_rules_test_support import black_row, blur_row


def test_list_available_alert_rules_returns_builtin_rule_metadata() -> None:
    """Built-in alert rules should expose lightweight metadata with stable ids."""
    rules = list_available_alert_rules()

    assert rules[0]["id"] == "video_metrics.default_rule"
    assert rules[0]["detector_id"] == "video_metrics"
    assert rules[0]["origin"] == "built_in"
    assert rules[1]["id"] == "video_blur.default_rule"
    assert rules[1]["status"] == "optional"


def test_list_available_alert_rules_keeps_stable_catalog_shape() -> None:
    """Rule discovery should keep the frontend-facing metadata contract stable."""
    rules = list_available_alert_rules()

    assert rules == [
        {
            "id": "video_metrics.default_rule",
            "detector_id": "video_metrics",
            "display_name": "Default Black Screen Rule",
            "description": alert_rules.VIDEO_BLACK_RULE.description,
            "origin": "built_in",
            "status": "core",
        },
        {
            "id": "video_blur.default_rule",
            "detector_id": "video_blur",
            "display_name": "Default Blur Rule",
            "description": alert_rules.VIDEO_BLUR_RULE.description,
            "origin": "built_in",
            "status": "optional",
        },
    ]


def test_evaluate_alerts_wraps_rule_failures_with_rule_identity(monkeypatch) -> None:
    """Rule failures should be logged and surfaced as rule-aware ``ValueError`` values."""
    logged: list[tuple[str, tuple[object, ...]]] = []

    def broken_should_alert(row: dict[str, object]) -> bool:
        """Simulate a rule implementation that fails inside ``should_alert``."""
        _ = row
        raise RuntimeError("broken rule")

    broken_rule = alert_rules.AlertRule(
        id="video_blur.default_rule",
        detector_id="video_blur",
        display_name="Broken Rule",
        description="Fails on purpose",
        title="Broken",
        should_alert=broken_should_alert,
        message_builder=lambda row: str(row),
    )
    monkeypatch.setitem(alert_rules.RULES_BY_DETECTOR, "video_blur", broken_rule)
    monkeypatch.setattr(alert_rules, "should_alert_video_blur", lambda *_args, **_kwargs: broken_should_alert({}))
    monkeypatch.setattr(
        alert_rules.logger,
        "exception",
        lambda message, *args: logged.append((message, args)),
    )

    with pytest.raises(ValueError, match="video_blur.default_rule"):
        evaluate_alerts(
            session_id="session-broken-rule",
            detector_id="video_blur",
            row={
                "timestamp_utc": "2026-03-31 10:00:00",
                "source_name": "segment_001.ts",
                "blur_detected": True,
            },
        )

    assert logged
    message, args = logged[0]
    assert message == "Alert rule evaluation failed [%s]"
    assert args[0] == (
        "session_id='session-broken-rule' "
        "current_item='segment_001.ts' "
        "detector_id='video_blur' "
        "rule_id='video_blur.default_rule'"
    )


def test_video_black_rule_ignores_malformed_numeric_payload_fields_safely() -> None:
    """Black rule should tolerate malformed numeric payloads without alerting."""
    reset_session_rule_state("session-black-malformed")

    alerts = evaluate_alerts(
        session_id="session-black-malformed",
        detector_id="video_metrics",
        row=black_row(
            black_ratio="bad",
            longest_black_sec=None,
        ),
    )

    assert alerts == []


def test_video_blur_rule_ignores_malformed_numeric_payload_fields_safely() -> None:
    """Blur rule should tolerate malformed numeric payloads without alerting."""
    reset_session_rule_state("session-blur-malformed")

    alerts = evaluate_alerts(
        session_id="session-blur-malformed",
        detector_id="video_blur",
        row=blur_row(
            blur_score="bad",
            threshold_used=None,
        ),
    )

    assert alerts == []


def test_evaluate_alerts_keeps_detector_rules_isolated() -> None:
    """One detector's row shape should not accidentally trigger another detector's rule path."""
    reset_session_rule_state("session-detector-isolation")

    black_only = evaluate_alerts(
        session_id="session-detector-isolation",
        detector_id="video_blur",
        row=black_row(),
    )
    blur_only = evaluate_alerts(
        session_id="session-detector-isolation",
        detector_id="video_metrics",
        row=blur_row(),
    )

    assert black_only == []
    assert blur_only == []


def test_evaluate_alerts_accepts_runtime_rows_without_mutating_caller() -> None:
    """Rule evaluation should consume normalized runtime rows without mutating the caller object."""
    reset_session_rule_state("session-runtime-row")
    row = RuntimeResultRow(
        analyzer="video_metrics",
        source_type="video",
        source_group="playlist-runtime-row",
        source_name="segment_001.ts",
        window_index=None,
        window_start_sec=None,
        window_duration_sec=None,
        timestamp_utc="2026-03-31 10:00:00",
        processing_sec=0.01,
        extra_fields={
            "black_detected": True,
            "duration_sec": 1.0,
            "black_ratio": 0.25,
            "longest_black_sec": 1.2,
        },
    )
    original = row.to_dict()

    alerts = evaluate_alerts(
        session_id="session-runtime-row",
        detector_id="video_metrics",
        row=row,
    )

    assert len(alerts) == 1
    assert alerts[0].title == "Black screen detected"
    assert "entered a black-screen state" in alerts[0].message
    assert row.to_dict() == original


def test_video_black_rule_records_state_metadata_on_alerting_rows() -> None:
    """Black rule evaluation should annotate the row with state and rolling metadata."""
    reset_session_rule_state("session-black-metadata")
    row = black_row(
        black_ratio=0.95,
        longest_black_sec=1.2,
    )

    should_alert = alert_rules.should_alert_video_black(
        "session-black-metadata",
        row,
    )

    assert should_alert is True
    assert row["black_rule_reason"] == "continuous_black"
    assert row["black_rule_state"] == "entered_black"
    assert row["black_recovery_ratio_threshold"] == alert_rules.config.VIDEO_BLACK_RECOVERY_RATIO_THRESHOLD
    assert row["rolling_black_ratio"] == 0.95
    assert row["rolling_window_sec"] == 1.0


def test_video_blur_rule_records_state_metadata_on_non_ready_rows() -> None:
    """Blur rule evaluation should annotate row state even before the window is ready."""
    reset_session_rule_state("session-blur-metadata")
    row = blur_row(
        blur_score=0.91,
        motion_mean=0.0,
        motion_p90=0.0,
    )

    should_alert = alert_rules.should_alert_video_blur(
        "session-blur-metadata",
        row,
    )

    assert should_alert is False
    assert row["blur_rule_state"] == "not_ready"
    assert row["blur_recovery_threshold"] == alert_rules.config.VIDEO_BLUR_RECOVERY_THRESHOLD
    assert row["rolling_blur_scores"] == [0.91]
    assert row["rolling_blur_high_count"] == 1
    assert row["rolling_motion_means"] == [0.0]


def test_video_black_rule_records_recovered_state_metadata() -> None:
    """Black rule recovery should stay quiet while exporting the recovered rule state."""
    reset_session_rule_state("session-black-recovered")

    entered = black_row(
        source_group="playlist-black-recovered",
        source_name="segment_001.ts",
        black_ratio=0.95,
        longest_black_sec=1.2,
    )
    assert alert_rules.should_alert_video_black("session-black-recovered", entered) is True

    for index in range(2, 5):
        recovery_row = black_row(
            timestamp_utc=f"2026-03-31 10:00:0{index}",
            source_group="playlist-black-recovered",
            source_name=f"segment_00{index}.ts",
            black_detected=False,
            black_ratio=0.0,
            longest_black_sec=0.0,
        )

        should_alert = alert_rules.should_alert_video_black(
            "session-black-recovered",
            recovery_row,
        )

    assert should_alert is False
    assert recovery_row["black_rule_state"] == "recovered"
    assert recovery_row["black_rule_reason"] == "recovered"
    assert recovery_row["black_recovery_ratio_threshold"] == alert_rules.config.VIDEO_BLACK_RECOVERY_RATIO_THRESHOLD


def test_rule_evaluator_receives_small_typed_context() -> None:
    """Custom evaluators should receive one small typed rule-evaluation context."""
    observed: list[RuleEvaluationContext] = []

    rule = alert_rules.AlertRule(
        id="video_metrics.default_rule",
        detector_id="video_metrics",
        display_name="Context Rule",
        description="Captures evaluator context",
        title="Context",
        should_alert=lambda _row: False,
        message_builder=lambda row: str(row),
        evaluator=lambda context: observed.append(context) or False,
    )

    result = alert_rules._evaluate_rule(
        "session-context",
        rule,
        alert_rules._coerce_runtime_rule_row(black_row(), detector_id="video_metrics"),
    )

    assert result is False
    assert len(observed) == 1
    context = observed[0]
    assert context.session_id == "session-context"
    assert context.detector_id == "video_metrics"
    assert context.row.analyzer == "video_metrics"
