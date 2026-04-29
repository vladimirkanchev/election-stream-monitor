"""Tests for sensitive log-value redaction.

These cases also lock the worker-observability redaction rules used by the
session service and CLI worker launch/failure logs.
"""

from logger import format_log_context


def test_format_log_context_redacts_sensitive_source_references_and_payloads() -> None:
    """Structured logging should keep debugging context without leaking full sources."""
    context = format_log_context(
        session_id="session-1",
        input_path="/private/stream-secrets/source.mp4",
        source_url="https://media.example.com/live/playlist.m3u8?token=secret",
        payload={"detector": "video_metrics", "secret": "value"},
    )

    assert "session_id='session-1'" in context
    assert "input_path='<path:source.mp4>'" in context
    assert "source_url='https://media.example.com/<redacted>'" in context
    assert "payload='<redacted-payload>'" in context
    assert "/private/stream-secrets" not in context
    assert "token=secret" not in context
    assert "value" not in context


def test_format_log_context_redacts_worker_observability_fields() -> None:
    """Worker launch/failure logs should keep session context without leaking filesystem paths."""
    context = format_log_context(
        session_id="session-123",
        mode="video_files",
        input_path="/private/uploads/source.mp4",
        worker_log_path="/private/data/sessions/session-123/worker.log",
    )

    assert "session_id='session-123'" in context
    assert "mode='video_files'" in context
    assert "input_path='<path:source.mp4>'" in context
    assert "worker_log_path='<path:worker.log>'" in context
    assert "/private/uploads" not in context
    assert "/private/data/sessions" not in context


def test_format_log_context_redacts_api_stream_urls_when_logged_as_url_fields() -> None:
    """Remote live URLs should keep origin-only visibility in observability logs."""
    context = format_log_context(
        session_id="session-live",
        input_url="https://media.example.com/live/playlist.m3u8?token=secret",
    )

    assert "session_id='session-live'" in context
    assert "input_url='https://media.example.com/<redacted>'" in context
    assert "playlist.m3u8" not in context
    assert "token=secret" not in context
