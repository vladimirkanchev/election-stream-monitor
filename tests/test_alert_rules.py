"""Production alert-rule tests that are shared across black and blur detectors.

This file covers rule discovery, failure wrapping, and row-annotation behavior
that should stay stable regardless of the detector-specific policy details.
"""

import pytest

import alert_rules
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
