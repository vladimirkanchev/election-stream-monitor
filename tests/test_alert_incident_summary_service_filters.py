"""Focused grouped incident-summary tests for filter reuse, validation, and empty results.

This file owns the grouped summary behavior that should stay aligned with the
shared raw alert-query seam:

- filtered-empty grouped summaries
- invalid and inverted time-range validation
- missing-session and unknown-filter behavior
"""

from pathlib import Path

import pytest

from session_alert_incidents import build_session_incident_summary
from session_alerts import SessionAlertsNotFoundError
from tests.alert_incident_service_test_support import (
    assert_empty_incident_summary,
    build_incident_summary_with_time_filters,
    single_time_filter_kwargs,
    write_single_grouped_alert_session,
)
from tests.session_alert_test_support import (
    configure_session_alert_test,
    write_known_session,
)


def test_build_session_incident_summary_returns_empty_summary_for_filtered_no_match(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Filtered grouped summaries should keep the stable empty contract when nothing matches."""
    session_root = configure_session_alert_test(monkeypatch, tmp_path)
    write_single_grouped_alert_session(
        session_root,
        "session-incident-filtered-empty",
        message="Only metrics warning persisted.",
    )

    assert_empty_incident_summary(
        build_session_incident_summary(
            "session-incident-filtered-empty",
            detector_id="video_blur",
        ),
        "session-incident-filtered-empty",
    )


@pytest.mark.parametrize(
    ("filter_name", "filter_value"),
    [
        ("start_time_utc", "bad-start"),
        ("end_time_utc", "2026/05/06 10:00:00"),
    ],
)
def test_build_session_incident_summary_rejects_invalid_time_filter_formats(
    monkeypatch,
    tmp_path: Path,
    filter_name: str,
    filter_value: str,
) -> None:
    """Incident summaries should preserve raw-service invalid-time validation."""
    session_root = configure_session_alert_test(monkeypatch, tmp_path)
    write_known_session(session_root, "session-incident-invalid-time")

    with pytest.raises(ValueError, match=filter_name):
        build_incident_summary_with_time_filters(
            "session-incident-invalid-time",
            **single_time_filter_kwargs(filter_name, filter_value),
        )


def test_build_session_incident_summary_rejects_inverted_time_range(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Grouped summaries should preserve raw-service inverted-range validation."""
    session_root = configure_session_alert_test(monkeypatch, tmp_path)
    write_known_session(session_root, "session-incident-inverted-range")

    with pytest.raises(
        ValueError,
        match="start_time_utc must be earlier than or equal to end_time_utc",
    ):
        build_incident_summary_with_time_filters(
            "session-incident-inverted-range",
            start_time_utc="2026-05-06 10:01:00",
            end_time_utc="2026-05-06 10:00:00",
        )


def test_build_session_incident_summary_requires_known_session(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Incident summaries should fail clearly for unknown sessions."""
    configure_session_alert_test(monkeypatch, tmp_path)

    with pytest.raises(SessionAlertsNotFoundError):
        build_session_incident_summary("missing-incident-summary-session")


@pytest.mark.parametrize(
    ("detector_id", "severity"),
    [
        ("unknown_detector", None),
        (None, "critical"),
        ("unknown_detector", "critical"),
    ],
)
def test_build_session_incident_summary_returns_empty_summary_for_unknown_filter_values(
    monkeypatch,
    tmp_path: Path,
    detector_id: str | None,
    severity: str | None,
) -> None:
    """Unknown grouped-summary filters should degrade to the stable empty summary."""
    session_root = configure_session_alert_test(monkeypatch, tmp_path)
    write_single_grouped_alert_session(
        session_root,
        "session-incident-unknown-filters",
    )

    assert_empty_incident_summary(
        build_session_incident_summary(
            "session-incident-unknown-filters",
            detector_id=detector_id,
            severity=severity,
        ),
        "session-incident-unknown-filters",
    )
