"""Sanitize PostgreSQL connection details for operator-facing diagnostics.

This is deliberately a narrow PostgreSQL helper, not a general-purpose secret
scrubber. Callers retain enough endpoint context to diagnose configuration
failures without exposing credentials.
"""

from __future__ import annotations

import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


REDACTED_POSTGRES_VALUE = "<redacted>"
REDACTED_POSTGRES_URL = "<redacted-postgres-url>"
_SENSITIVE_POSTGRES_QUERY_PARAMETER_NAMES = frozenset(
    {
        "access_token",
        "api_key",
        "apikey",
        "pass",
        "passfile",
        "passwd",
        "password",
        "pwd",
        "secret",
        "sslcert",
        "sslkey",
        "sslpassword",
        "sslrootcert",
        "token",
    }
)
_POSTGRES_URL_IN_DIAGNOSTIC_PATTERN = re.compile(
    r"(?i)\b(?:postgres|postgresql)://[^\s'\"`),;\]}]+"
)
_SENSITIVE_POSTGRES_ASSIGNMENT_PATTERN = re.compile(
    r"(?i)\b(?P<name>access[_-]?token|api[_-]?key|apikey|pass(?:word|wd|file)?|"
    r"pwd|secret|ssl(?:password|key|cert|rootcert)|token|user(?:name)?)\s*=\s*"
    r"(?P<value>'[^']*'|\"[^\"]*\"|[^\s,;]+)"
)


def redact_postgres_database_url(database_url: str) -> str:
    """Keep PostgreSQL endpoint context while removing credential-bearing parts.

    The result retains the scheme, host, port, and database path for actionable
    operator diagnostics. It removes user info, redacts known secret query
    values, and falls back to a fixed marker for malformed or non-PostgreSQL
    input rather than risking disclosure.
    """
    try:
        parsed = urlsplit(database_url.strip())
        if parsed.scheme.lower() not in {"postgres", "postgresql"} or not parsed.netloc:
            return REDACTED_POSTGRES_URL

        host_port = parsed.netloc.rsplit("@", maxsplit=1)[-1]
        if not host_port:
            return REDACTED_POSTGRES_URL
        netloc = (
            f"{REDACTED_POSTGRES_VALUE}@{host_port}"
            if "@" in parsed.netloc
            else host_port
        )
        query = urlencode(
            [
                (
                    name,
                    REDACTED_POSTGRES_VALUE
                    if _is_sensitive_postgres_query_parameter(name)
                    else value,
                )
                for name, value in parse_qsl(parsed.query, keep_blank_values=True)
            ]
        )
        return urlunsplit((parsed.scheme, netloc, parsed.path, query, ""))
    except (TypeError, ValueError, UnicodeError):
        return REDACTED_POSTGRES_URL


def redact_postgres_diagnostic(message: str) -> str:
    """Redact PostgreSQL URLs and credential assignments in one diagnostic.

    It preserves ordinary error detail and endpoint context while removing
    embedded PostgreSQL URLs and known secret assignments. Callers still own
    avoiding raw exception chaining after sanitizing a driver error.
    """
    without_urls = _POSTGRES_URL_IN_DIAGNOSTIC_PATTERN.sub(
        lambda match: redact_postgres_database_url(match.group()),
        message,
    )
    return _SENSITIVE_POSTGRES_ASSIGNMENT_PATTERN.sub(
        lambda match: f"{match.group('name')}={REDACTED_POSTGRES_VALUE}",
        without_urls,
    )


def _is_sensitive_postgres_query_parameter(name: str) -> bool:
    """Return whether one PostgreSQL URL query parameter carries a secret."""
    normalized = name.strip().lower().replace("-", "_")
    return normalized in _SENSITIVE_POSTGRES_QUERY_PARAMETER_NAMES
