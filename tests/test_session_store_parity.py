"""Shared session-store contract checks for file and PostgreSQL-like backends."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import cast

import config
import pytest

from session_models import ResultEvent, SessionMetadata, SessionProgress, SessionStatus
from session_store import SESSION_SNAPSHOT_KEYS, SessionStore
from session_store_file import FileSessionStore
from session_store_postgres import PostgresSessionStore
from tests.session_store_postgres_test_support import InMemoryPostgresSessionStoreConnection


@pytest.fixture
def file_store(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> FileSessionStore:
    """Return an isolated file-backed store for parity checks."""
    monkeypatch.setattr(config, "SESSION_OUTPUT_FOLDER", tmp_path)
    return FileSessionStore()


@pytest.fixture
def postgres_store() -> PostgresSessionStore:
    """Return a PostgreSQL-like store backed by the shared in-memory double."""
    return PostgresSessionStore(InMemoryPostgresSessionStoreConnection())


@pytest.fixture(params=("file_store", "postgres_store"), ids=("file", "postgres"))
def session_store(request: pytest.FixtureRequest) -> SessionStore:
    """Return one backend from the shared parity matrix."""
    return cast(SessionStore, request.getfixturevalue(cast(str, request.param)))


def _metadata(session_id: str, *, status: SessionStatus) -> SessionMetadata:
    """Build representative session metadata for parity tests."""
    return SessionMetadata(
        session_id=session_id,
        mode="video_files",
        input_path="/tmp/clip.mp4",
        selected_detectors=["video_metrics"],
        status=status,
    )


def _running_progress(session_id: str) -> SessionProgress:
    """Build representative in-flight progress."""
    return SessionProgress(
        session_id=session_id,
        status="running",
        processed_count=2,
        total_count=5,
        current_item="segment_0002.ts",
        latest_result_detector="video_metrics",
        alert_count=1,
        last_updated_utc="2026-06-30 10:00:02",
        latest_result_detectors=["video_metrics"],
        status_reason="running",
        status_detail=None,
    )


def _terminal_progress(
    session_id: str,
    *,
    status: SessionStatus,
    processed_count: int,
    current_item: str | None,
    status_reason: str,
    status_detail: str | None,
) -> SessionProgress:
    """Build representative terminal progress."""
    return replace(
        SessionProgress.initial(session_id=session_id, total_count=5),
        status=status,
        processed_count=processed_count,
        current_item=current_item,
        latest_result_detector="video_metrics",
        latest_result_detectors=["video_metrics"],
        alert_count=1 if processed_count else 0,
        last_updated_utc="2026-06-30 10:00:05",
        status_reason=status_reason,
        status_detail=status_detail,
    )


def _result(
    session_id: str,
    detector_id: str,
    *,
    window_index: int,
    timestamp_utc: str,
) -> ResultEvent:
    """Build a representative detector result."""
    return ResultEvent(
        session_id=session_id,
        detector_id=detector_id,
        payload={
            "timestamp_utc": timestamp_utc,
            "detector_name": detector_id.replace("_", " ").title(),
            "source_name": f"segment_{window_index:04d}.ts",
            "window_index": window_index,
        },
    )


def _rich_result(
    session_id: str,
    detector_id: str,
    *,
    window_index: int,
    timestamp_utc: str,
) -> ResultEvent:
    """Build a richer detector result for payload-shape checks."""
    return ResultEvent(
        session_id=session_id,
        detector_id=detector_id,
        payload={
            "timestamp_utc": timestamp_utc,
            "detector_name": detector_id.replace("_", " ").title(),
            "source_name": f"segment_{window_index:04d}.ts",
            "window_index": window_index,
            "window_start_sec": float(window_index),
            "title": "Blur warning",
            "message": "Frame quality degraded in the sampled window.",
            "severity": "warning",
            "blur_score": 0.91,
            "blur_detected": True,
        },
    )


def _state_payloads(session_id: str) -> dict[str, tuple[SessionMetadata, SessionProgress]]:
    """Return shared metadata/progress pairs for key lifecycle states."""
    return {
        "running": (
            _metadata(session_id, status="running"),
            _running_progress(session_id),
        ),
        "completed": (
            _metadata(session_id, status="completed"),
            _terminal_progress(
                session_id,
                status="completed",
                processed_count=5,
                current_item="segment_0005.ts",
                status_reason="completed",
                status_detail="session completed",
            ),
        ),
        "failed": (
            _metadata(session_id, status="failed"),
            _terminal_progress(
                session_id,
                status="failed",
                processed_count=3,
                current_item="segment_0003.ts",
                status_reason="source_unreachable",
                status_detail="upstream returned HTTP 503",
            ),
        ),
        "cancelled": (
            _metadata(session_id, status="cancelled"),
            _terminal_progress(
                session_id,
                status="cancelled",
                processed_count=2,
                current_item=None,
                status_reason="cancel_requested",
                status_detail="Cancellation requested by client",
            ),
        ),
    }


def _persist_snapshot_state(
    store: SessionStore,
    *,
    metadata: SessionMetadata,
    progress: SessionProgress | None = None,
    progress_updates: list[SessionProgress] | None = None,
    results: list[ResultEvent] | None = None,
    cancel_requested: bool = False,
) -> dict[str, object]:
    """Write one test state and return the public snapshot."""
    store.write_metadata(metadata)
    if progress is not None:
        store.write_progress(progress)
    for progress_update in progress_updates or []:
        store.write_progress(progress_update)
    for result in results or []:
        store.append_result(result)
    if cancel_requested:
        store.request_cancel(metadata.session_id)
    return cast(dict[str, object], store.read_snapshot(metadata.session_id))


def _assert_frontend_visible_snapshot_contract(
    snapshot: dict[str, object],
    *,
    results: list[ResultEvent],
) -> None:
    """Assert the stable public snapshot shape."""
    assert tuple(snapshot.keys()) == SESSION_SNAPSHOT_KEYS
    assert isinstance(snapshot["alerts"], list)
    assert isinstance(snapshot["results"], list)
    assert "cancel_requested" not in snapshot
    assert "progress_history" not in snapshot

    expected_results = [result.to_dict() for result in results]
    assert snapshot["results"] == expected_results
    assert snapshot["latest_result"] == (expected_results[-1] if expected_results else None)


def _assert_snapshot_matches_written_state(
    snapshot: dict[str, object],
    *,
    metadata: SessionMetadata | None,
    progress: SessionProgress | None,
    results: list[ResultEvent],
) -> None:
    """Assert the snapshot matches the written contract state."""
    _assert_frontend_visible_snapshot_contract(snapshot, results=results)
    assert snapshot["session"] == (metadata.to_dict() if metadata is not None else None)
    assert snapshot["progress"] == (progress.to_dict() if progress is not None else None)


def _assert_snapshot_latest_result_matches_ordered_history(
    store: SessionStore,
    *,
    session_id: str,
    snapshot: dict[str, object],
) -> None:
    """Assert the shared latest-result rule."""
    ordered_results = cast(list[dict[str, object]], store.read_results(session_id))
    snapshot_results = cast(list[dict[str, object]], snapshot["results"])

    assert snapshot_results == ordered_results
    if not ordered_results:
        assert snapshot["latest_result"] is None
        return
    assert snapshot["latest_result"] == ordered_results[-1]
    assert snapshot["latest_result"] == snapshot_results[-1]


def _assert_store_results_match(
    store: SessionStore,
    *,
    session_id: str,
    snapshot: dict[str, object],
    results: list[ResultEvent],
) -> None:
    """Assert ordered result-history behavior."""
    expected_results = [result.to_dict() for result in results]

    assert store.read_results(session_id) == expected_results
    _assert_snapshot_latest_result_matches_ordered_history(
        store,
        session_id=session_id,
        snapshot=snapshot,
    )


def _assert_cancel_state_matches(store: SessionStore, session_id: str, expected: bool) -> None:
    """Assert durable cancel intent."""
    assert store.is_cancel_requested(session_id) is expected


def _prepare_cancel_state(store: SessionStore, *, session_id: str, state: str) -> None:
    """Prepare one lifecycle state before exercising cancel intent."""
    if state == "missing":
        return

    lifecycle_state = "cancelled" if state == "already_canceled" else state
    metadata, progress = _state_payloads(session_id)[lifecycle_state]
    _persist_snapshot_state(store, metadata=metadata, progress=progress)


def _exercise_cancel_signal(
    store: SessionStore,
    *,
    session_id: str,
    state: str,
) -> dict[str, object]:
    """Apply cancel intent once and return the resulting snapshot."""
    _prepare_cancel_state(store, session_id=session_id, state=state)
    if state == "already_canceled":
        store.request_cancel(session_id)
        _assert_cancel_state_matches(store, session_id, True)

    store.request_cancel(session_id)
    return cast(dict[str, object], store.read_snapshot(session_id))


def test_session_store_parity_keeps_missing_session_contract(
    session_store: SessionStore,
) -> None:
    """Missing sessions should read the same stable snapshot on every backend."""
    session_id = "session-parity-missing"
    snapshot = cast(dict[str, object], session_store.read_snapshot(session_id))

    assert session_store.session_exists(session_id) is False
    _assert_cancel_state_matches(session_store, session_id, False)
    _assert_snapshot_matches_written_state(
        snapshot,
        metadata=None,
        progress=None,
        results=[],
    )


def test_session_store_parity_returns_fresh_empty_lists_for_missing_session_reads(
    session_store: SessionStore,
) -> None:
    """Repeated missing-session reads should not share mutable alert/result lists."""
    session_id = "session-parity-missing-fresh-lists"
    first_snapshot = cast(dict[str, object], session_store.read_snapshot(session_id))
    second_snapshot = cast(dict[str, object], session_store.read_snapshot(session_id))

    cast(list[dict[str, object]], first_snapshot["alerts"]).append({"title": "example"})
    cast(list[dict[str, object]], first_snapshot["results"]).append(
        {
            "session_id": session_id,
            "detector_id": "video_metrics",
            "payload": {"source_name": "segment_0001.ts"},
        }
    )

    assert second_snapshot["alerts"] == []
    assert second_snapshot["results"] == []
    assert second_snapshot["latest_result"] is None


def test_session_store_parity_preserves_metadata_only_snapshot_contract(
    session_store: SessionStore,
) -> None:
    """Metadata writes should establish session identity without implying extra state."""
    metadata = SessionMetadata(
        session_id="session-parity-metadata-only",
        mode="video_files",
        input_path="/tmp/metadata-only.mp4",
        selected_detectors=["video_metrics", "video_blur"],
        status="pending",
    )

    snapshot = _persist_snapshot_state(session_store, metadata=metadata)

    assert session_store.session_exists(metadata.session_id) is True
    _assert_cancel_state_matches(session_store, metadata.session_id, False)
    _assert_snapshot_matches_written_state(
        snapshot,
        metadata=metadata,
        progress=None,
        results=[],
    )


@pytest.mark.parametrize(
    ("state", "expected_exists"),
    [
        ("missing", False),
        ("running", True),
        ("already_canceled", True),
        ("completed", True),
    ],
)
def test_session_store_parity_preserves_cancel_contract_across_lifecycle_states(
    state: str,
    expected_exists: bool,
    session_store: SessionStore,
) -> None:
    """Cancel intent should not alter snapshot shape or existence semantics."""
    session_id = f"session-parity-cancel-{state}"

    snapshot_before_repeat = _exercise_cancel_signal(
        session_store,
        session_id=session_id,
        state=state,
    )

    assert session_store.session_exists(session_id) is expected_exists
    _assert_cancel_state_matches(session_store, session_id, True)

    session_store.request_cancel(session_id)
    snapshot_after_repeat = cast(dict[str, object], session_store.read_snapshot(session_id))

    assert snapshot_after_repeat == snapshot_before_repeat


def test_session_store_parity_keeps_cancel_intent_out_of_public_snapshot_state(
    session_store: SessionStore,
) -> None:
    """Cancel intent alone should not rewrite the public snapshot."""
    session_id = "session-parity-cancel-read-model"
    metadata = _metadata(session_id, status="running")
    progress = _running_progress(session_id)
    results = [
        _result(
            session_id,
            "video_metrics",
            window_index=0,
            timestamp_utc="2026-07-01 10:00:00",
        ),
        _result(
            session_id,
            "video_blur",
            window_index=1,
            timestamp_utc="2026-07-01 10:00:01",
        ),
    ]

    snapshot_before_cancel = _persist_snapshot_state(
        session_store,
        metadata=metadata,
        progress=progress,
        results=results,
        cancel_requested=False,
    )

    session_store.request_cancel(session_id)
    snapshot_after_cancel = cast(dict[str, object], session_store.read_snapshot(session_id))

    _assert_cancel_state_matches(session_store, session_id, True)
    assert snapshot_after_cancel == snapshot_before_cancel
    _assert_snapshot_matches_written_state(
        snapshot_after_cancel,
        metadata=metadata,
        progress=progress,
        results=results,
    )


@pytest.mark.parametrize("state", ("running", "completed", "failed", "cancelled"))
def test_session_store_parity_preserves_progress_contract_across_lifecycle_states(
    state: str,
    session_store: SessionStore,
) -> None:
    """Lifecycle progress snapshots should stay identical to the shared contract."""
    session_id = f"session-parity-{state}"
    metadata, progress = _state_payloads(session_id)[state]
    snapshot = _persist_snapshot_state(session_store, metadata=metadata, progress=progress)

    assert session_store.session_exists(session_id) is True
    _assert_snapshot_matches_written_state(
        snapshot,
        metadata=metadata,
        progress=progress,
        results=[],
    )


def test_session_store_parity_treats_progress_as_latest_state_not_history(
    session_store: SessionStore,
) -> None:
    """The store should expose only the last written progress payload."""
    session_id = "session-parity-progress-latest-only"
    metadata = _metadata(session_id, status="running")
    newer_progress = replace(
        _running_progress(session_id),
        processed_count=4,
        current_item="segment_0004.ts",
        alert_count=2,
        last_updated_utc="2026-06-30 10:00:04",
    )
    stale_progress = replace(
        _running_progress(session_id),
        processed_count=1,
        current_item="segment_0001.ts",
        alert_count=0,
        last_updated_utc="2026-06-30 09:59:59",
        status_detail="stale progress overwrite example",
    )

    snapshot = _persist_snapshot_state(
        session_store,
        metadata=metadata,
        progress_updates=[newer_progress, stale_progress],
    )

    assert session_store.session_exists(session_id) is True
    _assert_snapshot_matches_written_state(
        snapshot,
        metadata=metadata,
        progress=stale_progress,
        results=[],
    )


@pytest.mark.parametrize(
    ("state", "include_progress", "include_results", "cancel_requested"),
    [
        ("running", True, True, False),
        ("completed", True, True, False),
        ("failed", True, True, False),
        ("cancelled", True, True, True),
        ("running", False, False, False),
    ],
)
def test_session_store_parity_preserves_frontend_visible_snapshot_shape(
    state: str,
    include_progress: bool,
    include_results: bool,
    cancel_requested: bool,
    session_store: SessionStore,
) -> None:
    """Every backend should expose the same public snapshot contract."""
    session_id = f"session-parity-snapshot-{state}-{'partial' if not include_progress else 'full'}"
    metadata, progress = _state_payloads(session_id)[state]
    results = (
        [
            _result(
                session_id,
                "video_metrics",
                window_index=1,
                timestamp_utc="2026-07-01 10:00:01",
            ),
            _result(
                session_id,
                "video_blur",
                window_index=2,
                timestamp_utc="2026-07-01 10:00:02",
            ),
        ]
        if include_results
        else []
    )

    snapshot = _persist_snapshot_state(
        session_store,
        metadata=metadata,
        progress=progress if include_progress else None,
        results=results,
        cancel_requested=cancel_requested,
    )

    _assert_snapshot_matches_written_state(
        snapshot,
        metadata=metadata,
        progress=progress if include_progress else None,
        results=results,
    )
    assert session_store.is_cancel_requested(session_id) is cancel_requested


def test_session_store_parity_preserves_ordered_result_history(
    session_store: SessionStore,
) -> None:
    """Ordered result appends should read back through the shared store contract."""
    session_id = "session-parity-results"
    metadata = _metadata(session_id, status="running")
    results = [
        _result(
            session_id,
            "video_metrics",
            window_index=0,
            timestamp_utc="2026-07-01 10:00:00",
        ),
        _result(
            session_id,
            "video_blur",
            window_index=1,
            timestamp_utc="2026-07-01 10:00:01",
        ),
    ]
    snapshot = _persist_snapshot_state(session_store, metadata=metadata, results=results)

    _assert_snapshot_matches_written_state(
        snapshot,
        metadata=metadata,
        progress=None,
        results=results,
    )
    _assert_store_results_match(
        session_store,
        session_id=session_id,
        snapshot=snapshot,
        results=results,
    )


@pytest.mark.parametrize(
    ("case_name", "result_specs"),
    [
        (
            "same-timestamp",
            [
                ("video_metrics", 0, "2026-07-01 10:00:00"),
                ("video_blur", 1, "2026-07-01 10:00:00"),
            ],
        ),
        (
            "regressive-timestamps",
            [
                ("video_metrics", 3, "2026-07-01 10:00:03"),
                ("video_blur", 1, "2026-07-01 09:59:59"),
                ("video_metrics", 2, "2026-07-01 10:00:01"),
            ],
        ),
    ],
    ids=("same-timestamp", "regressive-timestamps"),
)
def test_session_store_parity_uses_append_order_for_timestamp_edge_cases(
    case_name: str,
    result_specs: list[tuple[str, int, str]],
    session_store: SessionStore,
) -> None:
    """Append order, not timestamp sorting, should define `latest_result`."""
    session_id = f"session-parity-results-{case_name}"
    metadata = _metadata(session_id, status="running")
    results = [
        _result(session_id, detector_id, window_index=window_index, timestamp_utc=timestamp_utc)
        for detector_id, window_index, timestamp_utc in result_specs
    ]
    snapshot = _persist_snapshot_state(session_store, metadata=metadata, results=results)

    _assert_snapshot_matches_written_state(
        snapshot,
        metadata=metadata,
        progress=None,
        results=results,
    )
    _assert_store_results_match(
        session_store,
        session_id=session_id,
        snapshot=snapshot,
        results=results,
    )
    assert snapshot["latest_result"] == results[-1].to_dict()


def test_session_store_parity_preserves_rich_result_payload_shape(
    session_store: SessionStore,
) -> None:
    """Each backend should preserve shared hints and detector-specific payload detail."""
    session_id = "session-parity-results-rich-payload"
    metadata = _metadata(session_id, status="running")
    results = [
        _rich_result(
            session_id,
            "video_blur",
            window_index=7,
            timestamp_utc="2026-07-01 10:00:07",
        ),
        _rich_result(
            session_id,
            "video_metrics",
            window_index=8,
            timestamp_utc="2026-07-01 10:00:08",
        ),
    ]
    snapshot = _persist_snapshot_state(session_store, metadata=metadata, results=results)

    _assert_snapshot_matches_written_state(
        snapshot,
        metadata=metadata,
        progress=None,
        results=results,
    )
    _assert_store_results_match(
        session_store,
        session_id=session_id,
        snapshot=snapshot,
        results=results,
    )
    snapshot_results = cast(list[dict[str, object]], snapshot["results"])
    first_payload = cast(dict[str, object], snapshot_results[0]["payload"])
    assert first_payload["blur_score"] == 0.91
    assert first_payload["severity"] == "warning"
