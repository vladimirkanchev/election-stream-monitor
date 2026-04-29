"""Pending and running lifecycle helpers for `session_runner`.

This module owns the small state-transition steps that happen before any
analysis loop starts:

- build and persist pending metadata
- write initial pending progress
- move a validated session into the running state
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from analyzer_contract import InputMode
from session_io import initialize_session, update_session_status, write_session_progress
from session_models import SessionMetadata, SessionProgress
import session_runner_progress

ProgressStatusBuilder = Callable[..., SessionProgress]


def build_pending_metadata(
    *,
    session_id: str,
    mode: InputMode,
    input_path: str | Path,
    selected_detectors: list[str],
) -> SessionMetadata:
    """Build pending session metadata for the current input path."""
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
) -> SessionMetadata:
    """Persist pending metadata and return the written snapshot."""
    metadata = build_pending_metadata(
        session_id=session_id,
        mode=mode,
        input_path=input_path,
        selected_detectors=selected_detectors,
    )
    initialize_session(metadata)
    return metadata


def initialize_pending_session(
    *,
    mode: InputMode,
    input_path: str | Path,
    selected_detectors: list[str],
    session_id: str,
) -> tuple[SessionMetadata, SessionProgress]:
    """Persist the initial pending metadata and zero-count progress snapshot."""
    metadata = persist_pending_metadata(
        session_id=session_id,
        mode=mode,
        input_path=input_path,
        selected_detectors=selected_detectors,
    )
    progress = SessionProgress.initial(session_id=session_id, total_count=0)
    write_session_progress(progress)
    return metadata, progress


def start_running_session(
    metadata: SessionMetadata,
    progress: SessionProgress,
    *,
    total_count: int,
    progress_builder: ProgressStatusBuilder | None = None,
) -> tuple[SessionMetadata, SessionProgress]:
    """Transition a validated pending session into the running state."""
    if progress_builder is None:
        progress_builder = session_runner_progress.build_progress_update

    initialized_progress = SessionProgress.initial(
        session_id=progress.session_id,
        total_count=total_count,
    )
    write_session_progress(initialized_progress)
    updated_metadata = update_session_status(metadata, "running")
    updated_progress = progress_builder(
        initialized_progress,
        status=updated_metadata.status,
    )
    write_session_progress(updated_progress)
    return updated_metadata, updated_progress
