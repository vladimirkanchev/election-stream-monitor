"""Focused tests for latest-progress write guards in the session runner."""

from dataclasses import replace

import session_runner_progress
from session_models import SessionProgress


def _progress(
    *,
    last_updated_utc: str,
    processed_count: int = 1,
    status: str = "running",
    status_reason: str | None = "running",
    status_detail: str | None = None,
    current_item: str | None = "segment_0001.ts",
) -> SessionProgress:
    """Build one compact persisted-progress payload for guard tests."""
    return SessionProgress(
        session_id="session-progress-guard",
        status=status,
        processed_count=processed_count,
        total_count=3,
        current_item=current_item,
        latest_result_detector="video_metrics",
        alert_count=1,
        last_updated_utc=last_updated_utc,
        latest_result_detectors=["video_metrics"],
        status_reason=status_reason,
        status_detail=status_detail,
    )


def test_persist_progress_if_changed_skips_timestamp_only_refreshes() -> None:
    """Timestamp-only refreshes should not create another persisted progress write."""
    current = _progress(last_updated_utc="2026-06-30 10:00:01")
    next_progress = replace(current, last_updated_utc="2026-06-30 10:00:02")
    recorded: list[SessionProgress] = []

    resolved = session_runner_progress.persist_progress_if_changed(
        current=current,
        next_progress=next_progress,
        write_progress=recorded.append,
    )

    assert recorded == []
    assert resolved is current


def test_persist_progress_if_changed_writes_semantic_progress_changes() -> None:
    """A real progress change should still persist immediately."""
    current = _progress(last_updated_utc="2026-06-30 10:00:01", processed_count=1)
    next_progress = _progress(last_updated_utc="2026-06-30 10:00:02", processed_count=2)
    recorded: list[SessionProgress] = []

    resolved = session_runner_progress.persist_progress_if_changed(
        current=current,
        next_progress=next_progress,
        write_progress=recorded.append,
    )

    assert recorded == [next_progress]
    assert resolved is next_progress
