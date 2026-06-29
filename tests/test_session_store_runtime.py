"""Tests for default durable session-store selection and rollback safety."""

from pathlib import Path

import config
import pytest
from session_models import ResultEvent, SessionMetadata, SessionProgress
from session_store_file import DEFAULT_FILE_SESSION_STORE, FileSessionStore
from session_store_runtime import (
    DEFAULT_SESSION_STORE,
    clear_default_session_store_cache,
    get_default_session_store,
)
from session_store_runtime_config import (
    DEFAULT_SESSION_STORE_BACKEND,
    SESSION_STORE_BACKEND_ENV,
    SessionStoreRuntimeSettings,
    get_session_store_runtime_settings,
)


def _metadata(session_id: str) -> SessionMetadata:
    """Build minimal metadata for default-store tests."""
    return SessionMetadata(
        session_id=session_id,
        mode="video_files",
        input_path="/tmp/clip.mp4",
        selected_detectors=["video_metrics"],
        status="running",
    )


@pytest.fixture(autouse=True)
def _clear_runtime_store_caches() -> None:
    """Keep runtime store selection deterministic across env-driven tests."""
    clear_default_session_store_cache()
    yield
    clear_default_session_store_cache()


def test_default_session_store_is_file_backed_for_current_stage() -> None:
    """Default selection should preserve the current file-backed runtime."""
    default_store = get_default_session_store()

    assert DEFAULT_SESSION_STORE is DEFAULT_FILE_SESSION_STORE
    assert default_store is DEFAULT_FILE_SESSION_STORE
    assert isinstance(default_store, FileSessionStore)


def test_session_store_runtime_settings_default_to_file_backend() -> None:
    """Runtime settings should keep file-backed persistence as the branch default."""
    settings = get_session_store_runtime_settings()

    assert settings == SessionStoreRuntimeSettings(backend=DEFAULT_SESSION_STORE_BACKEND)


def test_default_session_store_stays_file_backed_for_invalid_runtime_backend_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Invalid runtime config should still resolve to the file-backed rollback path."""
    monkeypatch.setenv(SESSION_STORE_BACKEND_ENV, "not-a-real-backend")

    settings = get_session_store_runtime_settings()
    default_store = get_default_session_store()

    assert settings == SessionStoreRuntimeSettings(backend=DEFAULT_SESSION_STORE_BACKEND)
    assert default_store is DEFAULT_FILE_SESSION_STORE


def test_default_session_store_accepts_explicit_file_runtime_backend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An explicit file mode should resolve to the same stable default store."""
    monkeypatch.setenv(SESSION_STORE_BACKEND_ENV, DEFAULT_SESSION_STORE_BACKEND)

    settings = get_session_store_runtime_settings()
    default_store = get_default_session_store()

    assert settings == SessionStoreRuntimeSettings(backend=DEFAULT_SESSION_STORE_BACKEND)
    assert default_store is DEFAULT_FILE_SESSION_STORE


def test_default_session_store_preserves_current_file_layout(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Default writes should still create the established session files."""
    monkeypatch.setattr(config, "SESSION_OUTPUT_FOLDER", tmp_path)
    store = get_default_session_store()
    metadata = _metadata("session-default-store")

    store.write_metadata(metadata)
    store.write_progress(SessionProgress.initial(session_id=metadata.session_id, total_count=1))
    store.append_result(
        ResultEvent(
            session_id=metadata.session_id,
            detector_id="video_metrics",
            payload={"window_index": 0},
        )
    )

    session_dir = tmp_path / metadata.session_id
    assert (session_dir / "session.json").exists()
    assert (session_dir / "progress.json").exists()
    assert (session_dir / "results.jsonl").exists()
    assert store.read_snapshot(metadata.session_id)["session"] == metadata.to_dict()
