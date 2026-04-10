"""Tests for rule-based alert evaluation."""

import pytest

import alert_rules
from alert_rules import evaluate_alerts, list_available_alert_rules, reset_session_rule_state


def test_list_available_alert_rules_returns_builtin_rule_metadata() -> None:
    """Built-in alert rules should expose lightweight metadata with stable ids."""
    rules = list_available_alert_rules()

    assert rules[0]["id"] == "video_metrics.default_rule"
    assert rules[0]["detector_id"] == "video_metrics"
    assert rules[0]["origin"] == "built_in"
    assert rules[1]["id"] == "video_blur.default_rule"
    assert rules[1]["status"] == "optional"


def test_video_black_rule_raises_alert_for_long_black_interval() -> None:
    """Video black rule should raise once on entry via a long black interval."""
    reset_session_rule_state("session-1")
    alerts = evaluate_alerts(
        session_id="session-1",
        detector_id="video_metrics",
        row={
            "timestamp_utc": "2026-03-31 10:00:00",
            "source_name": "segment_001.ts",
            "black_detected": True,
            "black_ratio": 0.25,
            "longest_black_sec": 1.2,
        },
    )

    assert len(alerts) == 1
    assert alerts[0].title == "Black screen detected"
    assert "entered a black-screen state" in alerts[0].message
    assert "Longest black interval 1.2 sec" in alerts[0].message


def test_evaluate_alerts_wraps_rule_failures_with_rule_identity(monkeypatch) -> None:
    """Rule failures should be logged and surfaced as rule-aware ValueErrors."""
    logged: list[tuple[str, tuple[object, ...]]] = []

    def broken_should_alert(row: dict[str, object]) -> bool:
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


def test_video_black_rule_raises_alert_for_rolling_black_ratio() -> None:
    """Video black rule should trigger once on entry into sustained black ratio."""
    reset_session_rule_state("session-rolling")

    first = evaluate_alerts(
        session_id="session-rolling",
        detector_id="video_metrics",
        row={
            "timestamp_utc": "2026-03-31 10:00:00",
            "source_group": "playlist-a",
            "source_name": "segment_001.ts",
            "black_detected": True,
            "duration_sec": 1.0,
            "black_ratio": 0.9,
            "longest_black_sec": 0.4,
        },
    )
    second = evaluate_alerts(
        session_id="session-rolling",
        detector_id="video_metrics",
        row={
            "timestamp_utc": "2026-03-31 10:00:01",
            "source_group": "playlist-a",
            "source_name": "segment_002.ts",
            "black_detected": True,
            "duration_sec": 1.0,
            "black_ratio": 0.9,
            "longest_black_sec": 0.4,
        },
    )
    third = evaluate_alerts(
        session_id="session-rolling",
        detector_id="video_metrics",
        row={
            "timestamp_utc": "2026-03-31 10:00:02",
            "source_group": "playlist-a",
            "source_name": "segment_003.ts",
            "black_detected": True,
            "duration_sec": 1.0,
            "black_ratio": 0.9,
            "longest_black_sec": 0.4,
        },
    )

    assert first == []
    assert second == []
    assert len(third) == 1
    assert "entered a black-screen state" in third[0].message
    assert "Rolling black ratio across the last 3 sec was 0.9" in third[0].message


def test_video_black_rule_does_not_alert_before_rolling_window_is_full() -> None:
    """Black rule should wait until the rolling window is full before ratio alerts."""
    reset_session_rule_state("session-black-short")

    first = evaluate_alerts(
        session_id="session-black-short",
        detector_id="video_metrics",
        row={
            "timestamp_utc": "2026-03-31 10:00:00",
            "source_group": "playlist-short",
            "source_name": "segment_001.ts",
            "black_detected": True,
            "duration_sec": 1.0,
            "black_ratio": 0.95,
            "longest_black_sec": 0.4,
        },
    )
    second = evaluate_alerts(
        session_id="session-black-short",
        detector_id="video_metrics",
        row={
            "timestamp_utc": "2026-03-31 10:00:01",
            "source_group": "playlist-short",
            "source_name": "segment_002.ts",
            "black_detected": True,
            "duration_sec": 1.0,
            "black_ratio": 0.95,
            "longest_black_sec": 0.4,
        },
    )

    assert first == []
    assert second == []


def test_video_black_rule_does_not_repeat_until_recovery_then_alerts_again() -> None:
    """Black rule should alert once, recover, then alert again on a new black episode."""
    reset_session_rule_state("session-black-repeat")

    first_alert = evaluate_alerts(
        session_id="session-black-repeat",
        detector_id="video_metrics",
        row={
            "timestamp_utc": "2026-03-31 10:00:00",
            "source_group": "playlist-c",
            "source_name": "segment_001.ts",
            "black_detected": True,
            "duration_sec": 1.0,
            "black_ratio": 0.95,
            "longest_black_sec": 1.2,
        },
    )
    assert len(first_alert) == 1

    still_black = evaluate_alerts(
        session_id="session-black-repeat",
        detector_id="video_metrics",
        row={
            "timestamp_utc": "2026-03-31 10:00:01",
            "source_group": "playlist-c",
            "source_name": "segment_002.ts",
            "black_detected": True,
            "duration_sec": 1.0,
            "black_ratio": 0.95,
            "longest_black_sec": 1.2,
        },
    )
    assert still_black == []

    for index, ratio in enumerate((0.0, 0.0, 0.0), start=2):
        recovered = evaluate_alerts(
            session_id="session-black-repeat",
            detector_id="video_metrics",
            row={
                "timestamp_utc": f"2026-03-31 10:00:0{index}",
                "source_group": "playlist-c",
                "source_name": f"segment_00{index + 1}.ts",
                "black_detected": False,
                "duration_sec": 1.0,
                "black_ratio": ratio,
                "longest_black_sec": 0.0,
            },
        )
        assert recovered == []

    second_alert = evaluate_alerts(
        session_id="session-black-repeat",
        detector_id="video_metrics",
        row={
            "timestamp_utc": "2026-03-31 10:00:05",
            "source_group": "playlist-c",
            "source_name": "segment_006.ts",
            "black_detected": True,
            "duration_sec": 1.0,
            "black_ratio": 0.95,
            "longest_black_sec": 1.2,
        },
    )
    assert len(second_alert) == 1


def test_video_black_rule_resets_between_sessions() -> None:
    """Black rolling state should not leak across sessions."""
    reset_session_rule_state("session-black-a")
    first_session = evaluate_alerts(
        session_id="session-black-a",
        detector_id="video_metrics",
        row={
            "timestamp_utc": "2026-03-31 10:00:00",
            "source_group": "playlist-reset",
            "source_name": "segment_001.ts",
            "black_detected": True,
            "duration_sec": 1.0,
            "black_ratio": 0.95,
            "longest_black_sec": 0.4,
        },
    )
    assert first_session == []

    reset_session_rule_state("session-black-b")
    second_session = evaluate_alerts(
        session_id="session-black-b",
        detector_id="video_metrics",
        row={
            "timestamp_utc": "2026-03-31 10:01:00",
            "source_group": "playlist-reset",
            "source_name": "segment_001.ts",
            "black_detected": True,
            "duration_sec": 1.0,
            "black_ratio": 0.95,
            "longest_black_sec": 0.4,
        },
    )
    assert second_session == []


def test_video_black_rule_keeps_rolling_state_isolated_per_source_group() -> None:
    """Interleaved live slices from another source group should not fill the window."""
    reset_session_rule_state("session-black-groups")

    first_a = evaluate_alerts(
        session_id="session-black-groups",
        detector_id="video_metrics",
        row={
            "timestamp_utc": "2026-03-31 10:00:00",
            "source_group": "playlist-a",
            "source_name": "a-segment-001.ts",
            "black_detected": True,
            "duration_sec": 1.0,
            "black_ratio": 0.95,
            "longest_black_sec": 0.4,
        },
    )
    only_b = evaluate_alerts(
        session_id="session-black-groups",
        detector_id="video_metrics",
        row={
            "timestamp_utc": "2026-03-31 10:00:01",
            "source_group": "playlist-b",
            "source_name": "b-segment-001.ts",
            "black_detected": True,
            "duration_sec": 1.0,
            "black_ratio": 0.95,
            "longest_black_sec": 0.4,
        },
    )
    second_a = evaluate_alerts(
        session_id="session-black-groups",
        detector_id="video_metrics",
        row={
            "timestamp_utc": "2026-03-31 10:00:02",
            "source_group": "playlist-a",
            "source_name": "a-segment-002.ts",
            "black_detected": True,
            "duration_sec": 1.0,
            "black_ratio": 0.95,
            "longest_black_sec": 0.4,
        },
    )
    third_a = evaluate_alerts(
        session_id="session-black-groups",
        detector_id="video_metrics",
        row={
            "timestamp_utc": "2026-03-31 10:00:03",
            "source_group": "playlist-a",
            "source_name": "a-segment-003.ts",
            "black_detected": True,
            "duration_sec": 1.0,
            "black_ratio": 0.95,
            "longest_black_sec": 0.4,
        },
    )

    assert first_a == []
    assert only_b == []
    assert second_a == []
    assert len(third_a) == 1


def test_video_black_rule_does_not_recover_from_other_source_groups() -> None:
    """Low-black slices from another source group should not reset the active stream."""
    reset_session_rule_state("session-black-cross-recovery")

    entered = evaluate_alerts(
        session_id="session-black-cross-recovery",
        detector_id="video_metrics",
        row={
            "timestamp_utc": "2026-03-31 10:00:00",
            "source_group": "playlist-a",
            "source_name": "a-segment-001.ts",
            "black_detected": True,
            "duration_sec": 1.0,
            "black_ratio": 0.95,
            "longest_black_sec": 1.2,
        },
    )
    assert len(entered) == 1

    for index in range(1, 4):
        recovered_other = evaluate_alerts(
            session_id="session-black-cross-recovery",
            detector_id="video_metrics",
            row={
                "timestamp_utc": f"2026-03-31 10:00:0{index}",
                "source_group": "playlist-b",
                "source_name": f"b-segment-00{index}.ts",
                "black_detected": False,
                "duration_sec": 1.0,
                "black_ratio": 0.0,
                "longest_black_sec": 0.0,
            },
        )
        assert recovered_other == []

    still_active_on_a = evaluate_alerts(
        session_id="session-black-cross-recovery",
        detector_id="video_metrics",
        row={
            "timestamp_utc": "2026-03-31 10:00:04",
            "source_group": "playlist-a",
            "source_name": "a-segment-002.ts",
            "black_detected": True,
            "duration_sec": 1.0,
            "black_ratio": 0.95,
            "longest_black_sec": 1.2,
        },
    )

    assert still_active_on_a == []


def test_video_blur_rule_raises_alert_for_normalized_blur_score() -> None:
    """Blur rule should raise once on entry into a sustained blurry state."""
    reset_session_rule_state("session-blur")
    first = evaluate_alerts(
        session_id="session-blur",
        detector_id="video_blur",
        row={
            "timestamp_utc": "2026-03-31 10:00:00",
            "source_group": "playlist-a",
            "source_name": "segment_001.ts",
            "blur_detected": True,
            "blur_score": 0.80,
            "threshold_used": 0.72,
        },
    )
    second = evaluate_alerts(
        session_id="session-blur",
        detector_id="video_blur",
        row={
            "timestamp_utc": "2026-03-31 10:00:01",
            "source_group": "playlist-a",
            "source_name": "segment_002.ts",
            "blur_detected": True,
            "blur_score": 0.76,
            "threshold_used": 0.72,
        },
    )
    third = evaluate_alerts(
        session_id="session-blur",
        detector_id="video_blur",
        row={
            "timestamp_utc": "2026-03-31 10:00:02",
            "source_group": "playlist-a",
            "source_name": "segment_003.ts",
            "blur_detected": True,
            "blur_score": 0.60,
            "threshold_used": 0.72,
        },
    )

    assert first == []
    assert second == []
    assert len(third) == 1
    assert "entered a blurry state" in third[0].message
    assert "2 of 3 slices above the threshold 0.72" in third[0].message


def test_video_blur_rule_does_not_alert_before_rolling_window_is_full() -> None:
    """Blur rule should wait until the rolling window is full before entry alerts."""
    reset_session_rule_state("session-blur-short")

    first = evaluate_alerts(
        session_id="session-blur-short",
        detector_id="video_blur",
        row={
            "timestamp_utc": "2026-03-31 10:00:00",
            "source_group": "playlist-short",
            "source_name": "segment_001.ts",
            "blur_detected": True,
            "blur_score": 0.9,
            "threshold_used": 0.72,
        },
    )
    second = evaluate_alerts(
        session_id="session-blur-short",
        detector_id="video_blur",
        row={
            "timestamp_utc": "2026-03-31 10:00:01",
            "source_group": "playlist-short",
            "source_name": "segment_002.ts",
            "blur_detected": True,
            "blur_score": 0.9,
            "threshold_used": 0.72,
        },
    )

    assert first == []
    assert second == []


def test_video_blur_rule_respects_threshold_boundary() -> None:
    """Blur rule should allow entry exactly at the configured threshold boundary."""
    reset_session_rule_state("session-blur-boundary")

    first = evaluate_alerts(
        session_id="session-blur-boundary",
        detector_id="video_blur",
        row={
            "timestamp_utc": "2026-03-31 10:00:00",
            "source_group": "playlist-boundary",
            "source_name": "segment_001.ts",
            "blur_detected": True,
            "blur_score": 0.72,
            "threshold_used": 0.72,
        },
    )
    second = evaluate_alerts(
        session_id="session-blur-boundary",
        detector_id="video_blur",
        row={
            "timestamp_utc": "2026-03-31 10:00:01",
            "source_group": "playlist-boundary",
            "source_name": "segment_002.ts",
            "blur_detected": True,
            "blur_score": 0.72,
            "threshold_used": 0.72,
        },
    )
    third = evaluate_alerts(
        session_id="session-blur-boundary",
        detector_id="video_blur",
        row={
            "timestamp_utc": "2026-03-31 10:00:02",
            "source_group": "playlist-boundary",
            "source_name": "segment_003.ts",
            "blur_detected": True,
            "blur_score": 0.60,
            "threshold_used": 0.72,
        },
    )

    assert first == []
    assert second == []
    assert len(third) == 1


def test_video_blur_rule_does_not_repeat_until_recovery_then_alerts_again() -> None:
    """Blur rule should alert once, recover, then alert again on a new blurry episode."""
    reset_session_rule_state("session-blur-repeat")

    entering_scores = [0.82, 0.79, 0.60]
    for index, score in enumerate(entering_scores):
        alerts = evaluate_alerts(
            session_id="session-blur-repeat",
            detector_id="video_blur",
            row={
                "timestamp_utc": f"2026-03-31 10:00:0{index}",
                "source_group": "playlist-b",
                "source_name": f"segment_00{index + 1}.ts",
                "blur_detected": True,
                "blur_score": score,
                "threshold_used": 0.72,
            },
        )

    assert len(alerts) == 1

    still_blurry = evaluate_alerts(
        session_id="session-blur-repeat",
        detector_id="video_blur",
        row={
            "timestamp_utc": "2026-03-31 10:00:04",
            "source_group": "playlist-b",
            "source_name": "segment_004.ts",
            "blur_detected": True,
            "blur_score": 0.90,
            "threshold_used": 0.72,
        },
    )
    assert still_blurry == []

    for index, score in enumerate((0.40, 0.42, 0.45), start=5):
        recovered = evaluate_alerts(
            session_id="session-blur-repeat",
            detector_id="video_blur",
            row={
                "timestamp_utc": f"2026-03-31 10:00:{index:02d}",
                "source_group": "playlist-b",
                "source_name": f"segment_{index:03d}.ts",
                "blur_detected": False,
                "blur_score": score,
                "threshold_used": 0.72,
            },
        )
        assert recovered == []

    reenter_alert_counts = []
    for index, score in enumerate((0.81, 0.77, 0.78), start=8):
        reenter_alerts = evaluate_alerts(
            session_id="session-blur-repeat",
            detector_id="video_blur",
            row={
                "timestamp_utc": f"2026-03-31 10:00:{index:02d}",
                "source_group": "playlist-b",
                "source_name": f"segment_{index:03d}.ts",
                "blur_detected": True,
                "blur_score": score,
                "threshold_used": 0.72,
            },
        )
        reenter_alert_counts.append(len(reenter_alerts))

    assert reenter_alert_counts == [0, 1, 0]


def test_video_blur_rule_resets_between_sessions() -> None:
    """Blur rolling state should not leak across sessions."""
    reset_session_rule_state("session-blur-a")
    first_session = evaluate_alerts(
        session_id="session-blur-a",
        detector_id="video_blur",
        row={
            "timestamp_utc": "2026-03-31 10:00:00",
            "source_group": "playlist-reset",
            "source_name": "segment_001.ts",
            "blur_detected": True,
            "blur_score": 0.90,
            "threshold_used": 0.72,
        },
    )
    assert first_session == []

    reset_session_rule_state("session-blur-b")
    second_session = evaluate_alerts(
        session_id="session-blur-b",
        detector_id="video_blur",
        row={
            "timestamp_utc": "2026-03-31 10:01:00",
            "source_group": "playlist-reset",
            "source_name": "segment_001.ts",
            "blur_detected": True,
            "blur_score": 0.90,
            "threshold_used": 0.72,
        },
    )
    assert second_session == []


def test_video_blur_rule_keeps_rolling_state_isolated_per_source_group() -> None:
    """Interleaved live slices from another source group should not fill blur windows."""
    reset_session_rule_state("session-blur-groups")

    first_a = evaluate_alerts(
        session_id="session-blur-groups",
        detector_id="video_blur",
        row={
            "timestamp_utc": "2026-03-31 10:00:00",
            "source_group": "playlist-a",
            "source_name": "a-segment-001.ts",
            "blur_detected": True,
            "blur_score": 0.82,
            "threshold_used": 0.72,
        },
    )
    only_b = evaluate_alerts(
        session_id="session-blur-groups",
        detector_id="video_blur",
        row={
            "timestamp_utc": "2026-03-31 10:00:01",
            "source_group": "playlist-b",
            "source_name": "b-segment-001.ts",
            "blur_detected": True,
            "blur_score": 0.88,
            "threshold_used": 0.72,
        },
    )
    second_a = evaluate_alerts(
        session_id="session-blur-groups",
        detector_id="video_blur",
        row={
            "timestamp_utc": "2026-03-31 10:00:02",
            "source_group": "playlist-a",
            "source_name": "a-segment-002.ts",
            "blur_detected": True,
            "blur_score": 0.79,
            "threshold_used": 0.72,
        },
    )
    third_a = evaluate_alerts(
        session_id="session-blur-groups",
        detector_id="video_blur",
        row={
            "timestamp_utc": "2026-03-31 10:00:03",
            "source_group": "playlist-a",
            "source_name": "a-segment-003.ts",
            "blur_detected": True,
            "blur_score": 0.60,
            "threshold_used": 0.72,
        },
    )

    assert first_a == []
    assert only_b == []
    assert second_a == []
    assert len(third_a) == 1


def test_video_blur_rule_does_not_recover_from_other_source_groups() -> None:
    """Recovery slices from another source group should not reset the active blur state."""
    reset_session_rule_state("session-blur-cross-recovery")

    for index, score in enumerate((0.82, 0.79, 0.60)):
        entered = evaluate_alerts(
            session_id="session-blur-cross-recovery",
            detector_id="video_blur",
            row={
                "timestamp_utc": f"2026-03-31 10:00:0{index}",
                "source_group": "playlist-a",
                "source_name": f"a-segment-00{index + 1}.ts",
                "blur_detected": True,
                "blur_score": score,
                "threshold_used": 0.72,
            },
        )

    assert len(entered) == 1

    for index, score in enumerate((0.40, 0.42, 0.45), start=3):
        recovered_other = evaluate_alerts(
            session_id="session-blur-cross-recovery",
            detector_id="video_blur",
            row={
                "timestamp_utc": f"2026-03-31 10:00:0{index}",
                "source_group": "playlist-b",
                "source_name": f"b-segment-00{index}.ts",
                "blur_detected": False,
                "blur_score": score,
                "threshold_used": 0.72,
            },
        )
        assert recovered_other == []

    still_active_on_a = evaluate_alerts(
        session_id="session-blur-cross-recovery",
        detector_id="video_blur",
        row={
            "timestamp_utc": "2026-03-31 10:00:06",
            "source_group": "playlist-a",
            "source_name": "a-segment-004.ts",
            "blur_detected": True,
            "blur_score": 0.90,
            "threshold_used": 0.72,
        },
    )

    assert still_active_on_a == []
