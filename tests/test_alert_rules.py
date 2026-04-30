"""Contract-level tests for alert-rule registration and cross-rule behavior.

The rule-family state-machine coverage lives in the sibling black and blur
files. This module keeps the smaller seams that should stay detector-agnostic:
metadata, failure wrapping, malformed payload tolerance, and cross-detector
isolation.
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
    """Rule failures should be logged and surfaced as rule-aware ValueErrors."""
    logged: list[tuple[str, tuple[object, ...]]] = []

    def broken_should_alert(row: dict[str, object]) -> bool:
        """Simulate a rule implementation that fails inside `should_alert`."""
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
