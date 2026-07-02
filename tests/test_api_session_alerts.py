"""Focused FastAPI tests for raw alert-route transport behavior.

This file owns route parameter binding, payload shaping, empty-result behavior,
and error mapping for the raw alert list and summary endpoints.
"""

from collections.abc import Iterator
from typing import cast

import pytest

from session_alert_store import clear_default_session_alert_store_cache
from tests.api_alert_test_support import (
    assert_request_validation_payload,
    build_internal_error_payload,
    build_session_not_found_payload,
    build_validation_error_payload,
)
from session_alert_store_runtime_config import ALERT_STORE_BACKEND_ENV
from session_alerts import SessionAlertsNotFoundError
from tests.api_boundary_test_support import request
from tests.mcp_alert_test_support import call_mcp_tool
from tests.mcp_server_alerts_test_support import assert_mcp_tool_success
from tests.session_alert_test_support import (
    AlertLogRow,
    FailingReadAlertStore,
    REAL_POSTGRES_ALERT_STORE_SMOKE_ENABLED,
    StaticAlertStore,
    build_alert_event,
    build_alert_summary_payload,
    build_live_runtime_postgres_store,
    build_normalized_alert,
    build_persisted_alert,
    build_unique_session_id,
    close_store_if_possible,
    configure_session_alert_test,
    install_runtime_postgres_bootstrap_failure,
    select_runtime_postgres_store,
    write_known_session,
)


@pytest.fixture(autouse=True)
def _clear_default_alert_store_cache() -> Iterator[None]:
    """Keep runtime-selected default-store caching isolated in route tests."""
    clear_default_session_alert_store_cache()
    yield
    clear_default_session_alert_store_cache()


def _write_real_alert_session(
    monkeypatch,
    tmp_path,
    *,
    session_id: str,
    alert_rows: list[AlertLogRow],
) -> None:
    """Persist one real session for raw FastAPI and MCP boundary tests."""
    session_root = configure_session_alert_test(monkeypatch, tmp_path)
    write_known_session(session_root, session_id, alert_rows=alert_rows)


def _empty_alert_list_payload(session_id: str) -> dict[str, object]:
    """Return the stable empty raw-alert list payload for one session."""
    return {
        "session_id": session_id,
        "alerts": [],
    }


def _empty_alert_summary_payload(session_id: str) -> dict[str, object]:
    """Return the stable empty raw-alert summary payload for one session."""
    return cast(
        dict[str, object],
        build_alert_summary_payload(
            session_id,
            total_alerts=0,
            counts_by_detector={},
            counts_by_severity={},
            first_alert_timestamp_utc=None,
            last_alert_timestamp_utc=None,
        ),
    )


def _assert_runtime_postgres_bootstrap_failure_response(route_path: str) -> None:
    """Assert the stable raw-alert `500` envelope for one bootstrap failure."""
    response = request("GET", route_path)

    assert response.status_code == 500
    assert response.json() == build_internal_error_payload("postgres bootstrap failed")


# Happy-path adapter behavior


def test_get_session_alerts_returns_filtered_response(monkeypatch) -> None:
    """The HTTP list route should forward filters and preserve response shape."""

    def fake_filter_session_alert_events(
        session_id: str,
        *,
        detector_id: str | None = None,
        severity: str | None = None,
        start_time_utc: str | None = None,
        end_time_utc: str | None = None,
    ) -> list[dict[str, object]]:
        assert session_id == "session-123"
        assert detector_id == "video_metrics"
        assert severity == "warning"
        assert start_time_utc == "2026-05-06 10:00:00"
        assert end_time_utc == "2026-05-06 10:05:00"
        return [
            {
                "session_id": session_id,
                "timestamp_utc": "2026-05-06 10:00:10",
                "detector_id": "video_metrics",
                "title": "Black screen detected",
                "message": "Black segment.",
                "severity": "warning",
                "source_name": "segment_0001.ts",
            }
        ]

    monkeypatch.setattr(
        "api.routers.alerts.filter_session_alert_events",
        fake_filter_session_alert_events,
    )

    response = request(
        "GET",
        (
            "/sessions/session-123/alerts"
            "?detector_id=video_metrics"
            "&severity=warning"
            "&start_time_utc=2026-05-06%2010:00:00"
            "&end_time_utc=2026-05-06%2010:05:00"
        ),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["session_id"] == "session-123"
    assert len(payload["alerts"]) == 1
    assert payload["alerts"][0]["session_id"] == "session-123"
    assert payload["alerts"][0]["timestamp_utc"] == "2026-05-06 10:00:10"
    assert payload["alerts"][0]["detector_id"] == "video_metrics"
    assert payload["alerts"][0]["title"] == "Black screen detected"
    assert payload["alerts"][0]["message"] == "Black segment."
    assert payload["alerts"][0]["severity"] == "warning"
    assert payload["alerts"][0]["source_name"] == "segment_0001.ts"


def test_get_session_alert_summary_returns_deterministic_payload(monkeypatch) -> None:
    """The HTTP summary route should stay a thin adapter over the service seam."""

    def fake_summarize_session_alert_events(
        session_id: str,
        *,
        detector_id: str | None = None,
        severity: str | None = None,
        start_time_utc: str | None = None,
        end_time_utc: str | None = None,
    ) -> dict[str, object]:
        assert session_id == "session-123"
        assert detector_id == "video_metrics"
        assert severity == "warning"
        assert start_time_utc == "2026-05-06 10:00:00"
        assert end_time_utc == "2026-05-06 10:05:00"
        return {
            "session_id": session_id,
            "total_alerts": 1,
            "counts_by_detector": {"video_metrics": 1},
            "counts_by_severity": {"warning": 1},
            "first_alert_timestamp_utc": "2026-05-06 10:00:10",
            "last_alert_timestamp_utc": "2026-05-06 10:00:10",
        }

    monkeypatch.setattr(
        "api.routers.alerts.summarize_session_alert_events",
        fake_summarize_session_alert_events,
    )

    response = request(
        "GET",
        (
            "/sessions/session-123/alerts/summary"
            "?detector_id=video_metrics"
            "&severity=warning"
            "&start_time_utc=2026-05-06%2010:00:00"
            "&end_time_utc=2026-05-06%2010:05:00"
        ),
    )

    assert response.status_code == 200
    assert response.json() == {
        "session_id": "session-123",
        "total_alerts": 1,
        "counts_by_detector": {"video_metrics": 1},
        "counts_by_severity": {"warning": 1},
        "first_alert_timestamp_utc": "2026-05-06 10:00:10",
        "last_alert_timestamp_utc": "2026-05-06 10:00:10",
    }


def test_get_session_alerts_returns_stable_empty_payload(monkeypatch) -> None:
    """The raw list route should keep the same top-level shape when no alerts exist."""

    def fake_filter_session_alert_events(
        session_id: str,
        **_: object,
    ) -> list[dict[str, object]]:
        assert session_id == "empty-session"
        return []

    monkeypatch.setattr(
        "api.routers.alerts.filter_session_alert_events",
        fake_filter_session_alert_events,
    )

    response = request("GET", "/sessions/empty-session/alerts")

    assert response.status_code == 200
    assert response.json() == _empty_alert_list_payload("empty-session")


def test_get_session_alert_summary_returns_stable_empty_payload(monkeypatch) -> None:
    """The raw summary route should preserve all summary keys for an empty session."""

    def fake_summarize_session_alert_events(
        session_id: str,
        **_: object,
    ) -> dict[str, object]:
        assert session_id == "empty-session"
        return _empty_alert_summary_payload(session_id)

    monkeypatch.setattr(
        "api.routers.alerts.summarize_session_alert_events",
        fake_summarize_session_alert_events,
    )

    response = request("GET", "/sessions/empty-session/alerts/summary")

    assert response.status_code == 200
    assert response.json() == _empty_alert_summary_payload("empty-session")


def test_get_session_alerts_reads_the_real_file_backed_seam(
    monkeypatch,
    tmp_path,
) -> None:
    """The raw list route should work over persisted alert files without monkeypatched services."""
    _write_real_alert_session(
        monkeypatch,
        tmp_path,
        session_id="session-real-alert-list",
        alert_rows=[
            {
                "session_id": "session-real-alert-list",
                "timestamp_utc": "2026-05-06 10:00:00",
                "detector_id": "video_metrics",
                "title": "Black screen detected",
                "message": "Real persisted alert row.",
                "severity": "warning",
                "source_name": "segment_0001.ts",
            }
        ],
    )

    response = request("GET", "/sessions/session-real-alert-list/alerts")

    assert response.status_code == 200
    assert response.json() == {
        "session_id": "session-real-alert-list",
        "alerts": [
            build_normalized_alert(
                "session-real-alert-list",
                timestamp_utc="2026-05-06 10:00:00",
                detector_id="video_metrics",
                title="Black screen detected",
                message="Real persisted alert row.",
                severity="warning",
                source_name="segment_0001.ts",
            )
        ],
    }


def test_get_session_alert_summary_reads_the_real_file_backed_seam(
    monkeypatch,
    tmp_path,
) -> None:
    """The raw summary route should work over the real persisted alert seam."""
    _write_real_alert_session(
        monkeypatch,
        tmp_path,
        session_id="session-real-alert-summary",
        alert_rows=[
            {
                "session_id": "session-real-alert-summary",
                "timestamp_utc": "2026-05-06 10:00:00",
                "detector_id": "video_metrics",
                "title": "Black screen detected",
                "message": "First persisted alert row.",
                "severity": "warning",
                "source_name": "segment_0001.ts",
            },
            {
                "session_id": "session-real-alert-summary",
                "timestamp_utc": "2026-05-06 10:00:10",
                "detector_id": "video_blur",
                "title": "Blur increased",
                "message": "Second persisted alert row.",
                "severity": "info",
                "source_name": "segment_0002.ts",
            },
        ],
    )

    response = request("GET", "/sessions/session-real-alert-summary/alerts/summary")

    assert response.status_code == 200
    assert response.json() == build_alert_summary_payload(
        "session-real-alert-summary",
        total_alerts=2,
        counts_by_detector={"video_metrics": 1, "video_blur": 1},
        counts_by_severity={"warning": 1, "info": 1},
        first_alert_timestamp_utc="2026-05-06 10:00:00",
        last_alert_timestamp_utc="2026-05-06 10:00:10",
    )


@pytest.mark.parametrize(
    "route_path",
    [
        "/sessions/missing-real-alert-session/alerts",
        "/sessions/missing-real-alert-session/alerts/summary",
    ],
)
def test_raw_alert_routes_return_404_for_real_missing_sessions(
    monkeypatch,
    tmp_path,
    route_path: str,
) -> None:
    """Raw alert routes should map real missing sessions to the public 404 shape."""
    configure_session_alert_test(monkeypatch, tmp_path)

    response = request("GET", route_path)

    assert response.status_code == 404
    assert response.json() == build_session_not_found_payload(
        "missing-real-alert-session"
    )


def test_get_session_alerts_uses_runtime_selected_postgres_backend(
    monkeypatch,
) -> None:
    """The raw FastAPI route should honor Postgres runtime selection without caller churn."""
    store = StaticAlertStore(
        "session-runtime-postgres-api-alerts",
        [
            build_normalized_alert(
                "session-runtime-postgres-api-alerts",
                timestamp_utc="2026-05-19 19:00:00",
                detector_id="video_metrics",
                title="Runtime-selected alert",
                message="Served through the runtime-selected Postgres backend.",
                severity="warning",
                source_name="segment_0001.ts",
            )
        ],
    )
    select_runtime_postgres_store(monkeypatch, store)

    response = request("GET", "/sessions/session-runtime-postgres-api-alerts/alerts")

    assert response.status_code == 200
    assert response.json() == {
        "session_id": "session-runtime-postgres-api-alerts",
        "alerts": [
            build_normalized_alert(
                "session-runtime-postgres-api-alerts",
                timestamp_utc="2026-05-19 19:00:00",
                detector_id="video_metrics",
                title="Runtime-selected alert",
                message="Served through the runtime-selected Postgres backend.",
                severity="warning",
                source_name="segment_0001.ts",
            )
        ],
    }


@pytest.mark.parametrize(
    "route_path",
    [
        "/sessions/session-runtime-postgres-api-error/alerts",
        "/sessions/session-runtime-postgres-api-error/alerts/summary",
    ],
)
def test_raw_alert_routes_keep_the_same_bootstrap_failure_envelope(
    monkeypatch,
    route_path: str,
) -> None:
    """Raw alert routes should share the same runtime Postgres bootstrap-failure envelope."""
    install_runtime_postgres_bootstrap_failure(monkeypatch)

    _assert_runtime_postgres_bootstrap_failure_response(route_path)


def test_get_session_alerts_falls_back_to_file_backend_for_invalid_runtime_backend_env(
    monkeypatch,
    tmp_path,
) -> None:
    """Invalid backend env values should still keep the public boundary usable through file mode."""
    _write_real_alert_session(
        monkeypatch,
        tmp_path,
        session_id="session-invalid-runtime-backend-fallback",
        alert_rows=[
            build_persisted_alert(
                "session-invalid-runtime-backend-fallback",
                timestamp_utc="2026-05-19 21:40:00",
                detector_id="video_metrics",
                title="Fallback file alert",
                message="Served through file mode after invalid backend config.",
                severity="warning",
                source_name="segment_0001.ts",
            )
        ],
    )
    monkeypatch.setenv(ALERT_STORE_BACKEND_ENV, "not-a-real-backend")
    clear_default_session_alert_store_cache()

    response = request(
        "GET",
        "/sessions/session-invalid-runtime-backend-fallback/alerts",
    )

    assert response.status_code == 200
    assert response.json() == {
        "session_id": "session-invalid-runtime-backend-fallback",
        "alerts": [
            build_normalized_alert(
                "session-invalid-runtime-backend-fallback",
                timestamp_utc="2026-05-19 21:40:00",
                detector_id="video_metrics",
                title="Fallback file alert",
                message="Served through file mode after invalid backend config.",
                severity="warning",
                source_name="segment_0001.ts",
            )
        ],
    }


def test_get_session_alerts_returns_internal_error_when_runtime_postgres_read_fails_after_startup(
    monkeypatch,
) -> None:
    """A runtime-selected Postgres backend should surface read failures after successful startup."""

    select_runtime_postgres_store(
        monkeypatch,
        FailingReadAlertStore(
            "session-runtime-postgres-read-error",
            "database read failed",
        ),
    )

    response = request("GET", "/sessions/session-runtime-postgres-read-error/alerts")

    assert response.status_code == 500
    assert response.json() == build_internal_error_payload("database read failed")


@pytest.mark.skipif(
    not REAL_POSTGRES_ALERT_STORE_SMOKE_ENABLED,
    reason="Real PostgreSQL alert-route smoke test is opt-in.",
)
def test_live_runtime_postgres_alert_routes_follow_actual_startup_path(
    monkeypatch,
    tmp_path,
) -> None:
    """The real runtime-selected Postgres backend should drive raw FastAPI list and summary routes."""
    session_id = build_unique_session_id("session-runtime-postgres-api-live")
    store = build_live_runtime_postgres_store(
        monkeypatch,
        tmp_path,
        session_id=session_id,
    )
    try:
        store.append_alert(
            build_alert_event(
                session_id,
                timestamp_utc="2026-05-19 21:00:00",
                detector_id="video_metrics",
                title="Live API alert",
                message="Served through the real runtime-selected Postgres backend.",
                severity="warning",
                source_name="segment_0001.ts",
            )
        )

        list_response = request("GET", f"/sessions/{session_id}/alerts")
        summary_response = request("GET", f"/sessions/{session_id}/alerts/summary")
    finally:
        close_store_if_possible(store)

    assert list_response.status_code == 200
    assert list_response.json() == {
        "session_id": session_id,
        "alerts": [
            build_normalized_alert(
                session_id,
                timestamp_utc="2026-05-19 21:00:00",
                detector_id="video_metrics",
                title="Live API alert",
                message="Served through the real runtime-selected Postgres backend.",
                severity="warning",
                source_name="segment_0001.ts",
            )
        ],
    }
    assert summary_response.status_code == 200
    assert summary_response.json() == build_alert_summary_payload(
        session_id,
        total_alerts=1,
        counts_by_detector={"video_metrics": 1},
        counts_by_severity={"warning": 1},
        first_alert_timestamp_utc="2026-05-19 21:00:00",
        last_alert_timestamp_utc="2026-05-19 21:00:00",
    )


@pytest.mark.skipif(
    not REAL_POSTGRES_ALERT_STORE_SMOKE_ENABLED,
    reason="Real PostgreSQL alert-route smoke test is opt-in.",
)
def test_live_runtime_postgres_keeps_sessions_isolated_across_api_and_mcp(
    monkeypatch,
    tmp_path,
) -> None:
    """The real runtime-selected Postgres backend should not leak alerts across sessions."""
    session_id = build_unique_session_id("session-runtime-postgres-isolated")
    other_session_id = f"{session_id}-other"
    store = build_live_runtime_postgres_store(
        monkeypatch,
        tmp_path,
        session_id=session_id,
    )
    configure_session_alert_test(monkeypatch, tmp_path)
    write_known_session(tmp_path, other_session_id)
    try:
        store.append_alert(
            build_alert_event(
                session_id,
                timestamp_utc="2026-05-19 21:02:00",
                detector_id="video_metrics",
                title="Primary session alert",
                message="Should stay isolated to the primary session.",
                severity="warning",
                source_name="segment_0001.ts",
            )
        )
        store.append_alert(
            build_alert_event(
                other_session_id,
                timestamp_utc="2026-05-19 21:02:10",
                detector_id="video_blur",
                title="Other session alert",
                message="Should not leak into the primary session response.",
                severity="info",
                source_name="segment_0002.ts",
            )
        )

        response = request("GET", f"/sessions/{session_id}/alerts")
        mcp_result = call_mcp_tool(
            "query_session_alerts",
            {"session_id": session_id},
        )
    finally:
        close_store_if_possible(store)

    expected_payload = {
        "session_id": session_id,
        "alerts": [
            build_normalized_alert(
                session_id,
                timestamp_utc="2026-05-19 21:02:00",
                detector_id="video_metrics",
                title="Primary session alert",
                message="Should stay isolated to the primary session.",
                severity="warning",
                source_name="segment_0001.ts",
            )
        ],
    }
    assert response.status_code == 200
    assert response.json() == expected_payload
    assert_mcp_tool_success(
        mcp_result,
        expected_payload=cast(dict[str, object], expected_payload),
    )


@pytest.mark.skipif(
    not REAL_POSTGRES_ALERT_STORE_SMOKE_ENABLED,
    reason="Real PostgreSQL alert-route smoke test is opt-in.",
)
def test_live_runtime_postgres_preserves_unknown_session_boundary_contracts(
    monkeypatch,
    tmp_path,
) -> None:
    """Live Postgres mode should keep unknown-session behavior stable across API and MCP."""
    session_id = build_unique_session_id("session-runtime-postgres-known-anchor")
    missing_session_id = f"{session_id}-missing"
    store = build_live_runtime_postgres_store(
        monkeypatch,
        tmp_path,
        session_id=session_id,
    )
    try:
        response = request("GET", f"/sessions/{missing_session_id}/alerts")
        mcp_result = call_mcp_tool(
            "query_session_alerts",
            {"session_id": missing_session_id},
        )
    finally:
        close_store_if_possible(store)

    assert response.status_code == 404
    assert response.json() == build_session_not_found_payload(missing_session_id)
    from tests.mcp_server_alerts_test_support import assert_mcp_tool_error

    assert_mcp_tool_error(
        mcp_result,
        expected_message=f"Session not found: {missing_session_id}",
    )


@pytest.mark.skipif(
    not REAL_POSTGRES_ALERT_STORE_SMOKE_ENABLED,
    reason="Real PostgreSQL alert-route smoke test is opt-in.",
)
def test_live_runtime_postgres_preserves_mixed_detector_and_severity_counts_at_public_boundaries(
    monkeypatch,
    tmp_path,
) -> None:
    """The real runtime-selected Postgres backend should keep mixed summary counts stable."""
    session_id = build_unique_session_id("session-runtime-postgres-mixed-summary")
    store = build_live_runtime_postgres_store(
        monkeypatch,
        tmp_path,
        session_id=session_id,
    )
    try:
        store.append_alert(
            build_alert_event(
                session_id,
                timestamp_utc="2026-05-19 21:05:00",
                detector_id="video_metrics",
                title="Black screen detected",
                message="Warning detector row.",
                severity="warning",
                source_name="segment_0001.ts",
            )
        )
        store.append_alert(
            build_alert_event(
                session_id,
                timestamp_utc="2026-05-19 21:05:10",
                detector_id="video_blur",
                title="Blur increased",
                message="Info detector row.",
                severity="info",
                source_name="segment_0002.ts",
            )
        )
        store.append_alert(
            build_alert_event(
                session_id,
                timestamp_utc="2026-05-19 21:05:20",
                detector_id="video_metrics",
                title="Black screen detected",
                message="Second warning detector row.",
                severity="warning",
                source_name="segment_0003.ts",
            )
        )

        api_summary = request("GET", f"/sessions/{session_id}/alerts/summary")
        mcp_summary = call_mcp_tool(
            "summarize_session_alerts",
            {"session_id": session_id},
        )
    finally:
        close_store_if_possible(store)

    expected_summary = build_alert_summary_payload(
        session_id,
        total_alerts=3,
        counts_by_detector={"video_metrics": 2, "video_blur": 1},
        counts_by_severity={"warning": 2, "info": 1},
        first_alert_timestamp_utc="2026-05-19 21:05:00",
        last_alert_timestamp_utc="2026-05-19 21:05:20",
    )
    assert api_summary.status_code == 200
    assert api_summary.json() == expected_summary
    assert_mcp_tool_success(
        mcp_summary,
        expected_payload=cast(dict[str, object], expected_summary),
    )


@pytest.mark.skipif(
    not REAL_POSTGRES_ALERT_STORE_SMOKE_ENABLED,
    reason="Real PostgreSQL alert-route smoke test is opt-in.",
)
def test_live_runtime_postgres_raw_reads_handle_multiple_detectors_and_repeated_titles(
    monkeypatch,
    tmp_path,
) -> None:
    """Live Postgres raw reads should keep ordering and summary counts stable with repeated titles."""
    session_id = build_unique_session_id("session-runtime-postgres-raw-matrix")
    store = build_live_runtime_postgres_store(
        monkeypatch,
        tmp_path,
        session_id=session_id,
    )
    try:
        store.append_alert(
            build_alert_event(
                session_id,
                timestamp_utc="2026-05-19 21:06:00",
                detector_id="video_metrics",
                title="Repeated alert title",
                message="First repeated-title row.",
                severity="warning",
                source_name="segment_0001.ts",
            )
        )
        store.append_alert(
            build_alert_event(
                session_id,
                timestamp_utc="2026-05-19 21:06:10",
                detector_id="video_blur",
                title="Repeated alert title",
                message="Second repeated-title row from another detector.",
                severity="info",
                source_name="segment_0002.ts",
            )
        )
        store.append_alert(
            build_alert_event(
                session_id,
                timestamp_utc="2026-05-19 21:06:20",
                detector_id="video_metrics",
                title="Unique alert title",
                message="Third row keeps ordering stable.",
                severity="warning",
                source_name="segment_0003.ts",
            )
        )

        list_response = request("GET", f"/sessions/{session_id}/alerts")
        summary_response = request("GET", f"/sessions/{session_id}/alerts/summary")
    finally:
        close_store_if_possible(store)

    assert list_response.status_code == 200
    assert list_response.json() == {
        "session_id": session_id,
        "alerts": [
            build_normalized_alert(
                session_id,
                timestamp_utc="2026-05-19 21:06:00",
                detector_id="video_metrics",
                title="Repeated alert title",
                message="First repeated-title row.",
                severity="warning",
                source_name="segment_0001.ts",
            ),
            build_normalized_alert(
                session_id,
                timestamp_utc="2026-05-19 21:06:10",
                detector_id="video_blur",
                title="Repeated alert title",
                message="Second repeated-title row from another detector.",
                severity="info",
                source_name="segment_0002.ts",
            ),
            build_normalized_alert(
                session_id,
                timestamp_utc="2026-05-19 21:06:20",
                detector_id="video_metrics",
                title="Unique alert title",
                message="Third row keeps ordering stable.",
                severity="warning",
                source_name="segment_0003.ts",
            ),
        ],
    }
    assert summary_response.status_code == 200
    assert summary_response.json() == build_alert_summary_payload(
        session_id,
        total_alerts=3,
        counts_by_detector={"video_metrics": 2, "video_blur": 1},
        counts_by_severity={"warning": 2, "info": 1},
        first_alert_timestamp_utc="2026-05-19 21:06:00",
        last_alert_timestamp_utc="2026-05-19 21:06:20",
    )


def test_raw_alert_boundaries_preserve_optional_window_fields(
    monkeypatch,
    tmp_path,
) -> None:
    """FastAPI and MCP raw readers should preserve normalized optional window fields."""
    _write_real_alert_session(
        monkeypatch,
        tmp_path,
        session_id="session-real-window-fields",
        alert_rows=[
            build_persisted_alert(
                "session-real-window-fields",
                timestamp_utc="2026-05-06 10:00:00",
                detector_id="video_metrics",
                title="Windowed alert",
                message="Carries explicit window fields.",
                severity="warning",
                source_name="segment_0001.ts",
                window_index=3,
                window_start_sec=12.5,
            ),
            build_persisted_alert(
                "session-real-window-fields",
                timestamp_utc="2026-05-06 10:00:10",
                detector_id="video_blur",
                title="Windowless alert",
                message="Normalizes missing optional fields.",
                severity="info",
                source_name="segment_0002.ts",
            ),
        ],
    )
    expected_payload = {
        "session_id": "session-real-window-fields",
        "alerts": [
            build_normalized_alert(
                "session-real-window-fields",
                timestamp_utc="2026-05-06 10:00:00",
                detector_id="video_metrics",
                title="Windowed alert",
                message="Carries explicit window fields.",
                severity="warning",
                source_name="segment_0001.ts",
                window_index=3,
                window_start_sec=12.5,
            ),
            build_normalized_alert(
                "session-real-window-fields",
                timestamp_utc="2026-05-06 10:00:10",
                detector_id="video_blur",
                title="Windowless alert",
                message="Normalizes missing optional fields.",
                severity="info",
                source_name="segment_0002.ts",
                window_index=None,
                window_start_sec=None,
            ),
        ],
    }

    response = request("GET", "/sessions/session-real-window-fields/alerts")
    result = call_mcp_tool(
        "query_session_alerts",
        {"session_id": "session-real-window-fields"},
    )

    assert response.status_code == 200
    assert response.json() == expected_payload
    assert_mcp_tool_success(
        result,
        expected_payload=cast(dict[str, object], expected_payload),
    )


def test_get_session_alerts_accepts_detector_only_filter_with_empty_result(
    monkeypatch,
) -> None:
    """Detector-only filters should forward cleanly without changing the empty envelope."""

    def fake_filter_session_alert_events(
        session_id: str,
        *,
        detector_id: str | None = None,
        severity: str | None = None,
        start_time_utc: str | None = None,
        end_time_utc: str | None = None,
    ) -> list[dict[str, object]]:
        assert session_id == "session-123"
        assert detector_id == "video_metrics"
        assert severity is None
        assert start_time_utc is None
        assert end_time_utc is None
        return []

    monkeypatch.setattr(
        "api.routers.alerts.filter_session_alert_events",
        fake_filter_session_alert_events,
    )

    response = request(
        "GET",
        "/sessions/session-123/alerts?detector_id=video_metrics",
    )

    assert response.status_code == 200
    assert response.json() == _empty_alert_list_payload("session-123")


def test_get_session_alert_summary_accepts_severity_only_filter_with_empty_result(
    monkeypatch,
) -> None:
    """Severity-only filters should forward cleanly without changing the empty summary envelope."""

    def fake_summarize_session_alert_events(
        session_id: str,
        *,
        detector_id: str | None = None,
        severity: str | None = None,
        start_time_utc: str | None = None,
        end_time_utc: str | None = None,
    ) -> dict[str, object]:
        assert session_id == "session-123"
        assert detector_id is None
        assert severity == "warning"
        assert start_time_utc is None
        assert end_time_utc is None
        return _empty_alert_summary_payload(session_id)

    monkeypatch.setattr(
        "api.routers.alerts.summarize_session_alert_events",
        fake_summarize_session_alert_events,
    )

    response = request(
        "GET",
        "/sessions/session-123/alerts/summary?severity=warning",
    )

    assert response.status_code == 200
    assert response.json() == _empty_alert_summary_payload("session-123")


# Service-error mapping


def test_get_session_alerts_maps_missing_session_to_404(monkeypatch) -> None:
    """Service-level unknown-session errors should map to the API not-found contract."""

    def fake_filter_session_alert_events(
        session_id: str,
        **_: object,
    ) -> list[dict[str, object]]:
        raise SessionAlertsNotFoundError(session_id)

    monkeypatch.setattr(
        "api.routers.alerts.filter_session_alert_events",
        fake_filter_session_alert_events,
    )

    response = request("GET", "/sessions/missing-session/alerts")

    assert response.status_code == 404
    assert response.json() == build_session_not_found_payload("missing-session")


def test_get_session_alert_summary_maps_service_validation_to_400(monkeypatch) -> None:
    """Service validation errors should surface as domain-style 400 responses."""

    def fake_summarize_session_alert_events(
        session_id: str,
        **_: object,
    ) -> dict[str, object]:
        raise ValueError("start_time_utc must be earlier than or equal to end_time_utc")

    monkeypatch.setattr(
        "api.routers.alerts.summarize_session_alert_events",
        fake_summarize_session_alert_events,
    )

    response = request(
        "GET",
        (
            "/sessions/session-123/alerts/summary"
            "?start_time_utc=2026-05-06%2010:10:00"
            "&end_time_utc=2026-05-06%2010:00:00"
        ),
    )

    assert response.status_code == 400
    assert response.json() == build_validation_error_payload(
        "start_time_utc must be earlier than or equal to end_time_utc"
    )


def test_get_session_alert_summary_maps_missing_session_to_404(monkeypatch) -> None:
    """The raw summary route should keep the same not-found contract as the list route."""

    def fake_summarize_session_alert_events(
        session_id: str,
        **_: object,
    ) -> dict[str, object]:
        raise SessionAlertsNotFoundError(session_id)

    monkeypatch.setattr(
        "api.routers.alerts.summarize_session_alert_events",
        fake_summarize_session_alert_events,
    )

    response = request("GET", "/sessions/missing-session/alerts/summary")

    assert response.status_code == 404
    assert response.json() == build_session_not_found_payload("missing-session")


# Request validation


def test_get_session_alerts_rejects_invalid_severity_query_value() -> None:
    """FastAPI request validation should reject unsupported severity values early."""

    response = request("GET", "/sessions/session-123/alerts?severity=critical")

    assert response.status_code == 422
    assert_request_validation_payload(response.json(), field_name="severity")


def test_get_session_alert_summary_rejects_invalid_severity_query_value() -> None:
    """The summary route should enforce the same severity contract as the list route."""
    response = request("GET", "/sessions/session-123/alerts/summary?severity=critical")

    assert response.status_code == 422
    assert_request_validation_payload(response.json(), field_name="severity")
