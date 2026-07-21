"""Focused contract tests for PostgreSQL diagnostic redaction.

They protect the shared sanitizer itself; store and runtime tests cover its
application at their respective failure boundaries.
"""

from __future__ import annotations

import pytest

from postgres_diagnostics import (
    REDACTED_POSTGRES_URL,
    redact_postgres_database_url,
    redact_postgres_diagnostic,
)


@pytest.mark.parametrize(
    ("database_url", "expected"),
    (
        (
            "postgresql://alerts:secret@db.example:5432/election_stream_monitor",
            "postgresql://<redacted>@db.example:5432/election_stream_monitor",
        ),
        (
            "postgresql://encoded%20user:secret%3Avalue@db.example/esm",
            "postgresql://<redacted>@db.example/esm",
        ),
        (
            "postgres://db.example/esm?application_name=esm",
            "postgres://db.example/esm?application_name=esm",
        ),
        (
            "postgresql://user:password@db.example/esm?sslpassword=query-secret&token=abc&application_name=esm",
            "postgresql://<redacted>@db.example/esm?sslpassword=%3Credacted%3E&token=%3Credacted%3E&application_name=esm",
        ),
    ),
)
def test_redact_postgres_database_url_keeps_only_safe_endpoint_context(
    database_url: str,
    expected: str,
) -> None:
    """Diagnostics should retain endpoint context without credentials."""
    assert redact_postgres_database_url(database_url) == expected


@pytest.mark.parametrize(
    "database_url",
    (
        "https://user:password@example.com/esm",
        "not a PostgreSQL URL with a password",
        "postgresql://",
    ),
)
def test_redact_postgres_database_url_fails_closed_for_invalid_input(
    database_url: str,
) -> None:
    """Unexpected URL shapes must not be reflected into diagnostics."""
    assert redact_postgres_database_url(database_url) == REDACTED_POSTGRES_URL


def test_redact_postgres_diagnostic_sanitizes_embedded_urls_and_assignments() -> None:
    """Driver-style details should retain context without credential values."""
    diagnostic = (
        "connection failed for postgresql://encoded%20user:secret%3Avalue@db.example/esm"
        "?token=query-token: password=plain-secret sslkey='/private/client.key'"
    )

    redacted = redact_postgres_diagnostic(diagnostic)

    assert "postgresql://<redacted>@db.example/esm?token=<redacted>" in redacted
    assert "password=<redacted>" in redacted
    assert "sslkey=<redacted>" in redacted
    assert "encoded%20user" not in redacted
    assert "secret%3Avalue" not in redacted
    assert "query-token" not in redacted
    assert "plain-secret" not in redacted
    assert "/private/client.key" not in redacted
