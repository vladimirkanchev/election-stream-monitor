"""Runner-path alert seam tests, including runtime-selected Postgres confidence."""

from collections.abc import Iterator
from pathlib import Path
from typing import cast

import pytest
from tests.api_boundary_test_support import request
from tests.mcp_alert_test_support import call_mcp_tool
from tests.mcp_server_alerts_test_support import assert_mcp_tool_success
from tests.session_alert_test_support import (
    REAL_POSTGRES_ALERT_STORE_SMOKE_ENABLED,
    build_alert_summary_payload,
    build_normalized_alert,
    build_unique_session_id,
    close_store_if_possible,
)
from session_alert_store import (
    AlertEventPayload,
    clear_default_session_alert_store_cache,
    get_default_session_alert_store,
)
from session_alert_store_postgres_config import POSTGRES_ALERT_AUTO_CREATE_TABLES_ENV
from session_alert_store_runtime_config import ALERT_STORE_BACKEND_ENV
from session_io import initialize_session, read_session_snapshot
from session_alerts import read_session_alert_events
from session_models import AlertEvent, SessionMetadata, SessionProgress
import session_runner_execution
from tests.session_runner_execution_test_support import (
    build_metadata,
    build_progress,
    build_slice,
    configure_session_output,
    persist_session_state,
)

WarningAlertRow = tuple[str, str, str, str]


@pytest.fixture(autouse=True)
def _clear_default_alert_store_cache() -> Iterator[None]:
    """Keep runtime-selected default-store caching isolated in runner tests."""
    clear_default_session_alert_store_cache()
    yield
    clear_default_session_alert_store_cache()


def _identity_finalizer(**kwargs):
    """Return finalizer inputs unchanged for small execution-loop tests."""
    return kwargs["metadata"], kwargs["progress"]


def _configure_local_execution_session(
    monkeypatch,
    tmp_path: Path,
    *,
    session_id: str,
) -> tuple[SessionMetadata, SessionProgress]:
    """Create one isolated local execution session with persisted base state."""
    configure_session_output(monkeypatch, tmp_path)
    metadata = build_metadata(session_id=session_id)
    progress = build_progress(session_id=metadata.session_id)
    persist_session_state(metadata, progress)
    return metadata, progress


def _select_runtime_postgres_store(monkeypatch, store: "MemoryRuntimeAlertStore") -> None:
    """Route runner alert writes and reads through one patched Postgres-mode store."""
    monkeypatch.setenv(ALERT_STORE_BACKEND_ENV, "postgres")
    monkeypatch.setattr(
        "session_alert_store._build_postgres_default_session_alert_store",
        lambda: store,
    )
    clear_default_session_alert_store_cache()


def _enable_live_runtime_postgres_backend(monkeypatch) -> object:
    """Resolve the real default Postgres alert store for one opt-in runner test."""
    monkeypatch.setenv(ALERT_STORE_BACKEND_ENV, "postgres")
    monkeypatch.setenv(POSTGRES_ALERT_AUTO_CREATE_TABLES_ENV, "1")
    clear_default_session_alert_store_cache()
    return get_default_session_alert_store()


def _warning_alert_entry(
    session_id: str,
    *,
    timestamp_utc: str,
    title: str,
    message: str,
    source_name: str,
    detector_id: str = "video_metrics",
) -> dict[str, object]:
    """Build one small warning alert entry for execution-loop seam tests."""
    return {
        "session_id": session_id,
        "timestamp_utc": timestamp_utc,
        "detector_id": detector_id,
        "title": title,
        "message": message,
        "severity": "warning",
        "source_name": source_name,
    }


def _warning_alert_batch(
    session_id: str,
    *rows: WarningAlertRow,
) -> list[dict[str, object]]:
    """Build one small batch of warning alert entries for runner-path seam tests."""
    return [
        _warning_alert_entry(
            session_id,
            timestamp_utc=timestamp_utc,
            title=title,
            message=message,
            source_name=source_name,
        )
        for timestamp_utc, title, message, source_name in rows
    ]


def _normalized_warning_alert_batch(
    session_id: str,
    *rows: WarningAlertRow,
) -> list[AlertEventPayload]:
    """Build the normalized read shape for one batch of runner-written warning alerts."""
    return [
        build_normalized_alert(
            session_id,
            timestamp_utc=timestamp_utc,
            detector_id="video_metrics",
            title=title,
            message=message,
            severity="warning",
            source_name=source_name,
            window_index=None,
            window_start_sec=None,
        )
        for timestamp_utc, title, message, source_name in rows
    ]


class MemoryRuntimeAlertStore:
    """Small write-capable store for runner tests that switch to Postgres mode."""

    def __init__(self) -> None:
        """Keep normalized alert rows grouped by session id for seam assertions."""
        self._alerts_by_session: dict[str, list[AlertEventPayload]] = {}

    def append_alert(self, event: AlertEvent) -> None:
        """Persist one normalized alert row in memory for one session."""
        self._alerts_by_session.setdefault(event.session_id, []).append(
            build_normalized_alert(
                event.session_id,
                timestamp_utc=event.timestamp_utc,
                detector_id=event.detector_id,
                title=event.title,
                message=event.message,
                severity=event.severity,
                source_name=event.source_name,
                window_index=event.window_index,
                window_start_sec=event.window_start_sec,
            )
        )

    def read_session_alert_events(self, session_id: str) -> list[AlertEventPayload]:
        """Return the in-memory normalized alert rows for one session."""
        return list(self._alerts_by_session.get(session_id, []))


def test_run_analyzers_for_slice_filters_kwargs_for_simple_bundle_runner(
    tmp_path: Path,
) -> None:
    """Analyzer execution should keep older narrow bundle-runner doubles working."""
    analysis_slice = build_slice(tmp_path, "segment_0001.ts")
    observed: dict[str, object] = {}

    def simple_bundle_runner(file_path: Path, session_id: str) -> dict[str, list[dict[str, object]]]:
        observed["file_path"] = file_path
        observed["session_id"] = session_id
        return {"results": [], "alerts": []}

    bundle = session_runner_execution.run_analyzers_for_slice(
        analysis_slice=analysis_slice,
        mode="video_segments",
        session_id="session-execution-filtered",
        selected_detectors=["video_metrics"],
        bundle_runner=simple_bundle_runner,
    )

    assert bundle == {"results": [], "alerts": []}
    assert observed == {
        "file_path": analysis_slice.file_path,
        "session_id": "session-execution-filtered",
    }


def test_persist_bundle_events_appends_results_and_alerts(
    monkeypatch, tmp_path: Path
) -> None:
    """Persisting one bundle should append both result and alert payloads."""
    configure_session_output(monkeypatch, tmp_path)
    metadata = build_metadata(session_id="session-execution-persist", status="pending")
    initialize_session(metadata)

    session_runner_execution.persist_bundle_events(
        {
            "results": [
                {
                    "session_id": metadata.session_id,
                    "detector_id": "video_metrics",
                    "payload": {"source_name": "segment_0001.ts"},
                }
            ],
            "alerts": [
                {
                    "session_id": metadata.session_id,
                    "timestamp_utc": "2026-04-28 12:00:01",
                    "detector_id": "video_metrics",
                    "title": "Test Alert",
                    "message": "Something happened",
                    "severity": "warning",
                    "source_name": "segment_0001.ts",
                }
            ],
        }
    )

    snapshot = read_session_snapshot(metadata.session_id)
    results = cast(list[dict[str, object]], snapshot["results"])
    alerts = cast(list[dict[str, object]], snapshot["alerts"])
    latest_result = cast(dict[str, object], snapshot["latest_result"])

    assert len(results) == 1
    assert len(alerts) == 1
    assert latest_result["detector_id"] == "video_metrics"


def test_process_discovered_slices_cancels_before_processing_next_slice(
    monkeypatch, tmp_path: Path
) -> None:
    """Cancellation before the next slice should stop processing cleanly."""
    configure_session_output(monkeypatch, tmp_path)
    metadata = build_metadata(session_id="session-execution-cancel")
    progress = build_progress(session_id=metadata.session_id)
    persist_session_state(metadata, progress)

    slices = [build_slice(tmp_path, "segment_0001.ts")]
    monkeypatch.setattr(
        session_runner_execution,
        "is_session_cancel_requested",
        lambda session_id: session_id == metadata.session_id,
    )

    finalizer_calls: list[dict[str, object]] = []

    def fake_finalizer(**kwargs):
        finalizer_calls.append(kwargs)
        return kwargs["metadata"], kwargs["progress"]

    bundle_called = {"value": False}

    def fake_bundle_runner(**kwargs):
        bundle_called["value"] = True
        return {"results": [], "alerts": []}

    updated_metadata, updated_progress = session_runner_execution.process_discovered_slices(
        metadata=metadata,
        progress=progress,
        mode="video_segments",
        session_id=metadata.session_id,
        selected_detectors=["video_metrics"],
        input_slices=slices,
        bundle_runner=fake_bundle_runner,
        progress_builder=lambda **kwargs: progress,
        finalizer=fake_finalizer,
    )

    assert updated_metadata is metadata
    assert updated_progress is progress
    assert bundle_called["value"] is False
    assert finalizer_calls
    assert finalizer_calls[0]["status"] == "cancelled"
    assert finalizer_calls[0]["flush_stores"] is True


def test_process_discovered_slices_completes_and_writes_slice_progress(
    monkeypatch, tmp_path: Path
) -> None:
    """Successful finite-slice execution should update progress and finalize completed."""
    configure_session_output(monkeypatch, tmp_path)
    metadata = build_metadata(session_id="session-execution-local-complete")
    progress = build_progress(session_id=metadata.session_id)
    persist_session_state(metadata, progress)

    slices = [build_slice(tmp_path, "segment_0001.ts")]
    monkeypatch.setattr(session_runner_execution, "is_session_cancel_requested", lambda session_id: False)

    finalizer_calls: list[dict[str, object]] = []

    def fake_finalizer(**kwargs):
        finalizer_calls.append(kwargs)
        return kwargs["metadata"], kwargs["progress"]

    def fake_bundle_runner(**kwargs):
        return {
            "results": [
                {
                    "session_id": metadata.session_id,
                    "detector_id": "video_metrics",
                    "payload": {"source_name": "segment_0001.ts"},
                }
            ],
            "alerts": [],
        }

    def fake_progress_builder(**kwargs):
        return SessionProgress(
            session_id=metadata.session_id,
            status="running",
            processed_count=kwargs["processed_count"],
            total_count=kwargs["total_count"],
            current_item=kwargs["current_item"],
            latest_result_detector="video_metrics",
            alert_count=0,
            last_updated_utc="2026-04-28 12:00:02",
            latest_result_detectors=["video_metrics"],
            status_reason="running",
            status_detail=None,
        )

    session_runner_execution.process_discovered_slices(
        metadata=metadata,
        progress=progress,
        mode="video_segments",
        session_id=metadata.session_id,
        selected_detectors=["video_metrics"],
        input_slices=slices,
        bundle_runner=fake_bundle_runner,
        progress_builder=fake_progress_builder,
        finalizer=fake_finalizer,
    )

    snapshot = read_session_snapshot(metadata.session_id)
    progress_data = cast(dict[str, object], snapshot["progress"])

    assert progress_data["processed_count"] == 1
    assert progress_data["current_item"] == "segment_0001.ts"
    assert finalizer_calls[-1]["status"] == "completed"


def test_process_discovered_slices_persists_alerts_through_the_shared_alert_seam(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Finite-slice execution should write alerts that the shared read models can read back."""
    configure_session_output(monkeypatch, tmp_path)
    metadata = build_metadata(session_id="session-execution-alert-seam")
    progress = build_progress(session_id=metadata.session_id)
    persist_session_state(metadata, progress)

    slices = [build_slice(tmp_path, "segment_0001.ts")]
    monkeypatch.setattr(session_runner_execution, "is_session_cancel_requested", lambda session_id: False)

    def fake_finalizer(**kwargs):
        return kwargs["metadata"], kwargs["progress"]

    def fake_bundle_runner(**kwargs):
        return {
            "results": [],
            "alerts": [
                {
                    "session_id": metadata.session_id,
                    "timestamp_utc": "2026-05-06 10:00:00",
                    "detector_id": "video_metrics",
                    "title": "Black screen detected",
                    "message": "Persisted through process_discovered_slices.",
                    "severity": "warning",
                    "source_name": "segment_0001.ts",
                    "window_index": 0,
                    "window_start_sec": 0.0,
                }
            ],
        }

    session_runner_execution.process_discovered_slices(
        metadata=metadata,
        progress=progress,
        mode="video_segments",
        session_id=metadata.session_id,
        selected_detectors=["video_metrics"],
        input_slices=slices,
        bundle_runner=fake_bundle_runner,
        progress_builder=lambda **kwargs: progress,
        finalizer=fake_finalizer,
    )

    snapshot = read_session_snapshot(metadata.session_id)
    alerts = cast(list[dict[str, object]], snapshot["alerts"])

    assert alerts == [
        {
            "session_id": metadata.session_id,
            "timestamp_utc": "2026-05-06 10:00:00",
            "detector_id": "video_metrics",
            "title": "Black screen detected",
            "message": "Persisted through process_discovered_slices.",
            "severity": "warning",
            "source_name": "segment_0001.ts",
            "window_index": 0,
            "window_start_sec": 0.0,
        }
    ]


def test_process_discovered_slices_runner_written_alert_is_visible_through_fastapi_and_mcp(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Runner-persisted alerts should be readable through both public raw boundaries."""
    metadata, progress = _configure_local_execution_session(
        monkeypatch,
        tmp_path,
        session_id="session-execution-boundary-parity",
    )
    slices = [build_slice(tmp_path, "segment_0001.ts")]
    monkeypatch.setattr(
        session_runner_execution,
        "is_session_cancel_requested",
        lambda session_id: False,
    )

    def fake_bundle_runner(**kwargs):
        return {
            "results": [],
            "alerts": [
                _warning_alert_entry(
                    metadata.session_id,
                    timestamp_utc="2026-05-06 10:00:00",
                    title="Boundary-visible alert",
                    message="Persisted by the runner write path.",
                    source_name="segment_0001.ts",
                )
            ],
        }

    session_runner_execution.process_discovered_slices(
        metadata=metadata,
        progress=progress,
        mode="video_segments",
        session_id=metadata.session_id,
        selected_detectors=["video_metrics"],
        input_slices=slices,
        bundle_runner=fake_bundle_runner,
        progress_builder=lambda **kwargs: progress,
        finalizer=_identity_finalizer,
    )

    expected_payload = {
        "session_id": metadata.session_id,
        "alerts": [
            build_normalized_alert(
                metadata.session_id,
                timestamp_utc="2026-05-06 10:00:00",
                detector_id="video_metrics",
                title="Boundary-visible alert",
                message="Persisted by the runner write path.",
                severity="warning",
                source_name="segment_0001.ts",
                window_index=None,
                window_start_sec=None,
            )
        ],
    }
    response = request("GET", f"/sessions/{metadata.session_id}/alerts")
    mcp_result = call_mcp_tool(
        "query_session_alerts",
        {"session_id": metadata.session_id},
    )

    assert response.status_code == 200
    assert response.json() == expected_payload
    assert_mcp_tool_success(mcp_result, expected_payload=expected_payload)


def test_process_discovered_slices_runner_written_alert_is_visible_through_runtime_postgres_backend(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Runner-persisted alerts should stay readable when the runtime backend is switched to Postgres."""
    metadata, progress = _configure_local_execution_session(
        monkeypatch,
        tmp_path,
        session_id="session-execution-runtime-postgres-boundary-parity",
    )
    runtime_store = MemoryRuntimeAlertStore()
    _select_runtime_postgres_store(monkeypatch, runtime_store)
    slices = [build_slice(tmp_path, "segment_0001.ts")]
    monkeypatch.setattr(
        session_runner_execution,
        "is_session_cancel_requested",
        lambda session_id: False,
    )

    def fake_bundle_runner(**kwargs):
        return {
            "results": [],
            "alerts": [
                _warning_alert_entry(
                    metadata.session_id,
                    timestamp_utc="2026-05-06 10:05:00",
                    title="Runtime Postgres boundary alert",
                    message="Persisted by the runner through the runtime-selected backend.",
                    source_name="segment_0001.ts",
                )
            ],
        }

    session_runner_execution.process_discovered_slices(
        metadata=metadata,
        progress=progress,
        mode="video_segments",
        session_id=metadata.session_id,
        selected_detectors=["video_metrics"],
        input_slices=slices,
        bundle_runner=fake_bundle_runner,
        progress_builder=lambda **kwargs: progress,
        finalizer=_identity_finalizer,
    )

    expected_payload = {
        "session_id": metadata.session_id,
        "alerts": [
            build_normalized_alert(
                metadata.session_id,
                timestamp_utc="2026-05-06 10:05:00",
                detector_id="video_metrics",
                title="Runtime Postgres boundary alert",
                message="Persisted by the runner through the runtime-selected backend.",
                severity="warning",
                source_name="segment_0001.ts",
                window_index=None,
                window_start_sec=None,
            )
        ],
    }
    response = request("GET", f"/sessions/{metadata.session_id}/alerts")
    mcp_result = call_mcp_tool(
        "query_session_alerts",
        {"session_id": metadata.session_id},
    )

    assert response.status_code == 200
    assert response.json() == expected_payload
    assert_mcp_tool_success(mcp_result, expected_payload=expected_payload)


def test_process_discovered_slices_runtime_postgres_alerts_keep_fastapi_list_and_summary_aligned(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Runner-persisted alerts should keep the FastAPI list and summary routes aligned in Postgres mode."""
    metadata, progress = _configure_local_execution_session(
        monkeypatch,
        tmp_path,
        session_id="session-execution-runtime-postgres-api-summary",
    )
    runtime_store = MemoryRuntimeAlertStore()
    _select_runtime_postgres_store(monkeypatch, runtime_store)
    slices = [build_slice(tmp_path, "segment_0001.ts")]
    monkeypatch.setattr(
        session_runner_execution,
        "is_session_cancel_requested",
        lambda session_id: False,
    )

    alert_rows = (
        (
            "2026-05-06 10:06:00",
            "Runtime Postgres API summary alert",
            "First runner alert for list/summary coherence.",
            "segment_0001.ts",
        ),
        (
            "2026-05-06 10:06:10",
            "Runtime Postgres API summary alert",
            "Second runner alert for list/summary coherence.",
            "segment_0002.ts",
        ),
    )

    def fake_bundle_runner(**kwargs):
        return {
            "results": [],
            "alerts": _warning_alert_batch(metadata.session_id, *alert_rows),
        }

    session_runner_execution.process_discovered_slices(
        metadata=metadata,
        progress=progress,
        mode="video_segments",
        session_id=metadata.session_id,
        selected_detectors=["video_metrics"],
        input_slices=slices,
        bundle_runner=fake_bundle_runner,
        progress_builder=lambda **kwargs: progress,
        finalizer=_identity_finalizer,
    )

    list_response = request("GET", f"/sessions/{metadata.session_id}/alerts")
    summary_response = request("GET", f"/sessions/{metadata.session_id}/alerts/summary")

    assert list_response.status_code == 200
    assert list_response.json() == {
        "session_id": metadata.session_id,
        "alerts": _normalized_warning_alert_batch(metadata.session_id, *alert_rows),
    }
    assert summary_response.status_code == 200
    assert summary_response.json() == build_alert_summary_payload(
        metadata.session_id,
        total_alerts=2,
        counts_by_detector={"video_metrics": 2},
        counts_by_severity={"warning": 2},
        first_alert_timestamp_utc="2026-05-06 10:06:00",
        last_alert_timestamp_utc="2026-05-06 10:06:10",
    )


@pytest.mark.skipif(
    not REAL_POSTGRES_ALERT_STORE_SMOKE_ENABLED,
    reason="Real PostgreSQL runner/operator-flow smoke test is opt-in.",
)
def test_live_runtime_postgres_runner_written_alerts_stay_aligned_across_snapshot_and_api(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Runner-written alerts should stay consistent across snapshot and HTTP reads in live Postgres mode."""
    session_id = build_unique_session_id("session-execution-runtime-postgres-live")
    metadata, progress = _configure_local_execution_session(
        monkeypatch,
        tmp_path,
        session_id=session_id,
    )
    store = _enable_live_runtime_postgres_backend(monkeypatch)
    slices = [build_slice(tmp_path, "segment_0001.ts")]
    monkeypatch.setattr(
        session_runner_execution,
        "is_session_cancel_requested",
        lambda session_id: False,
    )

    alert_rows = (
        (
            "2026-05-20 09:00:00",
            "Live runtime alert",
            "First runner-written alert persisted through live Postgres.",
            "segment_0001.ts",
        ),
        (
            "2026-05-20 09:00:10",
            "Live runtime alert",
            "Second runner-written alert persisted through live Postgres.",
            "segment_0002.ts",
        ),
    )

    def fake_bundle_runner(**kwargs):
        return {
            "results": [],
            "alerts": _warning_alert_batch(metadata.session_id, *alert_rows),
        }

    try:
        session_runner_execution.process_discovered_slices(
            metadata=metadata,
            progress=progress,
            mode="video_segments",
            session_id=metadata.session_id,
            selected_detectors=["video_metrics"],
            input_slices=slices,
            bundle_runner=fake_bundle_runner,
            progress_builder=lambda **kwargs: progress,
            finalizer=_identity_finalizer,
        )
        snapshot = read_session_snapshot(metadata.session_id)
        list_response = request("GET", f"/sessions/{metadata.session_id}/alerts")
        summary_response = request(
            "GET",
            f"/sessions/{metadata.session_id}/alerts/summary",
        )
        timeline_response = request(
            "GET",
            f"/sessions/{metadata.session_id}/alerts/timeline",
        )
    finally:
        close_store_if_possible(store)

    expected_alerts = _normalized_warning_alert_batch(metadata.session_id, *alert_rows)

    assert snapshot["alerts"] == expected_alerts
    assert list_response.status_code == 200
    assert list_response.json() == {
        "session_id": metadata.session_id,
        "alerts": expected_alerts,
    }
    assert summary_response.status_code == 200
    assert summary_response.json() == build_alert_summary_payload(
        metadata.session_id,
        total_alerts=2,
        counts_by_detector={"video_metrics": 2},
        counts_by_severity={"warning": 2},
        first_alert_timestamp_utc="2026-05-20 09:00:00",
        last_alert_timestamp_utc="2026-05-20 09:00:10",
    )
    assert timeline_response.status_code == 200
    assert timeline_response.json() == {
        "session_id": metadata.session_id,
        "entries": [
            {
                "start_time_utc": "2026-05-20 09:00:00",
                "end_time_utc": "2026-05-20 09:00:10",
                "detector_id": "video_metrics",
                "severity": "warning",
                "title": "Live runtime alert",
                "alert_count": 2,
                "source_names": ["segment_0001.ts", "segment_0002.ts"],
                "sample_message": "First runner-written alert persisted through live Postgres.",
            }
        ],
    }


def test_process_discovered_slices_preserves_alert_append_order_in_raw_reads(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Runner writes should preserve append order even when timestamps are not sorted."""
    metadata, progress = _configure_local_execution_session(
        monkeypatch,
        tmp_path,
        session_id="session-execution-alert-order",
    )
    slices = [build_slice(tmp_path, "segment_0001.ts")]
    monkeypatch.setattr(
        session_runner_execution,
        "is_session_cancel_requested",
        lambda session_id: False,
    )

    def fake_bundle_runner(**kwargs):
        return {
            "results": [],
            "alerts": [
                _warning_alert_entry(
                    metadata.session_id,
                    timestamp_utc="2026-05-06 10:00:20",
                    title="Persisted first",
                    message="Written first.",
                    source_name="segment_0002.ts",
                ),
                _warning_alert_entry(
                    metadata.session_id,
                    timestamp_utc="2026-05-06 10:00:00",
                    title="Persisted second",
                    message="Written second.",
                    source_name="segment_0001.ts",
                ),
            ],
        }

    session_runner_execution.process_discovered_slices(
        metadata=metadata,
        progress=progress,
        mode="video_segments",
        session_id=metadata.session_id,
        selected_detectors=["video_metrics"],
        input_slices=slices,
        bundle_runner=fake_bundle_runner,
        progress_builder=lambda **kwargs: progress,
        finalizer=_identity_finalizer,
    )

    assert read_session_alert_events(metadata.session_id) == [
        build_normalized_alert(
            metadata.session_id,
            timestamp_utc="2026-05-06 10:00:20",
            detector_id="video_metrics",
            title="Persisted first",
            message="Written first.",
            severity="warning",
            source_name="segment_0002.ts",
            window_index=None,
            window_start_sec=None,
        ),
        build_normalized_alert(
            metadata.session_id,
            timestamp_utc="2026-05-06 10:00:00",
            detector_id="video_metrics",
            title="Persisted second",
            message="Written second.",
            severity="warning",
            source_name="segment_0001.ts",
            window_index=None,
            window_start_sec=None,
        ),
    ]


def test_process_discovered_slices_stops_persisting_alerts_after_cancel(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Cancellation before the next slice should prevent later alerts from being written."""
    metadata, progress = _configure_local_execution_session(
        monkeypatch,
        tmp_path,
        session_id="session-execution-cancelled-alerts",
    )
    slices = [
        build_slice(tmp_path, "segment_0001.ts"),
        build_slice(tmp_path, "segment_0002.ts"),
    ]
    cancel_checks = iter([False, True])
    monkeypatch.setattr(
        session_runner_execution,
        "is_session_cancel_requested",
        lambda session_id: next(cancel_checks),
    )

    finalizer_calls: list[dict[str, object]] = []
    bundle_calls: list[str] = []

    def fake_bundle_runner(analysis_slice, **kwargs):
        bundle_calls.append(analysis_slice.source_name)
        return {
            "results": [],
            "alerts": [
                _warning_alert_entry(
                    metadata.session_id,
                    timestamp_utc="2026-05-06 10:00:00",
                    title="Only persisted alert",
                    message="Should survive cancellation.",
                    source_name=analysis_slice.source_name,
                )
            ],
        }

    def recording_finalizer(**kwargs):
        finalizer_calls.append(kwargs)
        return _identity_finalizer(**kwargs)

    session_runner_execution.process_discovered_slices(
        metadata=metadata,
        progress=progress,
        mode="video_segments",
        session_id=metadata.session_id,
        selected_detectors=["video_metrics"],
        input_slices=slices,
        bundle_runner=fake_bundle_runner,
        progress_builder=lambda **kwargs: progress,
        finalizer=recording_finalizer,
    )

    assert bundle_calls == ["segment_0001.ts"]
    assert finalizer_calls[-1]["status"] == "cancelled"
    assert read_session_alert_events(metadata.session_id) == [
        build_normalized_alert(
            metadata.session_id,
            timestamp_utc="2026-05-06 10:00:00",
            detector_id="video_metrics",
            title="Only persisted alert",
            message="Should survive cancellation.",
            severity="warning",
            source_name="segment_0001.ts",
            window_index=None,
            window_start_sec=None,
        )
    ]


def test_process_discovered_slices_uses_default_progress_and_finalizer_helpers(
    monkeypatch, tmp_path: Path
) -> None:
    configure_session_output(monkeypatch, tmp_path)
    metadata = build_metadata(session_id="session-execution-default-helpers")
    progress = build_progress(session_id=metadata.session_id)
    persist_session_state(metadata, progress)
    slices = [build_slice(tmp_path, "segment_0001.ts")]

    monkeypatch.setattr(session_runner_execution, "is_session_cancel_requested", lambda session_id: False)

    progress_builder_calls: list[dict[str, object]] = []
    finalizer_calls: list[dict[str, object]] = []

    def fake_progress_builder(**kwargs):
        progress_builder_calls.append(kwargs)
        return progress

    def fake_finalizer(**kwargs):
        finalizer_calls.append(kwargs)
        return kwargs["metadata"], kwargs["progress"]

    monkeypatch.setattr(
        session_runner_execution.session_runner_progress,
        "build_slice_progress",
        fake_progress_builder,
    )
    monkeypatch.setattr(
        session_runner_execution.session_runner_terminal,
        "finalize_session_outcome",
        fake_finalizer,
    )

    session_runner_execution.process_discovered_slices(
        metadata=metadata,
        progress=progress,
        mode="video_segments",
        session_id=metadata.session_id,
        selected_detectors=["video_metrics"],
        input_slices=slices,
        bundle_runner=lambda **kwargs: {"results": [], "alerts": []},
    )

    assert progress_builder_calls
    assert finalizer_calls[-1]["status"] == "completed"
