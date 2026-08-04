"""Persist the early lifecycle state used by `session_runner`.

This module owns the durable writes that happen before the execution loop:
pending metadata, initial progress, and the transition into `running`.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import session_runner_progress
from analyzer_contract import InputMode
from session_models import SessionMetadata, SessionProgress
from session_store import SessionStore
from session_store_runtime import get_default_session_store

ProgressStatusBuilder = Callable[..., SessionProgress]


def build_pending_metadata(
    *,
    session_id: str,
    mode: InputMode,
    input_path: str | Path,
    selected_detectors: list[str],
) -> SessionMetadata:
    """Build the pending metadata payload for one accepted input."""
    return SessionMetadata(
        session_id=session_id,
        mode=mode,
        input_path=str(input_path),
        selected_detectors=selected_detectors,
        status="pending",
    )


def persist_pending_metadata(
    *,
    session_id: str,
    mode: InputMode,
    input_path: str | Path,
    selected_detectors: list[str],
    session_store: SessionStore | None = None,
) -> SessionMetadata:
    """Write pending metadata through the injected or default session store."""
    session_store = session_store or get_default_session_store()
    metadata = build_pending_metadata(
        session_id=session_id,
        mode=mode,
        input_path=input_path,
        selected_detectors=selected_detectors,
    )
    session_store.write_metadata(metadata)
    return metadata


def initialize_pending_session(
    *,
    mode: InputMode,
    input_path: str | Path,
    selected_detectors: list[str],
    session_id: str,
    session_store: SessionStore | None = None,
) -> tuple[SessionMetadata, SessionProgress]:
    """Create the initial durable session state before execution begins."""
    session_store = session_store or get_default_session_store()
    metadata = persist_pending_metadata(
        session_id=session_id,
        mode=mode,
        input_path=input_path,
        selected_detectors=selected_detectors,
        session_store=session_store,
    )
    progress = SessionProgress.initial(session_id=session_id, total_count=0)
    session_store.write_progress(progress)
    return metadata, progress


def start_running_session(
    metadata: SessionMetadata,
    progress: SessionProgress,
    *,
    total_count: int,
    progress_builder: ProgressStatusBuilder | None = None,
    session_store: SessionStore | None = None,
) -> tuple[SessionMetadata, SessionProgress]:
    """Promote a pending session to `running` and refresh latest progress."""
    session_store = session_store or get_default_session_store()
    if progress_builder is None:
        progress_builder = session_runner_progress.build_progress_update

    initialized_progress = SessionProgress.initial(
        session_id=progress.session_id,
        total_count=total_count,
    )
    session_store.write_progress(initialized_progress)
    updated_metadata = metadata.transition_to("running")
    session_store.write_metadata(updated_metadata)
    updated_progress = progress_builder(
        initialized_progress,
        status=updated_metadata.status,
    )
    updated_progress = session_runner_progress.persist_progress_if_changed(
        current=initialized_progress,
        next_progress=updated_progress,
        write_progress=session_store.write_progress,
    )
    return updated_metadata, updated_progress
