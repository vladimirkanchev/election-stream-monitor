"""Focused service tests for raw session alert read, filter, and summary behavior.

This file owns the low-level alert-query contract:

- reading persisted alert rows from one known session
- tolerating malformed or unreadable alert-log input
- applying detector, severity, and time filters
- producing the raw numeric alert summary used by both FastAPI and MCP

Grouped incident behavior lives in ``test_alert_timeline_service.py`` and
``test_alert_incident_summary_service.py`` so the raw alert seam stays easy to
scan on its own.
"""

from pathlib import Path

import pytest

from session_alerts import (
    SessionAlertsNotFoundError,
    filter_session_alert_events,
    read_session_alert_events,
    summarize_session_alert_events,
)
from tests.session_alert_test_support import (
    build_alert_summary_payload,
    build_normalized_alert,
    build_persisted_alert,
    configure_session_alert_test,
    write_alert_log,
    write_known_session,
)


# Read semantics


def test_read_session_alert_events_returns_valid_rows_and_ignores_corrupt_lines(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Persisted reads should keep valid rows and degrade safely on bad lines."""
    session_root = configure_session_alert_test(monkeypatch, tmp_path)
    session_dir = write_known_session(session_root, "session-alerts")
    write_alert_log(
        session_dir,
        [
            build_persisted_alert(
                "session-alerts",
                timestamp_utc="2026-05-06 10:00:00",
                detector_id="video_metrics",
                title="Black screen detected",
                message="Long black segment exceeded threshold.",
                severity="warning",
                source_name="segment_0001.ts",
            ),
            "{bad json",
            build_persisted_alert(
                "session-alerts",
                timestamp_utc="2026-05-06 10:00:05",
                detector_id="",
                title="Invalid detector id",
                message="Should be ignored.",
                severity="warning",
                source_name="segment_0002.ts",
            ),
        ],
    )

    alerts = read_session_alert_events("session-alerts")

    assert alerts == [
        build_normalized_alert(
            "session-alerts",
            timestamp_utc="2026-05-06 10:00:00",
            detector_id="video_metrics",
            title="Black screen detected",
            message="Long black segment exceeded threshold.",
            severity="warning",
            source_name="segment_0001.ts",
        )
    ]


def test_read_session_alert_events_returns_empty_list_when_alert_log_is_missing(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Known sessions without ``alerts.jsonl`` should read as empty alert history."""
    session_root = configure_session_alert_test(monkeypatch, tmp_path)
    write_known_session(session_root, "session-no-alerts")

    assert read_session_alert_events("session-no-alerts") == []


def test_read_session_alert_events_returns_empty_list_when_alert_log_is_unreadable(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Unreadable alert logs should degrade to an empty read instead of failing."""
    session_root = configure_session_alert_test(monkeypatch, tmp_path)
    write_known_session(
        session_root,
        "session-unreadable",
        alert_rows=[
            build_persisted_alert(
                "session-unreadable",
                timestamp_utc="2026-05-06 10:00:00",
                detector_id="video_metrics",
                title="Black screen detected",
                message="Black segment.",
                severity="warning",
                source_name="segment_0001.ts",
            )
        ],
    )
    original_read_text = Path.read_text

    def fake_read_text(self: Path, *args: object, **kwargs: object) -> str:
        if self.parent.name == "session-unreadable" and self.name == "alerts.jsonl":
            raise OSError("simulated unreadable file")
        return original_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", fake_read_text)

    assert read_session_alert_events("session-unreadable") == []


def test_read_session_alert_events_requires_known_session(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Missing ``session.json`` should still be treated as an unknown session."""
    configure_session_alert_test(monkeypatch, tmp_path)

    with pytest.raises(SessionAlertsNotFoundError):
        read_session_alert_events("missing-session")


def test_read_session_alert_events_rejects_directory_without_session_metadata(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """An orphaned directory should not bypass the known-session contract."""
    configure_session_alert_test(monkeypatch, tmp_path)
    session_dir = tmp_path / "orphaned-session-dir"
    session_dir.mkdir(parents=True)
    (session_dir / "alerts.jsonl").write_text("", encoding="utf-8")

    with pytest.raises(SessionAlertsNotFoundError):
        read_session_alert_events("orphaned-session-dir")


# Filter semantics


def test_filter_session_alert_events_applies_detector_severity_and_time_filters(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Filtering should combine detector, severity, and inclusive time bounds."""
    session_root = configure_session_alert_test(monkeypatch, tmp_path)
    write_known_session(
        session_root,
        "session-filter",
        alert_rows=[
            build_persisted_alert(
                "session-filter",
                timestamp_utc="2026-05-06 10:00:00",
                detector_id="video_metrics",
                title="Black screen detected",
                message="Black segment.",
                severity="warning",
                source_name="segment_0001.ts",
            ),
            build_persisted_alert(
                "session-filter",
                timestamp_utc="2026-05-06 10:00:10",
                detector_id="video_blur",
                title="Blur increased",
                message="Blur threshold exceeded.",
                severity="info",
                source_name="segment_0002.ts",
            ),
            build_persisted_alert(
                "session-filter",
                timestamp_utc="2026-05-06 10:00:20",
                detector_id="video_metrics",
                title="Black screen detected",
                message="Black segment again.",
                severity="warning",
                source_name="segment_0003.ts",
            ),
        ],
    )

    filtered = filter_session_alert_events(
        "session-filter",
        detector_id="video_metrics",
        severity="warning",
        start_time_utc="2026-05-06 10:00:05",
        end_time_utc="2026-05-06 10:00:25",
    )

    assert filtered == [
        build_normalized_alert(
            "session-filter",
            timestamp_utc="2026-05-06 10:00:20",
            detector_id="video_metrics",
            title="Black screen detected",
            message="Black segment again.",
            severity="warning",
            source_name="segment_0003.ts",
        )
    ]


def test_filter_session_alert_events_ignores_rows_with_unparseable_persisted_timestamps(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Time-filtered queries should skip rows whose persisted timestamps are invalid."""
    session_root = configure_session_alert_test(monkeypatch, tmp_path)
    write_known_session(
        session_root,
        "session-bad-time-filter",
        alert_rows=[
            build_persisted_alert(
                "session-bad-time-filter",
                timestamp_utc="not-a-time",
                detector_id="video_metrics",
                title="Bad timestamp",
                message="Should be ignored for time filtering.",
                severity="warning",
                source_name="segment_0001.ts",
            ),
            build_persisted_alert(
                "session-bad-time-filter",
                timestamp_utc="2026-05-06 10:00:10",
                detector_id="video_metrics",
                title="Good timestamp",
                message="Should survive filtering.",
                severity="warning",
                source_name="segment_0002.ts",
            ),
        ],
    )

    filtered = filter_session_alert_events(
        "session-bad-time-filter",
        start_time_utc="2026-05-06 10:00:00",
        end_time_utc="2026-05-06 10:00:20",
    )

    assert filtered == [
        build_normalized_alert(
            "session-bad-time-filter",
            timestamp_utc="2026-05-06 10:00:10",
            detector_id="video_metrics",
            title="Good timestamp",
            message="Should survive filtering.",
            severity="warning",
            source_name="segment_0002.ts",
        )
    ]


def test_filter_session_alert_events_rejects_inverted_time_range(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Validation stays in the service layer for obviously invalid time ranges."""
    session_root = configure_session_alert_test(monkeypatch, tmp_path)
    write_known_session(session_root, "session-invalid-range")

    with pytest.raises(ValueError, match="start_time_utc"):
        filter_session_alert_events(
            "session-invalid-range",
            start_time_utc="2026-05-06 10:00:10",
            end_time_utc="2026-05-06 10:00:00",
        )


# Raw summary semantics


def test_summarize_session_alert_events_returns_counts_and_time_bounds(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """The summary contract should remain deterministic and numeric only."""
    session_root = configure_session_alert_test(monkeypatch, tmp_path)
    write_known_session(
        session_root,
        "session-summary",
        alert_rows=[
            build_persisted_alert(
                "session-summary",
                timestamp_utc="2026-05-06 10:00:00",
                detector_id="video_metrics",
                title="Black screen detected",
                message="Black segment.",
                severity="warning",
                source_name="segment_0001.ts",
            ),
            build_persisted_alert(
                "session-summary",
                timestamp_utc="2026-05-06 10:00:10",
                detector_id="video_blur",
                title="Blur increased",
                message="Blur threshold exceeded.",
                severity="info",
                source_name="segment_0002.ts",
            ),
            build_persisted_alert(
                "session-summary",
                timestamp_utc="2026-05-06 10:00:20",
                detector_id="video_metrics",
                title="Black screen detected",
                message="Black segment again.",
                severity="warning",
                source_name="segment_0003.ts",
            ),
        ],
    )

    summary = summarize_session_alert_events("session-summary")

    assert summary == build_alert_summary_payload(
        "session-summary",
        total_alerts=3,
        counts_by_detector={"video_metrics": 2, "video_blur": 1},
        counts_by_severity={"warning": 2, "info": 1},
        first_alert_timestamp_utc="2026-05-06 10:00:00",
        last_alert_timestamp_utc="2026-05-06 10:00:20",
    )


def test_summarize_session_alert_events_ignores_bad_timestamps_for_time_bounds(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Summary time bounds should ignore bad persisted timestamps but keep total counts."""
    session_root = configure_session_alert_test(monkeypatch, tmp_path)
    write_known_session(
        session_root,
        "session-summary-bad-time",
        alert_rows=[
            build_persisted_alert(
                "session-summary-bad-time",
                timestamp_utc="2026-05-06 10:00:00",
                detector_id="video_metrics",
                title="Good timestamp",
                message="Count this and use for bounds.",
                severity="warning",
                source_name="segment_0001.ts",
            ),
            build_persisted_alert(
                "session-summary-bad-time",
                timestamp_utc="bad-time",
                detector_id="video_blur",
                title="Bad timestamp",
                message="Count this but ignore it for bounds.",
                severity="info",
                source_name="segment_0002.ts",
            ),
        ],
    )

    summary = summarize_session_alert_events("session-summary-bad-time")

    assert summary == build_alert_summary_payload(
        "session-summary-bad-time",
        total_alerts=2,
        counts_by_detector={"video_metrics": 1, "video_blur": 1},
        counts_by_severity={"warning": 1, "info": 1},
        first_alert_timestamp_utc="2026-05-06 10:00:00",
        last_alert_timestamp_utc="2026-05-06 10:00:00",
    )


def test_summarize_session_alert_events_returns_empty_summary_when_filters_match_nothing(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Empty filtered summaries should keep the stable zero-alert contract."""
    session_root = configure_session_alert_test(monkeypatch, tmp_path)
    write_known_session(
        session_root,
        "session-summary-empty",
        alert_rows=[
            build_persisted_alert(
                "session-summary-empty",
                timestamp_utc="2026-05-06 10:00:00",
                detector_id="video_metrics",
                title="Black screen detected",
                message="Black segment.",
                severity="warning",
                source_name="segment_0001.ts",
            )
        ],
    )

    summary = summarize_session_alert_events(
        "session-summary-empty",
        severity="info",
    )

    assert summary == build_alert_summary_payload(
        "session-summary-empty",
        total_alerts=0,
        counts_by_detector={},
        counts_by_severity={},
        first_alert_timestamp_utc=None,
        last_alert_timestamp_utc=None,
    )
