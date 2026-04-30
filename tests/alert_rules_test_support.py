"""Shared helpers for the split alert-rule test suites.

These helpers intentionally stay small and procedural. They reduce repetitive
row-shaping and repeated one-session evaluation loops without hiding the actual
alert-rule timelines that the black and blur suites are protecting.
"""

from alert_rules import evaluate_alerts


def black_row(
    *,
    timestamp_utc: str = "2026-03-31 10:00:00",
    source_group: str = "playlist-a",
    source_name: str = "segment_001.ts",
    black_detected: bool = True,
    duration_sec: float = 1.0,
    black_ratio: object = 0.95,
    longest_black_sec: object = 1.2,
) -> dict[str, object]:
    """Build a representative `video_metrics` row for black-screen scenarios.

    The defaults describe an already-black slice so tests only need to override
    the fields that actually matter for the threshold or recovery transition
    being exercised.
    """
    return {
        "timestamp_utc": timestamp_utc,
        "source_group": source_group,
        "source_name": source_name,
        "black_detected": black_detected,
        "duration_sec": duration_sec,
        "black_ratio": black_ratio,
        "longest_black_sec": longest_black_sec,
    }


def blur_row(
    *,
    timestamp_utc: str = "2026-03-31 10:00:00",
    source_group: str = "playlist-a",
    source_name: str = "segment_001.ts",
    blur_detected: bool = True,
    blur_score: object = 0.80,
    threshold_used: object = 0.72,
) -> dict[str, object]:
    """Build a representative `video_blur` row for blur-rule scenarios.

    The defaults describe a slice that is already above the blur threshold so
    tests can focus on the values that change the rolling-window outcome.
    """
    return {
        "timestamp_utc": timestamp_utc,
        "source_group": source_group,
        "source_name": source_name,
        "blur_detected": blur_detected,
        "blur_score": blur_score,
        "threshold_used": threshold_used,
    }


def evaluate_detector_rows(
    *,
    session_id: str,
    detector_id: str,
    rows: list[dict[str, object]],
) -> list[list[object]]:
    """Evaluate an ordered batch of detector rows for one detector/session.

    The caller still owns the row sequence inline, so the scenario remains easy
    to read while the session/detector plumbing stays out of the way.
    """
    return [
        evaluate_alerts(
            session_id=session_id,
            detector_id=detector_id,
            row=row,
        )
        for row in rows
    ]


def assert_no_alerts(*alert_batches: list[object]) -> None:
    """Assert that one or more evaluation steps stay quiet.

    This keeps sequence-style tests readable without repeating identical
    `assert alerts == []` lines for every intermediate step.
    """
    for alerts in alert_batches:
        assert alerts == []
