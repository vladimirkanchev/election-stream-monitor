"""Focused contract tests for PostgreSQL diagnostic redaction.

They protect the shared sanitizer itself; store and runtime tests cover its
application at their respective failure boundaries.
"""

from __future__ import annotations

import pytest

from postgres_diagnostics import (
    REDACTED_POSTGRES_URL,
    SAFE_POSTGRES_DIAGNOSTIC,
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


def test_redact_postgres_diagnostic_hides_driver_level_details() -> None:
    """Driver diagnostics should not retain URLs, SQL, paths, or secret values."""
    diagnostic = (
        "psycopg failed SELECT * FROM session_alert_events for "
        "postgresql://encoded%20user:secret%3Avalue@db.example/esm"
        "?token=query-token: password=plain-secret sslkey='/private/client.key'"
    )

    redacted = redact_postgres_diagnostic(diagnostic)

    assert redacted == SAFE_POSTGRES_DIAGNOSTIC


def test_redact_postgres_diagnostic_preserves_unrelated_application_errors() -> None:
    """Ordinary worker failures must not be mislabeled as PostgreSQL failures."""

    detail = "detector failed with invalid input /tmp/clip.mp4"

    assert redact_postgres_diagnostic(detail) == detail
