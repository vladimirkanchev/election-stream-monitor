"""Focused contract and bootstrap tests for the PostgreSQL session-store adapter."""

from __future__ import annotations

from types import ModuleType
from typing import Any, cast

import pytest

from session_models import ResultEvent, SessionMetadata, SessionProgress
from session_store import SESSION_SNAPSHOT_KEYS, SessionStore, build_session_snapshot_payload
from session_store_postgres import (
    POSTGRES_SESSION_CANCEL_FIELDS,
    POSTGRES_SESSION_CANCEL_TABLE_NAME,
    POSTGRES_SESSION_CANCEL_TABLE_SQL,
    POSTGRES_SESSION_METADATA_FIELDS,
    POSTGRES_SESSION_METADATA_TABLE_NAME,
    POSTGRES_SESSION_METADATA_TABLE_SQL,
    POSTGRES_SESSION_RESULTS_INSERT_SQL,
    POSTGRES_SESSION_RESULTS_SELECT_SQL,
    PostgresSessionStore,
    POSTGRES_SESSION_PROGRESS_FIELDS,
    POSTGRES_SESSION_PROGRESS_TABLE_NAME,
    POSTGRES_SESSION_PROGRESS_TABLE_SQL,
    POSTGRES_SESSION_RESULT_FIELDS,
    POSTGRES_SESSION_RESULTS_TABLE_NAME,
    POSTGRES_SESSION_RESULTS_TABLE_SQL,
    POSTGRES_SESSION_STORE_METHOD_TABLE_MAP,
    POSTGRES_SESSION_STORE_SCHEMA_DROP_STATEMENTS,
    POSTGRES_SESSION_STORE_SCHEMA_STATEMENTS,
    POSTGRES_SESSION_STORE_TABLE_SPECS,
    PostgresSessionStoreBootstrapError,
    bootstrap_postgres_session_store,
    connect_postgres_session_store,
    drop_postgres_session_store_schema,
    initialize_postgres_session_store,
    load_postgres_session_store_driver,
    reset_postgres_session_store_schema,
)
from session_store_postgres_config import PostgresSessionStoreSettings
from tests import session_store_postgres_test_support
from tests.session_store_postgres_test_support import (
    InMemoryPostgresSessionStoreConnection,
    REAL_POSTGRES_SESSION_STORE_SMOKE_ENABLED,
    build_isolated_postgres_session_store,
    bootstrap_isolated_postgres_session_store,
    close_postgres_session_store_connection_if_possible,
)

VALID_POSTGRES_SESSION_URL = "postgresql://session:secret@db.example/esm"


def _metadata(
    session_id: str,
    *,
    status: str = "running",
    input_path: str = "/tmp/clip.mp4",
) -> SessionMetadata:
    """Build representative metadata for adapter tests."""
    return SessionMetadata(
        session_id=session_id,
        mode="video_files",
        input_path=input_path,
        selected_detectors=["video_metrics"],
        status=cast(Any, status),
    )


def _running_progress(session_id: str, *, processed_count: int) -> SessionProgress:
    """Build representative progress for adapter tests."""
    return SessionProgress(
        session_id=session_id,
        status="running",
        processed_count=processed_count,
        total_count=3,
        current_item=f"segment_{processed_count:04d}.ts",
        latest_result_detector="video_metrics",
        alert_count=processed_count,
        last_updated_utc=f"2026-06-29 10:00:0{processed_count}",
        latest_result_detectors=["video_metrics"],
        status_reason="running",
        status_detail=None,
    )


def _result(session_id: str, detector_id: str, window_index: int) -> ResultEvent:
    """Build one ordered result event for adapter tests."""
    return ResultEvent(
        session_id=session_id,
        detector_id=detector_id,
        payload={"source_name": f"clip.mp4 @ 00:0{window_index}", "window_index": window_index},
    )


def _assert_snapshot_contract_shape(snapshot: dict[str, object]) -> None:
    """Assert the stable public snapshot key set."""
    assert tuple(snapshot.keys()) == SESSION_SNAPSHOT_KEYS
    assert set(snapshot) == set(SESSION_SNAPSHOT_KEYS)


def _assert_store_round_trip_contract(store: SessionStore, session_id: str) -> None:
    """Assert the core round-trip contract shared by all backends."""
    metadata = _metadata(session_id, status="running")
    progress = _running_progress(session_id, processed_count=2)
    first = _result(session_id, "video_metrics", 1)
    second = _result(session_id, "video_blur", 2)
    expected_results = [first.to_dict(), second.to_dict()]

    store.write_metadata(metadata)
    store.write_progress(progress)
    store.append_result(first)
    store.append_result(second)

    snapshot = store.read_snapshot(session_id)
    _assert_snapshot_contract_shape(snapshot)
    assert store.session_exists(session_id) is True
    assert store.read_results(session_id) == expected_results
    assert snapshot == build_session_snapshot_payload(
        session=metadata.to_dict(),
        progress=progress.to_dict(),
        alerts=[],
        results=expected_results,
    )


class RecordingCursor:
    """Cursor double that records executed statements."""

    def __init__(self, *, executed_statements: list[tuple[str, object | None]]) -> None:
        self._executed_statements = executed_statements

    def __enter__(self) -> "RecordingCursor":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: Any,
    ) -> None:
        return None

    def execute(self, query: str, params: object | None = None) -> object:
        self._executed_statements.append((query, params))
        return object()

    def fetchone(self) -> object | None:
        return None

    def fetchall(self) -> list[object]:
        return []


class RecordingConnection:
    """Connection double that records statements and commit activity."""

    def __init__(self) -> None:
        self.executed_statements: list[tuple[str, object | None]] = []
        self.committed = False
        self.commit_count = 0

    def cursor(self) -> RecordingCursor:
        return RecordingCursor(executed_statements=self.executed_statements)

    def commit(self) -> None:
        self.committed = True
        self.commit_count = getattr(self, "commit_count", 0) + 1


class FakePsycopgModule:
    """Small `psycopg`-shaped double for connection-path tests."""

    class Error(Exception):
        """Driver-shaped base error used by bootstrap tests."""

    def __init__(
        self,
        *,
        connection: RecordingConnection | None = None,
        connect_error: BaseException | None = None,
    ) -> None:
        self.connection = connection or RecordingConnection()
        self.connect_error = connect_error
        self.connect_calls: list[str] = []

    def connect(self, database_url: str) -> RecordingConnection:
        self.connect_calls.append(database_url)
        if self.connect_error is not None:
            raise self.connect_error
        return self.connection


class MidSchemaFailureCursor:
    """Cursor double that fails during bootstrap to prove commit behavior."""

    def __init__(self) -> None:
        self.calls = 0

    def __enter__(self) -> "MidSchemaFailureCursor":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: Any,
    ) -> None:
        return None

    def execute(self, query: str, params: object | None = None) -> object:
        self.calls += 1
        if self.calls == 2:
            raise RuntimeError("index creation failed")
        return object()


class MidSchemaFailureConnection:
    """Connection double that surfaces bootstrap failure before commit."""

    def __init__(self) -> None:
        self.committed = False
        self.cursor_instance = MidSchemaFailureCursor()

    def cursor(self) -> MidSchemaFailureCursor:
        return self.cursor_instance

    def commit(self) -> None:
        self.committed = True


def _postgres_settings(
    *,
    database_url: str | None = VALID_POSTGRES_SESSION_URL,
    auto_create_tables: bool = False,
) -> PostgresSessionStoreSettings:
    """Build bootstrap settings for focused PostgreSQL tests."""
    return PostgresSessionStoreSettings(
        database_url=database_url,
        auto_create_tables=auto_create_tables,
        real_smoke_enabled=False,
    )


def test_postgres_session_schema_constants_match_current_store_contract() -> None:
    """The schema should model metadata, latest progress, results, and cancel state."""
    assert POSTGRES_SESSION_METADATA_TABLE_NAME == "session_metadata"
    assert POSTGRES_SESSION_PROGRESS_TABLE_NAME == "session_progress"
    assert POSTGRES_SESSION_RESULTS_TABLE_NAME == "session_result_events"
    assert POSTGRES_SESSION_CANCEL_TABLE_NAME == "session_cancel_requests"
    assert "selected_detectors JSONB NOT NULL" in POSTGRES_SESSION_METADATA_TABLE_SQL
    assert "latest_result_detectors JSONB NOT NULL" in POSTGRES_SESSION_PROGRESS_TABLE_SQL
    assert "detector_name TEXT NULL" in POSTGRES_SESSION_RESULTS_TABLE_SQL
    assert "event_timestamp_utc TEXT NULL" in POSTGRES_SESSION_RESULTS_TABLE_SQL
    assert "payload_json JSONB NOT NULL" in POSTGRES_SESSION_RESULTS_TABLE_SQL
    assert "cancel_requested BOOLEAN NOT NULL" in POSTGRES_SESSION_CANCEL_TABLE_SQL
    assert "alerts" not in POSTGRES_SESSION_METADATA_TABLE_SQL.lower()
    assert "worker.log" not in POSTGRES_SESSION_PROGRESS_TABLE_SQL.lower()
    assert "cancel_requested" not in POSTGRES_SESSION_RESULTS_TABLE_SQL.lower()


def test_postgres_result_event_schema_stays_queryable_without_over_normalizing() -> None:
    """Result rows should project shared hints while keeping detector detail in JSON."""
    assert POSTGRES_SESSION_RESULT_FIELDS == (
        "id",
        "session_id",
        "detector_id",
        "detector_name",
        "event_timestamp_utc",
        "payload_json",
    )
    assert "payload_json AS payload" in POSTGRES_SESSION_RESULTS_SELECT_SQL
    assert (
        "session_id,\n    detector_id,\n    detector_name,\n    event_timestamp_utc,\n    payload_json"
        in POSTGRES_SESSION_RESULTS_INSERT_SQL
    )
    assert any(
        "session_id, detector_id, id" in statement
        for statement in POSTGRES_SESSION_STORE_SCHEMA_STATEMENTS
    )


def test_postgres_session_table_specs_follow_contract_concerns_not_file_inventory() -> None:
    """Table specs should model store concerns rather than raw file names."""
    assert len(POSTGRES_SESSION_STORE_TABLE_SPECS) == 4
    assert [
        spec.table_name for spec in POSTGRES_SESSION_STORE_TABLE_SPECS
    ] == [
        POSTGRES_SESSION_METADATA_TABLE_NAME,
        POSTGRES_SESSION_PROGRESS_TABLE_NAME,
        POSTGRES_SESSION_RESULTS_TABLE_NAME,
        POSTGRES_SESSION_CANCEL_TABLE_NAME,
    ]
    assert POSTGRES_SESSION_STORE_TABLE_SPECS[0].payload_fields == POSTGRES_SESSION_METADATA_FIELDS
    assert POSTGRES_SESSION_STORE_TABLE_SPECS[1].payload_fields == POSTGRES_SESSION_PROGRESS_FIELDS
    assert POSTGRES_SESSION_STORE_TABLE_SPECS[2].payload_fields == POSTGRES_SESSION_RESULT_FIELDS
    assert POSTGRES_SESSION_STORE_TABLE_SPECS[3].payload_fields == POSTGRES_SESSION_CANCEL_FIELDS
    assert all("alert" not in spec.table_name for spec in POSTGRES_SESSION_STORE_TABLE_SPECS)
    assert all("worker" not in spec.table_name for spec in POSTGRES_SESSION_STORE_TABLE_SPECS)


def test_postgres_session_method_table_map_stays_small_and_explicit() -> None:
    """Each store method should map to contract-owned tables only."""
    assert POSTGRES_SESSION_STORE_METHOD_TABLE_MAP == {
        "write_metadata": (POSTGRES_SESSION_METADATA_TABLE_NAME,),
        "session_exists": (POSTGRES_SESSION_METADATA_TABLE_NAME,),
        "write_progress": (POSTGRES_SESSION_PROGRESS_TABLE_NAME,),
        "append_result": (POSTGRES_SESSION_RESULTS_TABLE_NAME,),
        "read_results": (POSTGRES_SESSION_RESULTS_TABLE_NAME,),
        "request_cancel": (POSTGRES_SESSION_CANCEL_TABLE_NAME,),
        "is_cancel_requested": (POSTGRES_SESSION_CANCEL_TABLE_NAME,),
        "read_snapshot": (
            POSTGRES_SESSION_METADATA_TABLE_NAME,
            POSTGRES_SESSION_PROGRESS_TABLE_NAME,
            POSTGRES_SESSION_RESULTS_TABLE_NAME,
        ),
    }


def test_postgres_session_schema_keeps_progress_and_results_owned_by_metadata() -> None:
    """Dependent session rows should cascade from metadata rather than float alone."""
    assert (
        "FOREIGN KEY (session_id)\n"
        f"        REFERENCES {POSTGRES_SESSION_METADATA_TABLE_NAME} (session_id)\n"
        "        ON DELETE CASCADE"
    ) in POSTGRES_SESSION_PROGRESS_TABLE_SQL
    assert (
        "FOREIGN KEY (session_id)\n"
        f"        REFERENCES {POSTGRES_SESSION_METADATA_TABLE_NAME} (session_id)\n"
        "        ON DELETE CASCADE"
    ) in POSTGRES_SESSION_RESULTS_TABLE_SQL


def test_postgres_session_store_skeleton_keeps_only_injected_connection_state() -> None:
    """The adapter should stay small and connection-injected."""
    connection = RecordingConnection()

    store = PostgresSessionStore(connection)

    assert store.connection is connection
    assert vars(store) == {"_connection": connection}


def test_postgres_session_store_missing_metadata_keeps_empty_snapshot_contract() -> None:
    """Missing metadata should keep the stable empty snapshot shape."""
    store = PostgresSessionStore(InMemoryPostgresSessionStoreConnection())

    assert store.session_exists("session-missing") is False
    assert store.is_cancel_requested("session-missing") is False
    assert store.read_results("session-missing") == []
    assert store.read_snapshot("session-missing") == {
        "session": None,
        "progress": None,
        "alerts": [],
        "results": [],
        "latest_result": None,
    }


def test_postgres_session_store_preserves_storage_neutral_round_trip_contract() -> None:
    """The shared SQL-aware fake should satisfy the storage-neutral store contract."""
    store = PostgresSessionStore(InMemoryPostgresSessionStoreConnection())

    _assert_store_round_trip_contract(store, "session-postgres-contract-parity")


def test_in_memory_postgres_session_store_fake_rejects_unexpected_sql() -> None:
    """The default fake should fail loudly when adapter SQL drifts unexpectedly."""
    connection = InMemoryPostgresSessionStoreConnection()

    with connection.cursor() as cursor:
        with pytest.raises(
            AssertionError,
            match="Unexpected PostgreSQL adapter query in test double",
        ):
            cursor.execute("SELECT now()")


def test_postgres_session_store_round_trips_cancel_intent() -> None:
    """Cancel writes should read back as current-state runtime control."""
    connection = InMemoryPostgresSessionStoreConnection()
    store = PostgresSessionStore(connection)

    assert store.is_cancel_requested("session-postgres-cancel") is False

    store.request_cancel("session-postgres-cancel")

    assert connection.commit_count == 1
    assert store.is_cancel_requested("session-postgres-cancel") is True


def test_postgres_session_store_request_cancel_stays_tolerant_without_metadata() -> None:
    """Low-level cancel intent should not require a durable metadata row."""
    connection = InMemoryPostgresSessionStoreConnection()
    store = PostgresSessionStore(connection)

    store.request_cancel("session-postgres-missing-metadata")

    assert connection.cancel_rows == {"session-postgres-missing-metadata": True}
    assert store.is_cancel_requested("session-postgres-missing-metadata") is True


def test_postgres_session_store_request_cancel_is_idempotent_current_state() -> None:
    """Repeated cancel writes should keep one stable current-state signal."""
    connection = InMemoryPostgresSessionStoreConnection()
    store = PostgresSessionStore(connection)
    session_id = "session-postgres-cancel-repeat"

    store.request_cancel(session_id)
    store.request_cancel(session_id)

    assert connection.cancel_rows == {session_id: True}
    assert connection.commit_count == 2
    assert store.is_cancel_requested(session_id) is True


def test_postgres_session_store_metadata_round_trip_preserves_snapshot_shape() -> None:
    """Metadata writes should rebuild the stable snapshot shape."""
    connection = InMemoryPostgresSessionStoreConnection()
    store = PostgresSessionStore(connection)
    metadata = _metadata("session-postgres-round-trip", status="running")

    store.write_metadata(metadata)

    assert connection.commit_count == 1
    assert store.session_exists(metadata.session_id) is True
    assert store.read_snapshot(metadata.session_id) == {
        "session": metadata.to_dict(),
        "progress": None,
        "alerts": [],
        "results": [],
        "latest_result": None,
    }


def test_postgres_session_store_write_metadata_upserts_existing_session_row() -> None:
    """Repeated metadata writes should replace the authoritative session row."""
    connection = InMemoryPostgresSessionStoreConnection()
    store = PostgresSessionStore(connection)
    first = _metadata("session-postgres-upsert", status="pending", input_path="/tmp/first.mp4")
    second = _metadata("session-postgres-upsert", status="running", input_path="/tmp/second.mp4")

    store.write_metadata(first)
    store.write_metadata(second)

    assert connection.commit_count == 2
    assert list(connection.metadata_rows) == [first.session_id]
    assert store.read_snapshot(first.session_id)["session"] == second.to_dict()


def test_postgres_session_store_write_progress_persists_latest_progress_snapshot() -> None:
    """Progress writes should populate the latest progress snapshot for one session."""
    connection = InMemoryPostgresSessionStoreConnection()
    store = PostgresSessionStore(connection)
    metadata = _metadata("session-postgres-progress")
    progress = _running_progress(metadata.session_id, processed_count=1)

    store.write_metadata(metadata)
    store.write_progress(progress)

    assert connection.commit_count == 2
    assert store.read_snapshot(metadata.session_id) == {
        "session": metadata.to_dict(),
        "progress": progress.to_dict(),
        "alerts": [],
        "results": [],
        "latest_result": None,
    }


def test_postgres_session_store_write_progress_keeps_latest_only_semantics() -> None:
    """Repeated progress writes should replace the latest row instead of appending history."""
    connection = InMemoryPostgresSessionStoreConnection()
    store = PostgresSessionStore(connection)
    metadata = _metadata("session-postgres-progress-latest")
    first = _running_progress(metadata.session_id, processed_count=1)
    second = _running_progress(metadata.session_id, processed_count=2)

    store.write_metadata(metadata)
    store.write_progress(first)
    store.write_progress(second)

    snapshot = store.read_snapshot(metadata.session_id)
    assert connection.commit_count == 3
    assert list(connection.progress_rows) == [metadata.session_id]
    assert snapshot["progress"] == second.to_dict()
    assert "progress_history" not in snapshot


def test_postgres_session_store_append_result_preserves_read_order_and_latest_result() -> None:
    """Ordered appends should drive result reads and `latest_result`."""
    connection = InMemoryPostgresSessionStoreConnection()
    store = PostgresSessionStore(connection)
    metadata = _metadata("session-postgres-results")
    first = _result(metadata.session_id, "video_metrics", 0)
    second = _result(metadata.session_id, "video_blur", 1)

    store.write_metadata(metadata)
    store.append_result(first)
    store.append_result(second)

    snapshot = store.read_snapshot(metadata.session_id)
    assert connection.commit_count == 3
    assert store.read_results(metadata.session_id) == [first.to_dict(), second.to_dict()]
    assert snapshot["results"] == [first.to_dict(), second.to_dict()]
    assert snapshot["latest_result"] == second.to_dict()


def test_postgres_session_store_append_result_projects_shared_query_fields() -> None:
    """Stored rows should keep a few queryable hints without flattening the payload."""
    connection = InMemoryPostgresSessionStoreConnection()
    store = PostgresSessionStore(connection)
    metadata = _metadata("session-postgres-result-columns")
    result = ResultEvent(
        session_id=metadata.session_id,
        detector_id="video_blur",
        payload={
            "timestamp_utc": "2026-07-01 10:00:00",
            "detector_name": "Blur Check",
            "source_name": "segment_0001.ts",
            "window_index": 1,
            "blur_score": 0.91,
        },
    )

    store.write_metadata(metadata)
    store.append_result(result)

    assert connection.result_rows == [
        {
            "id": 1,
            "session_id": metadata.session_id,
            "detector_id": "video_blur",
            "detector_name": "Blur Check",
            "event_timestamp_utc": "2026-07-01 10:00:00",
            "payload_json": result.payload,
        }
    ]


def test_postgres_session_store_keeps_append_order_when_timestamps_match_or_rows_arrive_unsorted() -> None:
    """Append order should come from durable row ids, not timestamp or fetch order."""
    connection = InMemoryPostgresSessionStoreConnection()
    metadata = _metadata("session-postgres-same-timestamp-order")
    first = ResultEvent(
        session_id=metadata.session_id,
        detector_id="video_metrics",
        payload={
            "timestamp_utc": "2026-07-01 10:00:00",
            "source_name": "clip.mp4 @ 00:00",
            "window_index": 0,
        },
    ).to_dict()
    second = ResultEvent(
        session_id=metadata.session_id,
        detector_id="video_blur",
        payload={
            "timestamp_utc": "2026-07-01 10:00:00",
            "source_name": "clip.mp4 @ 00:01",
            "window_index": 1,
        },
    ).to_dict()
    connection.metadata_rows[metadata.session_id] = metadata.to_dict()
    connection.result_rows.extend(
        [
            {"id": 2, **second},
            {"id": 1, **first},
        ]
    )
    connection.result_sequence = 2
    store = PostgresSessionStore(connection)

    results = store.read_results(metadata.session_id)

    assert results == [first, second]
    assert store.read_snapshot(metadata.session_id)["latest_result"] == second


def test_postgres_session_store_assembles_full_snapshot_contract_shape() -> None:
    """Snapshots should match the file-backed public shape from durable rows."""
    connection = InMemoryPostgresSessionStoreConnection()
    store = PostgresSessionStore(connection)
    metadata = _metadata("session-postgres-full-snapshot", status="running")
    progress = _running_progress(metadata.session_id, processed_count=2)
    first = _result(metadata.session_id, "video_metrics", 1)
    second = _result(metadata.session_id, "video_blur", 2)

    store.write_metadata(metadata)
    store.write_progress(progress)
    store.append_result(first)
    store.append_result(second)

    snapshot = store.read_snapshot(metadata.session_id)
    _assert_snapshot_contract_shape(snapshot)
    assert snapshot == {
        "session": metadata.to_dict(),
        "progress": progress.to_dict(),
        "alerts": [],
        "results": [first.to_dict(), second.to_dict()],
        "latest_result": second.to_dict(),
    }


def test_postgres_session_store_read_results_tolerates_malformed_rows() -> None:
    """Malformed result rows should be skipped while valid rows keep append order."""
    connection = InMemoryPostgresSessionStoreConnection()
    metadata = _metadata("session-postgres-results-malformed")
    valid_first = _result(metadata.session_id, "video_metrics", 0).to_dict()
    valid_second = _result(metadata.session_id, "video_blur", 1).to_dict()
    connection.metadata_rows[metadata.session_id] = metadata.to_dict()
    connection.result_rows.extend(
        [
            {
                "id": 1,
                **valid_first,
            },
            {
                "id": 2,
                "session_id": metadata.session_id,
                "detector_id": "",
                "payload": {"window_index": 99},
            },
            {
                "id": 3,
                **valid_second,
            },
        ]
    )
    connection.result_sequence = 3
    store = PostgresSessionStore(connection)

    assert store.read_results(metadata.session_id) == [valid_first, valid_second]
    assert store.read_snapshot(metadata.session_id)["latest_result"] == valid_second


def test_postgres_session_store_session_exists_tracks_metadata_presence_not_validity() -> None:
    """Known-session checks should follow metadata-row presence even if unreadable."""
    connection = InMemoryPostgresSessionStoreConnection()
    connection.metadata_rows["session-postgres-malformed"] = {
        "session_id": "session-postgres-malformed",
        "mode": "video_files",
        "input_path": "/tmp/input.mp4",
        "selected_detectors": "video_metrics",
        "status": "running",
    }
    store = PostgresSessionStore(connection)

    assert store.session_exists("session-postgres-malformed") is True
    assert store.read_snapshot("session-postgres-malformed") == {
        "session": None,
        "progress": None,
        "alerts": [],
        "results": [],
        "latest_result": None,
    }


def test_postgres_session_store_snapshot_tolerates_malformed_progress_rows() -> None:
    """Malformed progress rows should degrade to `progress is None` without hiding metadata."""
    connection = InMemoryPostgresSessionStoreConnection()
    metadata = _metadata("session-postgres-progress-malformed")
    connection.metadata_rows[metadata.session_id] = metadata.to_dict()
    connection.progress_rows[metadata.session_id] = {
        "session_id": metadata.session_id,
        "status": "running",
        "processed_count": 1,
        "total_count": 3,
        "current_item": "segment_0001.ts",
        "latest_result_detector": None,
        "alert_count": 1,
        "last_updated_utc": "2026-06-29 10:00:01",
        "latest_result_detectors": ["video_metrics"],
        "status_reason": "running",
        "status_detail": None,
    }
    store = PostgresSessionStore(connection)

    assert store.read_snapshot(metadata.session_id) == {
        "session": metadata.to_dict(),
        "progress": None,
        "alerts": [],
        "results": [],
        "latest_result": None,
    }


def test_initialize_postgres_session_store_executes_schema_statements_in_order() -> None:
    """Bootstrap should execute the frozen table/index statements in order."""
    connection = RecordingConnection()

    initialize_postgres_session_store(connection)

    assert connection.executed_statements == [
        (statement, None) for statement in POSTGRES_SESSION_STORE_SCHEMA_STATEMENTS
    ]
    assert connection.committed is True


def test_initialize_postgres_session_store_is_repeatable_for_idempotent_bootstrap_calls(
) -> None:
    """Repeated bootstrap calls should stay safe for idempotent table/index creation."""
    connection = RecordingConnection()

    initialize_postgres_session_store(connection)
    initialize_postgres_session_store(connection)

    expected_statements = [
        *POSTGRES_SESSION_STORE_SCHEMA_STATEMENTS,
        *POSTGRES_SESSION_STORE_SCHEMA_STATEMENTS,
    ]
    assert connection.executed_statements == [
        (statement, None) for statement in expected_statements
    ]
    assert connection.commit_count == 2


def test_initialize_postgres_session_store_does_not_commit_after_mid_schema_failure() -> None:
    """Bootstrap should not commit partial schema work after a later statement fails."""
    connection = MidSchemaFailureConnection()

    with pytest.raises(RuntimeError, match="index creation failed"):
        initialize_postgres_session_store(connection)

    assert connection.cursor_instance.calls == 2
    assert connection.committed is False


def test_drop_postgres_session_store_schema_executes_drop_statements_in_safe_order() -> None:
    """Cleanup should drop result rows before progress and metadata tables."""
    connection = RecordingConnection()

    drop_postgres_session_store_schema(connection)

    assert connection.executed_statements == [
        (statement, None) for statement in POSTGRES_SESSION_STORE_SCHEMA_DROP_STATEMENTS
    ]
    assert connection.committed is True


def test_reset_postgres_session_store_schema_recreates_clean_schema_after_drop() -> None:
    """Isolation reset should drop old tables, then recreate the durable schema."""
    connection = RecordingConnection()

    reset_postgres_session_store_schema(connection)

    expected_statements = [
        *POSTGRES_SESSION_STORE_SCHEMA_DROP_STATEMENTS,
        *POSTGRES_SESSION_STORE_SCHEMA_STATEMENTS,
    ]
    assert connection.executed_statements == [
        (statement, None) for statement in expected_statements
    ]
    assert connection.commit_count == 2


def test_bootstrap_isolated_postgres_session_store_resets_schema_before_returning(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The isolation helper should connect once and reset the known session tables."""
    connection = RecordingConnection()
    seen: list[str] = []

    monkeypatch.setattr(
        session_store_postgres_test_support,
        "connect_postgres_session_store",
        lambda: seen.append("connect") or connection,
    )
    monkeypatch.setattr(
        session_store_postgres_test_support,
        "reset_postgres_session_store_schema",
        lambda resolved_connection: seen.append("reset")
        if resolved_connection is connection
        else None,
    )

    result = bootstrap_isolated_postgres_session_store()

    assert result is connection
    assert seen == ["connect", "reset"]


def test_close_postgres_session_store_connection_if_possible_ignores_objects_without_close(
) -> None:
    """The close helper should stay no-op for simple fake objects."""
    close_postgres_session_store_connection_if_possible(object())


def test_bootstrap_postgres_session_store_initializes_schema_when_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Bootstrap should connect and initialize when auto-create is enabled."""
    settings = _postgres_settings(auto_create_tables=True)
    connection = RecordingConnection()
    seen: list[str] = []

    def fake_connect(
        resolved_settings: PostgresSessionStoreSettings,
    ) -> RecordingConnection:
        assert resolved_settings == settings
        seen.append("connect")
        return connection

    def fake_initialize(resolved_connection: RecordingConnection) -> None:
        assert resolved_connection is connection
        seen.append("initialize")

    monkeypatch.setattr(
        "session_store_postgres.connect_postgres_session_store",
        fake_connect,
    )
    monkeypatch.setattr(
        "session_store_postgres.initialize_postgres_session_store",
        fake_initialize,
    )

    result = bootstrap_postgres_session_store(settings)

    assert result is connection
    assert seen == ["connect", "initialize"]


def test_bootstrap_postgres_session_store_skips_schema_init_when_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Bootstrap should skip schema creation when auto-create is disabled."""
    settings = _postgres_settings()
    connection = RecordingConnection()
    seen: list[str] = []

    def fake_connect(
        resolved_settings: PostgresSessionStoreSettings,
    ) -> RecordingConnection:
        assert resolved_settings == settings
        seen.append("connect")
        return connection

    def fake_initialize(resolved_connection: RecordingConnection) -> None:
        assert resolved_connection is connection
        seen.append("initialize")

    monkeypatch.setattr(
        "session_store_postgres.connect_postgres_session_store",
        fake_connect,
    )
    monkeypatch.setattr(
        "session_store_postgres.initialize_postgres_session_store",
        fake_initialize,
    )

    result = bootstrap_postgres_session_store(settings)

    assert result is connection
    assert seen == ["connect"]


def test_bootstrap_postgres_session_store_uses_cached_settings_when_not_provided(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Bootstrap should fall back to the cached session-store settings."""
    settings = _postgres_settings()
    connection = RecordingConnection()
    seen: list[str] = []

    monkeypatch.setattr(
        "session_store_postgres.get_postgres_session_store_settings",
        lambda: settings,
    )

    def fake_connect(
        resolved_settings: PostgresSessionStoreSettings,
    ) -> RecordingConnection:
        assert resolved_settings == settings
        seen.append("connect")
        return connection

    monkeypatch.setattr(
        "session_store_postgres.connect_postgres_session_store",
        fake_connect,
    )

    result = bootstrap_postgres_session_store()

    assert result is connection
    assert seen == ["connect"]


def test_bootstrap_postgres_session_store_explicit_settings_override_stale_cached_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Explicit bootstrap settings should win over already-cached env-derived settings."""
    stale_settings = PostgresSessionStoreSettings(
        database_url="postgresql://stale:stale@localhost:5432/election_stream_monitor",
        auto_create_tables=False,
        real_smoke_enabled=False,
    )
    explicit_settings = PostgresSessionStoreSettings(
        database_url="postgresql://fresh:secret@db.example/esm",
        auto_create_tables=False,
        real_smoke_enabled=False,
    )
    connection = RecordingConnection()
    seen_settings: list[PostgresSessionStoreSettings] = []

    monkeypatch.setattr(
        "session_store_postgres.get_postgres_session_store_settings",
        lambda: stale_settings,
    )

    def fake_connect(
        resolved_settings: PostgresSessionStoreSettings,
    ) -> RecordingConnection:
        seen_settings.append(resolved_settings)
        return connection

    monkeypatch.setattr(
        "session_store_postgres.connect_postgres_session_store",
        fake_connect,
    )

    result = bootstrap_postgres_session_store(explicit_settings)

    assert result is connection
    assert seen_settings == [explicit_settings]


def test_load_postgres_session_store_driver_reports_missing_psycopg_dependency(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Bootstrap should fail clearly when the psycopg dependency is unavailable."""
    monkeypatch.setattr(
        "session_store_postgres.importlib.import_module",
        lambda name: (_ for _ in ()).throw(ImportError("psycopg missing")),
    )

    with pytest.raises(
        PostgresSessionStoreBootstrapError,
        match="Install psycopg to use the PostgreSQL session-store backend",
    ):
        load_postgres_session_store_driver()


def test_load_postgres_session_store_driver_returns_imported_driver_module(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Bootstrap should pass through the loaded PostgreSQL driver module."""
    fake_driver = ModuleType("psycopg")
    monkeypatch.setattr(
        "session_store_postgres.importlib.import_module",
        lambda name: fake_driver,
    )

    loaded_driver = load_postgres_session_store_driver()

    assert loaded_driver is fake_driver


def test_connect_postgres_session_store_reports_missing_psycopg_dependency(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Bootstrap should fail clearly when the psycopg dependency is unavailable."""
    monkeypatch.setattr(
        "session_store_postgres.load_postgres_session_store_driver",
        lambda: (_ for _ in ()).throw(
            PostgresSessionStoreBootstrapError(
                "Install psycopg to use the PostgreSQL session-store backend"
            )
        ),
    )

    with pytest.raises(
        PostgresSessionStoreBootstrapError,
        match="Install psycopg to use the PostgreSQL session-store backend",
    ):
        connect_postgres_session_store(_postgres_settings())


def test_connect_postgres_session_store_rejects_missing_database_url_before_driver_load(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Bootstrap validation should fail before the driver is loaded when no URL exists."""
    monkeypatch.setattr(
        "session_store_postgres.load_postgres_session_store_driver",
        lambda: (_ for _ in ()).throw(AssertionError("driver should not load")),
    )

    with pytest.raises(
        PostgresSessionStoreBootstrapError,
        match="PostgreSQL session store requires ESM_POSTGRES_SESSION_DATABASE_URL",
    ):
        connect_postgres_session_store(_postgres_settings(database_url=None))


def test_connect_postgres_session_store_rejects_invalid_database_url_before_driver_load(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Bootstrap validation should reject invalid URL schemes before driver work starts."""
    monkeypatch.setattr(
        "session_store_postgres.load_postgres_session_store_driver",
        lambda: (_ for _ in ()).throw(AssertionError("driver should not load")),
    )

    with pytest.raises(
        PostgresSessionStoreBootstrapError,
        match="must use a postgres or postgresql URL",
    ):
        connect_postgres_session_store(
            _postgres_settings(database_url="sqlite:///tmp/sessions.db")
        )


def test_connect_postgres_session_store_uses_validated_database_url_with_driver_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Bootstrap should pass the validated URL through to psycopg.connect."""
    fake_psycopg = FakePsycopgModule()
    settings = _postgres_settings()
    monkeypatch.setattr(
        "session_store_postgres.load_postgres_session_store_driver",
        lambda: fake_psycopg,
    )

    connection = connect_postgres_session_store(settings)

    assert connection is fake_psycopg.connection
    assert fake_psycopg.connect_calls == [settings.database_url]


def test_connect_postgres_session_store_wraps_driver_connection_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Driver connection failures should become one stable bootstrap error."""
    fake_psycopg = FakePsycopgModule(
        connect_error=FakePsycopgModule.Error("database unavailable")
    )
    monkeypatch.setattr(
        "session_store_postgres.load_postgres_session_store_driver",
        lambda: fake_psycopg,
    )

    with pytest.raises(
        PostgresSessionStoreBootstrapError,
        match="Could not connect to the PostgreSQL session store",
    ):
        connect_postgres_session_store(_postgres_settings())

    assert fake_psycopg.connect_calls == [VALID_POSTGRES_SESSION_URL]


@pytest.mark.skipif(
    not REAL_POSTGRES_SESSION_STORE_SMOKE_ENABLED,
    reason="Real PostgreSQL session-store smoke test is opt-in.",
)
def test_real_postgres_session_store_isolation_helper_resets_schema_cleanly() -> None:
    """The isolation helper should provide a clean live schema without polluting default lanes."""
    connection = bootstrap_isolated_postgres_session_store()
    try:
        initialize_postgres_session_store(connection)
        initialize_postgres_session_store(connection)
    finally:
        close_postgres_session_store_connection_if_possible(connection)


@pytest.mark.skipif(
    not REAL_POSTGRES_SESSION_STORE_SMOKE_ENABLED,
    reason="Real PostgreSQL session-store smoke test is opt-in.",
)
def test_real_postgres_session_store_adapter_round_trip_smoke() -> None:
    """Live adapter smoke should stay isolated and preserve the shared store contract."""
    connection, store = build_isolated_postgres_session_store()
    try:
        _assert_store_round_trip_contract(
            store,
            "session-postgres-real-smoke-round-trip",
        )
    finally:
        close_postgres_session_store_connection_if_possible(connection)
