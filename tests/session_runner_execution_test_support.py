"""Shared fixtures and helpers for the split session-runner execution suites.

These helpers keep cancellation tests focused on runner behavior rather than
repeating file setup and synthetic slice construction in each suite.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

import config
from analyzer_contract import AnalysisSlice, InputMode
from session_io import initialize_session, write_session_progress
from session_models import SessionMetadata, SessionProgress
from session_models import SessionStatus
from session_store import SessionStore
from session_store_file import FileSessionStore
import session_runner_execution
from stream_loader_contracts import ApiStreamSourceContract, ApiStreamTelemetrySnapshot

DEFAULT_TIMESTAMP_UTC = "2026-04-28 12:00:00"


@dataclass(slots=True)
class LoaderStub:
    """Small loader double that exposes the runner methods under test."""

    accepted_count: int
    telemetry: ApiStreamTelemetrySnapshot
    slices: tuple[AnalysisSlice, ...] = ()
    persisted_keys: set[tuple[str, int, str]] | None = None

    def connect(self, source: ApiStreamSourceContract) -> None:
        """Satisfy the live-loader protocol without changing test behavior."""
        _ = source

    def iter_slices(self) -> Iterator[AnalysisSlice]:
        """Yield any synthetic slices attached to this stub."""
        return iter(self.slices)

    def close(self) -> None:
        """Satisfy the live-loader protocol with a no-op close."""
        return None

    def load_persisted_identity_keys(self) -> set[tuple[str, int, str]]:
        """Return any preloaded de-dup keys attached to this stub."""
        return set(self.persisted_keys or set())

    def persist_identity_key(self, key: tuple[str, int, str]) -> None:
        """Record one accepted identity key on the stub for assertions."""
        if self.persisted_keys is None:
            self.persisted_keys = set()
        self.persisted_keys.add(key)

    def accepted_slice_count(self) -> int:
        """Return the number of accepted slices seen during a synthetic run."""
        return self.accepted_count

    def telemetry_snapshot(self) -> ApiStreamTelemetrySnapshot:
        """Return the fixed telemetry snapshot attached to this stub."""
        return self.telemetry


def configure_session_output(monkeypatch, tmp_path: Path) -> None:
    """Redirect persisted session output into the test-specific temp directory."""
    monkeypatch.setattr(config, "SESSION_OUTPUT_FOLDER", tmp_path / "sessions")


def build_metadata(
    *,
    session_id: str,
    mode: InputMode = "video_segments",
    status: SessionStatus = "running",
) -> SessionMetadata:
    """Build minimal metadata records for runner execution tests."""
    return SessionMetadata(
        session_id=session_id,
        mode=mode,
        input_path="input-path",
        selected_detectors=["video_metrics"],
        status=status,
    )


def build_progress(
    *,
    session_id: str,
    status: SessionStatus = "running",
    processed_count: int = 0,
    total_count: int = 0,
    current_item: str | None = None,
) -> SessionProgress:
    """Build a lightweight progress snapshot with stable defaults."""
    return SessionProgress(
        session_id=session_id,
        status=status,
        processed_count=processed_count,
        total_count=total_count,
        current_item=current_item,
        latest_result_detector=None,
        alert_count=0,
        last_updated_utc=DEFAULT_TIMESTAMP_UTC,
        latest_result_detectors=[],
        status_reason=status,
        status_detail=None,
    )


def persist_session_state(metadata: SessionMetadata, progress: SessionProgress) -> None:
    """Write initial metadata and progress so runner helpers can update them."""
    initialize_session(metadata)
    write_session_progress(progress)


def build_slice(tmp_path: Path, name: str) -> AnalysisSlice:
    """Create one persisted finite-slice input for local runner execution tests."""
    analysis_slice = AnalysisSlice(
        file_path=tmp_path / name,
        source_group="segments",
        source_name=name,
        window_index=0,
    )
    analysis_slice.file_path.write_bytes(b"ts")
    return analysis_slice


def settle_cancelled_local_session_once(
    *,
    tmp_path: Path,
    metadata: SessionMetadata,
    progress: SessionProgress,
    session_store: SessionStore | None = None,
) -> bool:
    """Run one local slice after cancel intent and report whether work still ran.

    This keeps runtime tests focused on the public contract: once cancel intent
    is visible to the worker, bundle execution should stop before the next
    slice while normal terminal settlement still happens.
    """
    bundle_called = {"value": False}

    def fake_bundle_runner(**_: object) -> dict[str, list[dict[str, object]]]:
        bundle_called["value"] = True
        return {"results": [], "alerts": []}

    session_runner_execution.process_discovered_slices(
        metadata=metadata,
        progress=progress,
        mode=metadata.mode,
        session_id=metadata.session_id,
        selected_detectors=metadata.selected_detectors,
        input_slices=[build_slice(tmp_path, "segment_0001.ts")],
        bundle_runner=fake_bundle_runner,
        session_store=session_store or FileSessionStore(),
    )
    return bundle_called["value"]


def build_live_slice(
    tmp_path: Path,
    name: str,
    *,
    source_group: str = "stream-a",
    window_index: int = 0,
) -> AnalysisSlice:
    """Create one persisted live-slice input for api_stream runner tests."""
    analysis_slice = AnalysisSlice(
        file_path=tmp_path / name,
        source_group=source_group,
        source_name=name,
        window_index=window_index,
    )
    analysis_slice.file_path.write_bytes(b"ts")
    return analysis_slice


def build_loader(
    *,
    accepted_slice_count: int = 1,
    stop_reason: str | None = None,
    source_url_class: str = "hls_playlist_url",
    playlist_refresh_count: int = 0,
    skipped_replay_count: int = 0,
    reconnect_attempt_count: int = 0,
    reconnect_budget_exhaustion_count: int = 0,
    terminal_failure_reason: str | None = None,
) -> LoaderStub:
    """Build a loader stub with configurable accepted-count and telemetry fields."""
    telemetry = ApiStreamTelemetrySnapshot(
        source_url_class=source_url_class,
        playlist_refresh_count=playlist_refresh_count,
        skipped_replay_count=skipped_replay_count,
        reconnect_attempt_count=reconnect_attempt_count,
        reconnect_budget_exhaustion_count=reconnect_budget_exhaustion_count,
        terminal_failure_reason=terminal_failure_reason,
        stop_reason=stop_reason,
    )
    return LoaderStub(accepted_count=accepted_slice_count, telemetry=telemetry)


__all__ = [
    "DEFAULT_TIMESTAMP_UTC",
    "LoaderStub",
    "build_live_slice",
    "build_loader",
    "build_metadata",
    "build_progress",
    "build_slice",
    "configure_session_output",
    "persist_session_state",
    "settle_cancelled_local_session_once",
]
