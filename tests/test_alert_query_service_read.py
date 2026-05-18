"""Focused tests for raw alert reads over the persistence seam.

This suite keeps the lowest-level read contract small: valid persisted rows,
safe degradation on bad logs, and the shared known-session boundary.
"""

from pathlib import Path

import pytest

from session_alerts import SessionAlertsNotFoundError, read_session_alert_events
from tests.session_alert_test_support import (
    StaticAlertStore,
    build_normalized_alert,
    build_persisted_alert,
    configure_session_alert_test,
    write_alert_log,
    write_known_session,
)


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

    def fake_read_text(
        self: Path,
        encoding: str | None = None,
        errors: str | None = None,
    ) -> str:
        if self.parent.name == "session-unreadable" and self.name == "alerts.jsonl":
            raise OSError("simulated unreadable file")
        return original_read_text(self, encoding=encoding, errors=errors)

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


def test_read_session_alert_events_accepts_an_explicit_store_seam() -> None:
    """Raw alert reads should be able to depend on an injected store seam."""
    store = StaticAlertStore(
        "store-session",
        [
            build_normalized_alert(
                "store-session",
                timestamp_utc="2026-05-06 10:00:00",
                detector_id="video_metrics",
                title="Black screen detected",
                message="From the injected store.",
                severity="warning",
                source_name="segment_0001.ts",
            )
        ],
    )

    assert read_session_alert_events("store-session", store=store) == [
        build_normalized_alert(
            "store-session",
            timestamp_utc="2026-05-06 10:00:00",
            detector_id="video_metrics",
            title="Black screen detected",
            message="From the injected store.",
            severity="warning",
            source_name="segment_0001.ts",
        )
    ]
