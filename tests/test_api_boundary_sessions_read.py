"""Focused FastAPI tests for session read routes and snapshot contract stability.

This file covers the HTTP-facing snapshot contract used by the desktop polling
path, including store-backed progress reads, ordered result history, and
derived `latest_result` behavior.
"""

import json
from collections.abc import Iterator
from threading import Event, Thread

import pytest
import config

from session_alert_store import AlertEventPayload
from session_alert_store import clear_default_session_alert_store_cache
from session_io import append_result, initialize_session, write_session_progress
from session_models import ResultEvent, SessionMetadata, SessionProgress, SessionStatus
from session_store import SessionSnapshotPayload
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
    """Keep runtime-selected default-store caching isolated across route tests."""
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
    """Build one normalized alert row for session-route snapshot tests."""
    return build_normalized_alert(
        session_id,
        timestamp_utc=timestamp_utc,
        detector_id=detector_id,
        title=title,
        message=message,
        severity=severity,
        source_name=source_name,
    )


def _progress(
    *,
    session_id: str,
    processed_count: int,
    total_count: int,
    current_item: str,
    alert_count: int = 1,
    last_updated_utc: str | None = None,
    status: SessionStatus = "running",
) -> SessionProgress:
    """Build one route-facing progress payload for polling-contract tests."""
    return SessionProgress(
        session_id=session_id,
        status=status,
        processed_count=processed_count,
        total_count=total_count,
        current_item=current_item,
        latest_result_detector="video_metrics",
        alert_count=alert_count,
        last_updated_utc=last_updated_utc or f"2026-06-30 11:00:0{processed_count}",
        latest_result_detectors=["video_metrics"],
        status_reason=status,
        status_detail=None,
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


def test_get_session_reads_real_file_backed_snapshot_through_default_store(
    monkeypatch,
    tmp_path,
) -> None:
    """The session route should read the default file-backed snapshot end to end."""
    monkeypatch.setattr(config, "SESSION_OUTPUT_FOLDER", tmp_path)
    metadata = SessionMetadata(
        session_id="session-route-file-store",
        mode="video_files",
        input_path="/tmp/input.mp4",
        selected_detectors=["video_metrics"],
        status="running",
    )
    progress = SessionProgress(
        session_id=metadata.session_id,
        status="running",
        processed_count=1,
        total_count=2,
        current_item="clip.mp4 @ 00:00",
        latest_result_detector="video_metrics",
        alert_count=0,
        last_updated_utc="2026-06-29 10:00:00",
        latest_result_detectors=["video_metrics"],
        status_reason="running",
        status_detail=None,
    )
    result = ResultEvent(
        session_id=metadata.session_id,
        detector_id="video_metrics",
        payload={"source_name": "clip.mp4 @ 00:00", "window_index": 0},
    )
    initialize_session(metadata)
    write_session_progress(progress)
    append_result(result)

    response = request("GET", f"/sessions/{metadata.session_id}")

    assert response.status_code == 200
    assert response.json() == {
        "session": metadata.to_dict(),
        "progress": progress.to_dict(),
        "alerts": [],
        "results": [result.to_dict()],
        "latest_result": result.to_dict(),
    }


def test_get_session_reads_progress_through_default_session_store(monkeypatch) -> None:
    """The session route should expose store-backed progress without storage-specific drift."""
    expected_progress = _progress(
        session_id="session-route-store-progress",
        processed_count=7,
        total_count=9,
        current_item="live-window-007.ts",
        alert_count=2,
        last_updated_utc="2026-06-30 09:15:00",
    ).to_dict()

    class FakeStore:
        def read_snapshot(self, session_id: str) -> dict[str, object]:
            return {
                "session": {
                    "session_id": session_id,
                    "mode": "api_stream",
                    "input_path": "https://example.com/live/index.m3u8",
                    "selected_detectors": ["video_metrics"],
                    "status": "running",
                },
                "progress": expected_progress,
                "alerts": [],
                "results": [],
                "latest_result": None,
            }

    monkeypatch.setattr(
        "session_service.get_default_session_store",
        lambda: FakeStore(),
    )

    response = request("GET", "/sessions/session-route-store-progress")

    assert response.status_code == 200
    assert response.json()["progress"] == expected_progress


def test_get_session_keeps_store_backed_ordered_results_and_latest_result(monkeypatch) -> None:
    """The session route should preserve ordered results from the active store snapshot."""
    session_id = "session-route-store-results"
    expected_results = [
        {
            "session_id": session_id,
            "detector_id": "video_metrics",
            "payload": {
                "timestamp_utc": "2026-07-01 10:00:00",
                "source_name": "segment_0000.ts",
                "window_index": 0,
            },
        },
        {
            "session_id": session_id,
            "detector_id": "video_blur",
            "payload": {
                "timestamp_utc": "2026-07-01 10:00:00",
                "source_name": "segment_0001.ts",
                "window_index": 1,
            },
        },
    ]

    class FakeStore:
        def read_snapshot(self, read_session_id: str) -> dict[str, object]:
            return {
                "session": {
                    "session_id": read_session_id,
                    "mode": "video_segments",
                    "input_path": "/tmp/segments",
                    "selected_detectors": ["video_metrics", "video_blur"],
                    "status": "running",
                },
                "progress": None,
                "alerts": [],
                "results": expected_results,
                "latest_result": expected_results[-1],
            }

    monkeypatch.setattr(
        "session_service.get_default_session_store",
        lambda: FakeStore(),
    )

    response = request("GET", f"/sessions/{session_id}")

    assert response.status_code == 200
    assert response.json()["results"] == expected_results
    assert response.json()["latest_result"] == expected_results[-1]


def test_get_session_keeps_last_committed_progress_during_interleaved_store_update(
    monkeypatch,
) -> None:
    """The route should return a stable progress snapshot while a newer write is in flight."""
    session_id = "session-route-progress-race"
    first_progress = _progress(
        session_id=session_id,
        processed_count=2,
        total_count=5,
        current_item="segment_0002.ts",
        last_updated_utc="2026-06-30 11:00:02",
    )
    second_progress = _progress(
        session_id=session_id,
        processed_count=3,
        total_count=5,
        current_item="segment_0003.ts",
        last_updated_utc="2026-06-30 11:00:03",
    )
    first_progress_payload = first_progress.to_dict()
    second_progress_payload = second_progress.to_dict()
    write_errors: list[BaseException] = []

    class CoordinatedStore:
        def __init__(self) -> None:
            self._committed_progress = first_progress_payload
            self.write_started = Event()
            self.allow_commit = Event()

        def read_snapshot(self, read_session_id: str) -> SessionSnapshotPayload:
            return {
                "session": {
                    "session_id": read_session_id,
                    "mode": "video_segments",
                    "input_path": "/tmp/segments",
                    "selected_detectors": ["video_metrics"],
                    "status": "running",
                },
                "progress": self._committed_progress,
                "alerts": [],
                "results": [],
                "latest_result": None,
            }

        def write_progress(self, progress: SessionProgress) -> None:
            self.write_started.set()
            assert self.allow_commit.wait(timeout=1.0)
            self._committed_progress = progress.to_dict()

    store = CoordinatedStore()
    monkeypatch.setattr("session_service.get_default_session_store", lambda: store)

    def write_second_progress() -> None:
        try:
            store.write_progress(second_progress)
        except BaseException as error:
            write_errors.append(error)

    writer = Thread(target=write_second_progress)
    writer.start()
    assert store.write_started.wait(timeout=1.0)

    response_during_write = request("GET", f"/sessions/{session_id}")
    assert response_during_write.status_code == 200
    assert response_during_write.json()["progress"] == first_progress_payload

    store.allow_commit.set()
    writer.join(timeout=1.0)
    assert not writer.is_alive()
    assert write_errors == []

    response_after_write = request("GET", f"/sessions/{session_id}")
    assert response_after_write.status_code == 200
    assert response_after_write.json()["progress"] == second_progress_payload


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
