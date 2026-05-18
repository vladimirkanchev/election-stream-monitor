"""Focused contract tests for the file-backed alert store seam.

These tests lock the current file-backed store behavior before a PostgreSQL
implementation is introduced.
"""

from pathlib import Path

import pytest

from session_alert_incidents import (
    build_session_incident_summary,
    build_session_timeline,
)
from session_alert_store import FileSessionAlertStore, SessionAlertsNotFoundError
from session_alerts import summarize_session_alert_events
from tests.session_alert_test_support import (
    build_normalized_alert,
    build_persisted_alert,
    configure_session_alert_test,
    write_alert_log,
    write_known_session,
)
from session_models import AlertEvent


def _file_store() -> FileSessionAlertStore:
    """Return the concrete file-backed store used in these seam tests."""
    return FileSessionAlertStore()


def _store_event(
    session_id: str,
    *,
    timestamp_utc: str,
    detector_id: str,
    title: str,
    message: str,
    severity: str,
    source_name: str,
    window_index: int | None = None,
    window_start_sec: float | None = None,
) -> AlertEvent:
    """Build one concrete store-write event for file-backed seam tests."""
    return AlertEvent(
        session_id=session_id,
        timestamp_utc=timestamp_utc,
        detector_id=detector_id,
        title=title,
        message=message,
        severity=severity,
        source_name=source_name,
        window_index=window_index,
        window_start_sec=window_start_sec,
    )


def test_file_session_alert_store_reads_valid_rows_and_ignores_corrupt_lines(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """The file-backed store should preserve valid rows and skip bad lines safely."""
    session_root = configure_session_alert_test(monkeypatch, tmp_path)
    session_dir = write_known_session(session_root, "store-read")
    write_alert_log(
        session_dir,
        [
            build_persisted_alert(
                "store-read",
                timestamp_utc="2026-05-06 10:00:00",
                detector_id="video_metrics",
                title="Black screen detected",
                message="Valid alert row.",
                severity="warning",
                source_name="segment_0001.ts",
            ),
            "{bad json",
            build_persisted_alert(
                "store-read",
                timestamp_utc="2026-05-06 10:00:05",
                detector_id="",
                title="Invalid detector",
                message="Should be ignored.",
                severity="warning",
                source_name="segment_0002.ts",
            ),
        ],
    )

    assert _file_store().read_session_alert_events("store-read") == [
        build_normalized_alert(
            "store-read",
            timestamp_utc="2026-05-06 10:00:00",
            detector_id="video_metrics",
            title="Black screen detected",
            message="Valid alert row.",
            severity="warning",
            source_name="segment_0001.ts",
        )
    ]


def test_file_session_alert_store_requires_known_session(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """The file-backed store should keep the shared unknown-session contract."""
    configure_session_alert_test(monkeypatch, tmp_path)

    with pytest.raises(SessionAlertsNotFoundError):
        _file_store().read_session_alert_events("missing-store-session")


def test_file_session_alert_store_supports_append_read_round_trip(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Appending through the store should round-trip through the same raw row contract."""
    session_root = configure_session_alert_test(monkeypatch, tmp_path)
    write_known_session(session_root, "store-round-trip")
    store = _file_store()
    store.append_alert(
        _store_event(
            "store-round-trip",
            timestamp_utc="2026-05-06 10:00:00",
            detector_id="video_metrics",
            title="Black screen detected",
            message="Round-trip through the file-backed store.",
            severity="warning",
            source_name="segment_0001.ts",
            window_index=0,
            window_start_sec=0.0,
        )
    )

    assert store.read_session_alert_events("store-round-trip") == [
        build_normalized_alert(
            "store-round-trip",
            timestamp_utc="2026-05-06 10:00:00",
            detector_id="video_metrics",
            title="Black screen detected",
            message="Round-trip through the file-backed store.",
            severity="warning",
            source_name="segment_0001.ts",
            window_index=0,
            window_start_sec=0.0,
        )
    ]


def test_file_session_alert_store_preserves_append_order_across_multiple_writes(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Multiple writes should still read back in append order."""
    session_root = configure_session_alert_test(monkeypatch, tmp_path)
    write_known_session(session_root, "store-append-order")
    store = _file_store()

    store.append_alert(
        _store_event(
            "store-append-order",
            timestamp_utc="2026-05-06 10:00:20",
            detector_id="video_metrics",
            title="Persisted first",
            message="Written first, even with a later timestamp.",
            severity="warning",
            source_name="segment_0002.ts",
        )
    )
    store.append_alert(
        _store_event(
            "store-append-order",
            timestamp_utc="2026-05-06 10:00:00",
            detector_id="video_metrics",
            title="Persisted second",
            message="Written second, even with an earlier timestamp.",
            severity="warning",
            source_name="segment_0001.ts",
        )
    )

    assert store.read_session_alert_events("store-append-order") == [
        build_normalized_alert(
            "store-append-order",
            timestamp_utc="2026-05-06 10:00:20",
            detector_id="video_metrics",
            title="Persisted first",
            message="Written first, even with a later timestamp.",
            severity="warning",
            source_name="segment_0002.ts",
        ),
        build_normalized_alert(
            "store-append-order",
            timestamp_utc="2026-05-06 10:00:00",
            detector_id="video_metrics",
            title="Persisted second",
            message="Written second, even with an earlier timestamp.",
            severity="warning",
            source_name="segment_0001.ts",
        ),
    ]


def test_file_session_alert_store_repeated_reads_pick_up_later_appends(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Repeated reads should reflect later appends without disturbing earlier rows."""
    session_root = configure_session_alert_test(monkeypatch, tmp_path)
    write_known_session(session_root, "store-repeated-read")
    store = _file_store()

    first_event = _store_event(
        "store-repeated-read",
        timestamp_utc="2026-05-06 10:00:00",
        detector_id="video_metrics",
        title="First persisted row",
        message="Visible on the first read.",
        severity="warning",
        source_name="segment_0001.ts",
    )
    second_event = _store_event(
        "store-repeated-read",
        timestamp_utc="2026-05-06 10:00:10",
        detector_id="video_blur",
        title="Second persisted row",
        message="Visible after the second append.",
        severity="info",
        source_name="segment_0002.ts",
    )

    store.append_alert(first_event)
    assert store.read_session_alert_events("store-repeated-read") == [
        build_normalized_alert(
            "store-repeated-read",
            timestamp_utc="2026-05-06 10:00:00",
            detector_id="video_metrics",
            title="First persisted row",
            message="Visible on the first read.",
            severity="warning",
            source_name="segment_0001.ts",
        )
    ]

    store.append_alert(second_event)
    assert store.read_session_alert_events("store-repeated-read") == [
        build_normalized_alert(
            "store-repeated-read",
            timestamp_utc="2026-05-06 10:00:00",
            detector_id="video_metrics",
            title="First persisted row",
            message="Visible on the first read.",
            severity="warning",
            source_name="segment_0001.ts",
        ),
        build_normalized_alert(
            "store-repeated-read",
            timestamp_utc="2026-05-06 10:00:10",
            detector_id="video_blur",
            title="Second persisted row",
            message="Visible after the second append.",
            severity="info",
            source_name="segment_0002.ts",
        ),
    ]


def test_file_session_alert_store_normalizes_missing_optional_window_fields(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Missing optional window fields should still read back as explicit ``None`` values."""
    session_root = configure_session_alert_test(monkeypatch, tmp_path)
    write_known_session(session_root, "store-window-none")
    store = _file_store()

    store.append_alert(
        _store_event(
            "store-window-none",
            timestamp_utc="2026-05-06 10:00:00",
            detector_id="video_metrics",
            title="Window fields omitted",
            message="The normalized read shape should fill missing optionals with None.",
            severity="warning",
            source_name="segment_0001.ts",
        )
    )

    assert store.read_session_alert_events("store-window-none") == [
        build_normalized_alert(
            "store-window-none",
            timestamp_utc="2026-05-06 10:00:00",
            detector_id="video_metrics",
            title="Window fields omitted",
            message="The normalized read shape should fill missing optionals with None.",
            severity="warning",
            source_name="segment_0001.ts",
            window_index=None,
            window_start_sec=None,
        )
    ]


def test_file_session_alert_store_returns_empty_list_when_alert_log_is_unreadable(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Unreadable alert logs should degrade to an empty store read."""
    session_root = configure_session_alert_test(monkeypatch, tmp_path)
    write_known_session(
        session_root,
        "store-unreadable",
        alert_rows=[
            build_persisted_alert(
                "store-unreadable",
                timestamp_utc="2026-05-06 10:00:00",
                detector_id="video_metrics",
                title="Black screen detected",
                message="This row should become unreadable.",
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
        if self.parent.name == "store-unreadable" and self.name == "alerts.jsonl":
            raise OSError("simulated unreadable alert log")
        return original_read_text(self, encoding=encoding, errors=errors)

    monkeypatch.setattr(Path, "read_text", fake_read_text)

    assert _file_store().read_session_alert_events("store-unreadable") == []


def test_raw_alert_summary_matches_explicit_file_store_behavior(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """The raw summary service should behave the same with the explicit file store seam."""
    session_root = configure_session_alert_test(monkeypatch, tmp_path)
    write_known_session(
        session_root,
        "store-summary-parity",
        alert_rows=[
            build_persisted_alert(
                "store-summary-parity",
                timestamp_utc="2026-05-06 10:00:00",
                detector_id="video_metrics",
                title="Black screen detected",
                message="First warning.",
                severity="warning",
                source_name="segment_0001.ts",
            ),
            build_persisted_alert(
                "store-summary-parity",
                timestamp_utc="2026-05-06 10:00:10",
                detector_id="video_blur",
                title="Blur increased",
                message="Informational blur event.",
                severity="info",
                source_name="segment_0002.ts",
            ),
        ],
    )
    store = _file_store()

    assert summarize_session_alert_events(
        "store-summary-parity",
        store=store,
    ) == summarize_session_alert_events("store-summary-parity")


def test_grouped_incident_read_models_match_explicit_file_store_behavior(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """The grouped services should keep the same output over the explicit file store seam."""
    session_root = configure_session_alert_test(monkeypatch, tmp_path)
    write_known_session(
        session_root,
        "store-incident-parity",
        alert_rows=[
            build_persisted_alert(
                "store-incident-parity",
                timestamp_utc="2026-05-06 10:00:00",
                detector_id="video_metrics",
                title="Black screen detected",
                message="First grouped row.",
                severity="warning",
                source_name="segment_0001.ts",
            ),
            build_persisted_alert(
                "store-incident-parity",
                timestamp_utc="2026-05-06 10:00:20",
                detector_id="video_metrics",
                title="Black screen detected",
                message="Second grouped row.",
                severity="warning",
                source_name="segment_0002.ts",
            ),
        ],
    )
    store = _file_store()

    assert build_session_timeline(
        "store-incident-parity",
        store=store,
    ) == build_session_timeline("store-incident-parity")
    assert build_session_incident_summary(
        "store-incident-parity",
        store=store,
    ) == build_session_incident_summary("store-incident-parity")
