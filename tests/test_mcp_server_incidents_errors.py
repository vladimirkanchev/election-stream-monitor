"""Negative-path tests for grouped MCP incident timeline and summary tools.

This file owns grouped MCP tool-level error mapping:

- missing-session failures
- invalid time-range failures
- invalid timestamp-format failures
- sanitized storage failures
- timeline/summary parity where both grouped tools should expose the same MCP
  error contract

Keeping these checks apart from the grouped payload file makes incident/timeline
output regressions and grouped error-translation regressions fail in distinct,
easy-to-scan places.
"""

from collections.abc import Iterator
from pathlib import Path

import esm_mcp.alert_tools as alert_tools
import pytest
from session_alert_store import clear_default_session_alert_store_cache
from session_alerts import SessionAlertsNotFoundError
from tests.mcp_alert_test_support import (
    assert_mcp_storage_failure_is_sanitized,
    call_mcp_tool,
)
from tests.mcp_server_incidents_test_support import (
    assert_mcp_tool_error,
    write_incident_tool_session,
)
from tests.session_alert_test_support import (
    FailingReadAlertStore,
    REAL_POSTGRES_ALERT_STORE_SMOKE_ENABLED,
    build_live_runtime_postgres_store,
    build_unique_session_id,
    close_store_if_possible,
    select_runtime_postgres_store,
)


@pytest.fixture(autouse=True)
def _clear_default_alert_store_cache() -> Iterator[None]:
    """Keep runtime-selected default-store caching isolated in grouped MCP error tests."""
    clear_default_session_alert_store_cache()
    yield
    clear_default_session_alert_store_cache()


def _assert_grouped_tool_maps_service_error(
    monkeypatch,
    *,
    tool_name: str,
    service_attr: str,
    session_id: str,
    tool_arguments: dict[str, str],
    service_error: Exception,
    expected_message: str,
) -> None:
    """Assert one grouped MCP tool maps a shared-service error into MCP error text."""

    def fake_grouped_service(
        current_session_id: str,
        **_: object,
    ) -> dict[str, object]:
        assert current_session_id == session_id
        raise service_error

    monkeypatch.setattr(alert_tools, service_attr, fake_grouped_service)

    result = call_mcp_tool(
        tool_name,
        {"session_id": session_id, **tool_arguments},
    )

    assert_mcp_tool_error(result, expected_message=expected_message)


def test_query_session_alert_timeline_tool_reports_missing_session_as_tool_error(
    monkeypatch,
) -> None:
    """Timeline tool failures should reuse the ordinary MCP tool error contract."""
    _assert_grouped_tool_maps_service_error(
        monkeypatch,
        tool_name="query_session_alert_timeline",
        service_attr="build_session_timeline",
        session_id="missing-session",
        tool_arguments={},
        service_error=SessionAlertsNotFoundError("missing-session"),
        expected_message="Session not found: missing-session",
    )


@pytest.mark.parametrize(
    ("tool_name", "service_attr", "session_id"),
    [
        (
            "query_session_alert_timeline",
            "build_session_timeline",
            "session-mcp-timeline-invalid-range",
        ),
        (
            "summarize_session_alert_incidents",
            "build_session_incident_summary",
            "session-mcp-incident-invalid-range",
        ),
    ],
)
def test_grouped_mcp_tools_report_invalid_time_range_as_tool_error(
    monkeypatch,
    tool_name: str,
    service_attr: str,
    session_id: str,
) -> None:
    """Grouped MCP tools should keep the same invalid-range error contract."""
    expected_message = "start_time_utc must be earlier than or equal to end_time_utc"
    _assert_grouped_tool_maps_service_error(
        monkeypatch,
        tool_name=tool_name,
        service_attr=service_attr,
        session_id=session_id,
        tool_arguments={
            "start_time_utc": "2026-05-06 10:10:00",
            "end_time_utc": "2026-05-06 10:00:00",
        },
        service_error=ValueError(expected_message),
        expected_message=expected_message,
    )


@pytest.mark.parametrize(
    ("tool_name", "service_attr", "session_id"),
    [
        (
            "query_session_alert_timeline",
            "build_session_timeline",
            "session-mcp-timeline-invalid-format",
        ),
        (
            "summarize_session_alert_incidents",
            "build_session_incident_summary",
            "session-mcp-incident-invalid-format",
        ),
    ],
)
def test_grouped_mcp_tools_report_invalid_timestamp_format_as_tool_error(
    monkeypatch,
    tool_name: str,
    service_attr: str,
    session_id: str,
) -> None:
    """Malformed grouped MCP timestamp filters should stay readable and aligned."""
    expected_message = (
        "start_time_utc must use UTC timestamp format '%Y-%m-%d %H:%M:%S'"
    )
    _assert_grouped_tool_maps_service_error(
        monkeypatch,
        tool_name=tool_name,
        service_attr=service_attr,
        session_id=session_id,
        tool_arguments={"start_time_utc": "not-a-time"},
        service_error=ValueError(expected_message),
        expected_message=expected_message,
    )


def test_grouped_mcp_tools_report_runtime_postgres_read_failure_as_tool_error(
    monkeypatch,
) -> None:
    """Grouped tools should hide post-startup PostgreSQL read diagnostics."""
    select_runtime_postgres_store(
        monkeypatch,
        FailingReadAlertStore(
            "session-runtime-postgres-mcp-grouped-error",
            "database grouped read failed",
        ),
    )

    timeline_result = call_mcp_tool(
        "query_session_alert_timeline",
        {"session_id": "session-runtime-postgres-mcp-grouped-error"},
    )
    summary_result = call_mcp_tool(
        "summarize_session_alert_incidents",
        {"session_id": "session-runtime-postgres-mcp-grouped-error"},
    )

    assert_mcp_tool_error(timeline_result, expected_message="Alert storage is unavailable")
    assert_mcp_tool_error(summary_result, expected_message="Alert storage is unavailable")


@pytest.mark.skipif(
    not REAL_POSTGRES_ALERT_STORE_SMOKE_ENABLED,
    reason="Real PostgreSQL grouped MCP error smoke test is opt-in.",
)
def test_grouped_mcp_tools_report_live_runtime_postgres_read_failure_after_successful_startup(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Live PostgreSQL read failures should use the safe grouped-tool error."""
    session_id = build_unique_session_id(
        "session-runtime-postgres-mcp-grouped-live-error"
    )
    store = build_live_runtime_postgres_store(
        monkeypatch,
        tmp_path,
        session_id=session_id,
        session_root_builder=write_incident_tool_session,
    )
    try:
        monkeypatch.setattr(
            store,
            "read_session_alert_events",
            lambda current_session_id: (_ for _ in ()).throw(
                RuntimeError("live database grouped read failed")
            ),
        )
        monkeypatch.setattr(
            "session_alert_store._build_postgres_default_session_alert_store",
            lambda: store,
        )
        clear_default_session_alert_store_cache()

        timeline_result = call_mcp_tool(
            "query_session_alert_timeline",
            {"session_id": session_id},
        )
        summary_result = call_mcp_tool(
            "summarize_session_alert_incidents",
            {"session_id": session_id},
    )
    finally:
        close_store_if_possible(store)

    assert_mcp_tool_error(
        timeline_result,
        expected_message="Alert storage is unavailable",
    )
    assert_mcp_tool_error(
        summary_result,
        expected_message="Alert storage is unavailable",
    )


@pytest.mark.parametrize(
    ("tool_name", "service_attr", "error_type"),
    [
        ("query_session_alert_timeline", "build_session_timeline", RuntimeError),
        ("query_session_alert_timeline", "build_session_timeline", ValueError),
        (
            "summarize_session_alert_incidents",
            "build_session_incident_summary",
            RuntimeError,
        ),
        (
            "summarize_session_alert_incidents",
            "build_session_incident_summary",
            ValueError,
        ),
    ],
)
def test_grouped_mcp_tools_hide_storage_diagnostics(
    monkeypatch,
    tool_name: str,
    service_attr: str,
    error_type: type[Exception],
) -> None:
    """Grouped tools must not disclose backend details from failed reads."""
    leaked_detail = (
        "psycopg driver failed: SELECT * FROM session_alert_events "
        "for postgresql://alerts:db-secret@db.example/esm "
        "password=tool-secret path=/srv/esm/incidents"
    )

    def failing_service(*_: object, **__: object) -> object:
        raise error_type(leaked_detail)

    monkeypatch.setattr(alert_tools, service_attr, failing_service)
    result = call_mcp_tool(tool_name, {"session_id": "session-storage-failure"})

    assert_mcp_storage_failure_is_sanitized(
        result,
        forbidden_values=(
            "db-secret",
            "tool-secret",
            "postgresql://",
            "SELECT",
            "/srv/esm",
            "psycopg",
        ),
    )
