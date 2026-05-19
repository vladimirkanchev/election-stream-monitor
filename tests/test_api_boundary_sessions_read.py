"""Focused FastAPI adapter tests for session read routes and snapshot parity.

This file now covers the Task-3 runtime wiring outcome: the general session
snapshot route should expose alerts from the active alert-store seam, not only
from the legacy local alert log.
"""

import json
from collections.abc import Iterator

import pytest

from session_alert_store import AlertEventPayload
from session_alert_store import clear_default_session_alert_store_cache
from tests.api_alert_test_support import build_internal_error_payload
from tests.session_alert_test_support import (
    FailingReadAlertStore,
    REAL_POSTGRES_ALERT_STORE_SMOKE_ENABLED,
    StaticAlertStore,
    build_alert_event,
    build_live_runtime_postgres_store,
    build_normalized_alert,
    build_unique_session_id,
    close_store_if_possible,
    install_runtime_postgres_session_alerts,
    select_runtime_postgres_store,
)

from tests.api_boundary_sessions_test_support import (
    session_not_found_payload,
    validation_error_payload,
)
from tests.api_boundary_test_support import request


@pytest.fixture(autouse=True)
def _clear_default_alert_store_cache() -> Iterator[None]:
    """Keep runtime-selected default-store caching isolated in session-route tests."""
    clear_default_session_alert_store_cache()
    yield
    clear_default_session_alert_store_cache()


def _snapshot_alert(
    session_id: str,
    *,
    timestamp_utc: str,
    detector_id: str = "video_metrics",
    title: str,
    message: str,
    severity: str = "warning",
    source_name: str,
) -> AlertEventPayload:
    """Build one normalized snapshot alert row for session-route runtime tests."""
    return build_normalized_alert(
        session_id,
        timestamp_utc=timestamp_utc,
        detector_id=detector_id,
        title=title,
        message=message,
        severity=severity,
        source_name=source_name,
    )


def test_sessions_missing_id() -> None:
    """Missing sessions should keep the stable route-level not-found payload."""
    response = request("GET", "/sessions/missing-session-id")
    assert response.status_code == 404
    assert response.json() == session_not_found_payload("missing-session-id")


def test_get_session_returns_fully_populated_snapshot(monkeypatch) -> None:
    """The session route should pass through the shared snapshot shape unchanged."""
    snapshot: dict[str, object] = {
        "session": {
            "session_id": "test-session-123",
            "mode": "video_files",
            "input_path": "/tmp/input.mp4",
            "selected_detectors": ["video_metrics"],
            "status": "running",
        },
        "progress": {
            "session_id": "test-session-123",
            "status": "running",
            "processed_count": 1,
            "total_count": 2,
            "current_item": "segment_001.ts",
            "latest_result_detector": "video_metrics",
            "latest_result_detectors": ["video_metrics"],
            "alert_count": 1,
            "last_updated_utc": "2026-04-18 10:00:00",
            "status_reason": "running",
            "status_detail": None,
        },
        "alerts": [
            {
                "session_id": "test-session-123",
                "timestamp_utc": "2026-04-18 10:00:00",
                "detector_id": "video_metrics",
                "title": "Black screen detected",
                "message": "Black segment exceeded threshold.",
                "severity": "warning",
                "source_name": "segment_001.ts",
            },
        ],
        "results": [
            {
                "session_id": "test-session-123",
                "detector_id": "video_metrics",
                "payload": {
                    "black_ratio": 0.8,
                    "longest_black_sec": 2.4,
                },
            },
        ],
        "latest_result": {
            "session_id": "test-session-123",
            "detector_id": "video_metrics",
            "payload": {
                "black_ratio": 0.8,
                "longest_black_sec": 2.4,
            },
        },
    }

    monkeypatch.setattr(
        "api.routers.sessions.read_session_snapshot_or_none",
        lambda session_id: snapshot,
    )

    response = request("GET", "/sessions/test-session-123")

    assert response.status_code == 200
    payload = response.json()
    assert payload["session"] == snapshot["session"]
    assert payload["progress"] == snapshot["progress"]
    assert payload["results"] == snapshot["results"]
    assert payload["latest_result"] == snapshot["latest_result"]
    assert payload["alerts"][0]["detector_id"] == "video_metrics"
    assert payload["alerts"][0]["source_name"] == "segment_001.ts"


def test_get_session_validation_failure_returns_structured_error(monkeypatch) -> None:
    """Route-level validation failures should keep the shared error envelope."""
    detail = "session directory requires a single safe path component"
    monkeypatch.setattr(
        "api.routers.sessions.read_session_snapshot_or_none",
        lambda session_id: (_ for _ in ()).throw(ValueError(detail)),
    )

    response = request("GET", "/sessions/bad-session-id")

    assert response.status_code == 400
    assert response.json() == validation_error_payload(detail)


def test_get_session_reads_snapshot_alerts_through_runtime_selected_postgres_backend(
    monkeypatch,
    tmp_path,
) -> None:
    """The session snapshot route should source alerts from the active runtime-selected store."""
    session_id = "session-runtime-postgres-snapshot"
    alerts = [
        _snapshot_alert(
            session_id,
            timestamp_utc="2026-05-19 23:00:00",
            title="Runtime-selected snapshot alert",
            message="Returned by the runtime-selected Postgres seam.",
            source_name="segment_0001.ts",
        )
    ]
    install_runtime_postgres_session_alerts(
        monkeypatch,
        tmp_path,
        session_id=session_id,
        alerts=alerts,
    )

    response = request("GET", f"/sessions/{session_id}")

    assert response.status_code == 200
    assert response.json()["alerts"] == alerts


def test_get_session_snapshot_alerts_match_the_dedicated_alert_route_in_postgres_mode(
    monkeypatch,
    tmp_path,
) -> None:
    """The session snapshot route and the raw alert route should agree in Postgres mode."""
    session_id = "session-runtime-postgres-snapshot-parity"
    alerts = [
        _snapshot_alert(
            session_id,
            timestamp_utc="2026-05-19 23:05:00",
            title="First parity alert",
            message="Shared through both snapshot and raw alert routes.",
            source_name="segment_0001.ts",
        ),
        _snapshot_alert(
            session_id,
            timestamp_utc="2026-05-19 23:05:10",
            detector_id="video_blur",
            title="Second parity alert",
            message="Shared through both snapshot and raw alert routes.",
            severity="info",
            source_name="segment_0002.ts",
        ),
    ]
    install_runtime_postgres_session_alerts(
        monkeypatch,
        tmp_path,
        session_id=session_id,
        alerts=alerts,
    )

    snapshot_response = request("GET", f"/sessions/{session_id}")
    alerts_response = request("GET", f"/sessions/{session_id}/alerts")

    assert snapshot_response.status_code == 200
    assert alerts_response.status_code == 200
    assert snapshot_response.json()["alerts"] == alerts
    assert alerts_response.json() == {
        "session_id": session_id,
        "alerts": alerts,
    }


def test_get_session_returns_internal_error_when_runtime_postgres_snapshot_read_fails(
    monkeypatch,
    tmp_path,
) -> None:
    """Unexpected seam-backed snapshot failures should surface through the API envelope."""
    session_id = "session-runtime-postgres-snapshot-error"
    install_runtime_postgres_session_alerts(
        monkeypatch,
        tmp_path,
        session_id=session_id,
        alerts=[],
    )
    select_runtime_postgres_store(
        monkeypatch,
        FailingReadAlertStore(session_id, "database read failed"),
    )

    response = request("GET", f"/sessions/{session_id}")

    assert response.status_code == 500
    assert response.json() == build_internal_error_payload("database read failed")


def test_get_session_snapshot_and_cli_read_session_stay_aligned_in_postgres_mode(
    monkeypatch,
    tmp_path,
    capsys,
) -> None:
    """The session API and CLI should expose the same snapshot alerts in Postgres mode."""
    import session_cli

    session_id = "session-runtime-postgres-cli-api-parity"
    alerts = [
        _snapshot_alert(
            session_id,
            timestamp_utc="2026-05-19 23:20:00",
            title="Shared snapshot alert",
            message="Visible through both CLI and FastAPI.",
            source_name="segment_0001.ts",
        )
    ]
    install_runtime_postgres_session_alerts(
        monkeypatch,
        tmp_path,
        session_id=session_id,
        alerts=alerts,
    )
    monkeypatch.setattr("sys.argv", ["session_cli.py", "read-session", "--session-id", session_id])
    session_cli.main()
    cli_payload = capsys.readouterr().out
    response = request("GET", f"/sessions/{session_id}")

    assert response.status_code == 200
    assert json.loads(cli_payload)["alerts"] == alerts
    assert response.json()["alerts"] == alerts


def test_get_session_snapshot_keeps_known_empty_alerts_aligned_with_dedicated_alert_route(
    monkeypatch,
    tmp_path,
) -> None:
    """Known sessions without alerts should stay aligned across snapshot and raw alert routes."""
    session_id = "session-runtime-postgres-known-empty"
    install_runtime_postgres_session_alerts(
        monkeypatch,
        tmp_path,
        session_id=session_id,
        alerts=[],
    )

    snapshot_response = request("GET", f"/sessions/{session_id}")
    alerts_response = request("GET", f"/sessions/{session_id}/alerts")

    assert snapshot_response.status_code == 200
    assert alerts_response.status_code == 200
    assert snapshot_response.json()["alerts"] == []
    assert alerts_response.json() == {
        "session_id": session_id,
        "alerts": [],
    }


@pytest.mark.skipif(
    not REAL_POSTGRES_ALERT_STORE_SMOKE_ENABLED,
    reason="Real PostgreSQL session-snapshot smoke test is opt-in.",
)
def test_live_runtime_postgres_session_snapshot_reads_alerts_from_the_active_backend(
    monkeypatch,
    tmp_path,
) -> None:
    """The real runtime-selected Postgres backend should drive the session snapshot route."""
    session_id = build_unique_session_id("session-runtime-postgres-snapshot-live")
    store = build_live_runtime_postgres_store(
        monkeypatch,
        tmp_path,
        session_id=session_id,
    )
    try:
        store.append_alert(
            build_alert_event(
                session_id,
                timestamp_utc="2026-05-19 23:25:00",
                detector_id="video_metrics",
                title="Live snapshot alert",
                message="Read through the live runtime-selected Postgres backend.",
                severity="warning",
                source_name="segment_0001.ts",
            )
        )
        response = request("GET", f"/sessions/{session_id}")
    finally:
        close_store_if_possible(store)

    assert response.status_code == 200
    assert response.json()["alerts"] == [
        build_normalized_alert(
            session_id,
            timestamp_utc="2026-05-19 23:25:00",
            detector_id="video_metrics",
            title="Live snapshot alert",
            message="Read through the live runtime-selected Postgres backend.",
            severity="warning",
            source_name="segment_0001.ts",
        )
    ]


def test_get_session_missing_keeps_the_same_not_found_contract_in_runtime_postgres_mode(
    monkeypatch,
) -> None:
    """Switching to Postgres mode should not change the session snapshot 404 contract."""
    select_runtime_postgres_store(
        monkeypatch,
        StaticAlertStore("session-runtime-postgres-anchor", []),
    )

    response = request("GET", "/sessions/session-runtime-postgres-missing")

    assert response.status_code == 404
    assert response.json() == session_not_found_payload("session-runtime-postgres-missing")


def test_get_session_snapshot_stays_consistent_with_grouped_timeline_in_postgres_mode(
    monkeypatch,
    tmp_path,
) -> None:
    """Snapshot alerts and grouped timeline responses should agree on the same Postgres-backed data."""
    session_id = "session-runtime-postgres-grouped-parity"
    alerts = [
        _snapshot_alert(
            session_id,
            timestamp_utc="2026-05-19 23:40:00",
            title="Grouped parity alert",
            message="Should align between snapshot and grouped views.",
            source_name="segment_0001.ts",
        ),
        _snapshot_alert(
            session_id,
            timestamp_utc="2026-05-19 23:40:10",
            title="Grouped parity alert",
            message="Second alert in the same grouped incident.",
            source_name="segment_0002.ts",
        ),
    ]
    install_runtime_postgres_session_alerts(
        monkeypatch,
        tmp_path,
        session_id=session_id,
        alerts=alerts,
    )

    snapshot_response = request("GET", f"/sessions/{session_id}")
    timeline_response = request("GET", f"/sessions/{session_id}/alerts/timeline")

    assert snapshot_response.status_code == 200
    assert timeline_response.status_code == 200
    assert len(snapshot_response.json()["alerts"]) == 2
    assert timeline_response.json() == {
        "session_id": session_id,
        "entries": [
            {
                "start_time_utc": "2026-05-19 23:40:00",
                "end_time_utc": "2026-05-19 23:40:10",
                "detector_id": "video_metrics",
                "severity": "warning",
                "title": "Grouped parity alert",
                "alert_count": 2,
                "source_names": ["segment_0001.ts", "segment_0002.ts"],
                "sample_message": "Should align between snapshot and grouped views.",
            }
        ],
    }
