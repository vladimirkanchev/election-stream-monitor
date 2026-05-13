"""Shared setup helpers for the raw session alert query service tests.

The split read/filter/summary suites all rely on the same lightweight
file-backed session setup. This support module intentionally stays small: it
owns only the helper seams that improve readability across the split files
without absorbing behavior ownership from the service-specific suites.
"""

from collections.abc import Callable
from pathlib import Path

import pytest

from session_alerts import SessionAlertsNotFoundError
from tests.session_alert_test_support import (
    configure_session_alert_test,
    write_known_session,
)


def write_known_session_without_alerts(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    session_id: str,
) -> None:
    """Create one known session for validation paths that do not need alert rows."""
    session_root = configure_session_alert_test(monkeypatch, tmp_path)
    write_known_session(session_root, session_id)


def assert_query_requires_known_session(
    query: Callable[[str], object],
    session_id: str,
) -> None:
    """Assert that one query entrypoint preserves the shared unknown-session contract."""
    with pytest.raises(SessionAlertsNotFoundError):
        query(session_id)
