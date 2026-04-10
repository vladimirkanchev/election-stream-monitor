"""Tests for sensitive log-value redaction."""

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
