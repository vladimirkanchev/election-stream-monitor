"""Session-file helpers for the local monitoring bridge.

The frontend does not read these files directly. Instead, backend helpers write
and read a small set of session artifacts that together form the current local
session contract:

- `session.json` for stable session metadata
- `progress.json` for the latest progress snapshot
- `alerts.jsonl` for append-only alert events
- `results.jsonl` for append-only detector result events

These helpers keep the snapshot shape stable even when persisted files are
missing, malformed, or only partially written.
"""

import json
from pathlib import Path
from tempfile import NamedTemporaryFile

import config
from logger import get_logger
from session_models import (
    AlertEvent,
    parse_alert_event_payload,
    parse_result_event_payload,
    parse_session_metadata_payload,
    parse_session_progress_payload,
    ResultEvent,
    SessionMetadata,
    SessionProgress,
    SessionStatus,
)

logger = get_logger(__name__)
EMPTY_SESSION_SNAPSHOT = {
    "session": None,
    "progress": None,
    "alerts": [],
    "results": [],
    "latest_result": None,
}


def get_session_dir(session_id: str) -> Path:
    """Return the filesystem directory used by a session."""
    return config.SESSION_OUTPUT_FOLDER / _normalize_session_path_component(
        session_id,
        context="session directory",
    )


def initialize_session(metadata: SessionMetadata) -> Path:
    """Create the session directory and persist the initial metadata snapshot."""
    session_dir = get_session_dir(metadata.session_id)
    session_dir.mkdir(parents=True, exist_ok=True)
    write_session_metadata(metadata)
    return session_dir


def get_cancel_request_path(session_id: str) -> Path:
    """Return the file used to signal a cancel request for a session."""
    return get_session_dir(session_id) / "cancel_requested.json"


def get_api_stream_seen_chunk_keys_path(session_id: str) -> Path:
    """Return the persisted de-duplication log for one live session."""
    return get_session_dir(session_id) / "api_stream_seen_chunks.jsonl"


def write_session_metadata(metadata: SessionMetadata) -> None:
    """Write the authoritative `session.json` metadata snapshot for a session."""
    metadata.validate()
    session_dir = get_session_dir(metadata.session_id)
    session_dir.mkdir(parents=True, exist_ok=True)
    metadata_path = session_dir / "session.json"
    _write_json_file(metadata_path, metadata.to_dict())
    logger.debug("Wrote session metadata to %s", metadata_path)


def update_session_status(metadata: SessionMetadata, status: SessionStatus) -> SessionMetadata:
    """Persist and return a validated metadata copy with a new lifecycle status."""
    updated = metadata.transition_to(status)
    write_session_metadata(updated)
    return updated


def request_session_cancel(session_id: str) -> Path:
    """Persist a cancel request that can be picked up by the session runner.

    This helper is intentionally file-oriented and tolerant. Higher-level API
    routes and runner logic decide whether cancellation is valid for the
    current lifecycle state; this helper only records cancel intent.
    """
    request_path = get_cancel_request_path(session_id)
    request_path.parent.mkdir(parents=True, exist_ok=True)
    _write_json_file(
        request_path,
        {"session_id": session_id, "cancel_requested": True},
    )
    logger.info("Cancel requested for session %s", session_id)
    return request_path


def is_session_cancel_requested(session_id: str) -> bool:
    """Return whether a cancel request has been written for this session."""
    return get_cancel_request_path(session_id).exists()


def write_session_progress(progress: SessionProgress) -> None:
    """Write the current `progress.json` snapshot for one session."""
    progress.validate()
    session_dir = get_session_dir(progress.session_id)
    session_dir.mkdir(parents=True, exist_ok=True)
    progress_path = session_dir / "progress.json"
    _write_json_file(progress_path, progress.to_dict())
    logger.debug("Wrote session progress to %s", progress_path)


def append_result(event: ResultEvent) -> None:
    """Append one validated detector result event to `results.jsonl`."""
    _append_jsonl(get_session_dir(event.session_id) / "results.jsonl", event.to_dict())


def append_alert(event: AlertEvent) -> None:
    """Append one validated alert event to `alerts.jsonl`."""
    _append_jsonl(get_session_dir(event.session_id) / "alerts.jsonl", event.to_dict())


def read_api_stream_seen_chunk_keys(session_id: str) -> set[tuple[str, int, str]]:
    """Return persisted reconnect de-dup keys for one live session.

    The loader uses this file-backed set to avoid replaying already accepted
    live chunks after reconnect or repeated startup against the same session.
    Malformed lines are ignored so de-dup state degrades safely.
    """
    file_path = get_api_stream_seen_chunk_keys_path(session_id)
    if not file_path.exists():
        return set()

    keys: set[tuple[str, int, str]] = set()
    try:
        lines = file_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        logger.warning("Ignoring unreadable api_stream de-dup log: %s", file_path)
        return set()

    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            logger.warning(
                "Ignoring unreadable api_stream de-dup line: %s:%d",
                file_path,
                line_number,
            )
            continue
        if not isinstance(payload, dict):
            continue
        source_group = payload.get("source_group")
        window_index = payload.get("window_index")
        source_name = payload.get("source_name")
        if (
            isinstance(source_group, str)
            and isinstance(source_name, str)
            and isinstance(window_index, int)
        ):
            keys.add((source_group, window_index, source_name))

    return keys


def append_api_stream_seen_chunk_key(
    session_id: str,
    key: tuple[str, int, str],
) -> None:
    """Persist one live-slice identity key for reconnect-safe de-duplication."""
    source_group, window_index, source_name = key
    _append_jsonl(
        get_api_stream_seen_chunk_keys_path(session_id),
        {
            "source_group": source_group,
            "window_index": window_index,
            "source_name": source_name,
        },
    )


def read_session_snapshot(session_id: str) -> dict[str, object]:
    """Read one stable frontend snapshot assembled from persisted session files.

    Missing or malformed artifacts degrade to the empty snapshot shape rather
    than surfacing partially parsed internal state.
    """
    session_dir = get_session_dir(session_id)
    metadata = parse_session_metadata_payload(_read_json_file(session_dir / "session.json"))
    progress = parse_session_progress_payload(_read_json_file(session_dir / "progress.json"))
    alerts = _read_jsonl_file(session_dir / "alerts.jsonl", parser=parse_alert_event_payload)
    results = _read_jsonl_file(session_dir / "results.jsonl", parser=parse_result_event_payload)
    return _build_session_snapshot(
        metadata=metadata,
        progress=progress,
        alerts=alerts,
        results=results,
    )


def _append_jsonl(file_path: Path, payload: dict[str, object]) -> None:
    """Append one JSON object as a single JSONL line."""
    file_path.parent.mkdir(parents=True, exist_ok=True)
    with file_path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(payload) + "\n")


def _build_session_snapshot(
    *,
    metadata: dict[str, object] | None,
    progress: dict[str, object] | None,
    alerts: list[dict[str, object]],
    results: list[dict[str, object]],
) -> dict[str, object]:
    """Build the stable frontend snapshot shape from persisted session artifacts."""
    snapshot = dict(EMPTY_SESSION_SNAPSHOT)
    snapshot.update(
        {
            "session": metadata,
            "progress": progress,
            "alerts": alerts,
            "results": results,
            "latest_result": results[-1] if results else None,
        }
    )
    return snapshot


def _write_json_file(file_path: Path, payload: dict[str, object]) -> None:
    """Write one JSON file atomically to avoid partial reads during polling."""
    file_path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=file_path.parent,
        prefix=f"{file_path.name}.",
        suffix=".tmp",
        delete=False,
    ) as temp_file:
        temp_file.write(json.dumps(payload, indent=2))
        temp_path = Path(temp_file.name)

    temp_path.replace(file_path)


def _normalize_session_path_component(session_id: str, *, context: str) -> str:
    """Return one session path component or raise when traversal is attempted."""
    normalized_session_id = str(session_id).strip()
    if not normalized_session_id:
        raise ValueError(f"{context} requires a non-empty session_id")
    if normalized_session_id in {".", ".."} or any(
        separator in normalized_session_id for separator in ("/", "\\")
    ):
        raise ValueError(f"{context} requires a single safe path component")
    return normalized_session_id


def _read_json_file(file_path: Path) -> dict[str, object] | None:
    """Read one JSON object file, degrading unreadable payloads to `None`."""
    if not file_path.exists():
        return None
    try:
        payload = json.loads(file_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        logger.warning("Ignoring unreadable JSON file during snapshot read: %s", file_path)
        return None
    if not isinstance(payload, dict):
        logger.warning("Ignoring non-object JSON file during snapshot read: %s", file_path)
        return None
    return payload


def _read_jsonl_file(
    file_path: Path,
    *,
    parser,
) -> list[dict[str, object]]:
    """Read one JSONL event log while skipping malformed or unreadable lines."""
    if not file_path.exists():
        return []
    payloads: list[dict[str, object]] = []
    try:
        lines = file_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        logger.warning("Ignoring unreadable JSONL file during snapshot read: %s", file_path)
        return []

    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            raw_payload = json.loads(line)
        except json.JSONDecodeError:
            logger.warning(
                "Ignoring unreadable JSONL line during snapshot read: %s:%d",
                file_path,
                line_number,
            )
            continue

        parsed_payload = parser(raw_payload)
        if parsed_payload is None:
            logger.warning(
                "Ignoring malformed JSONL event during snapshot read: %s:%d",
                file_path,
                line_number,
            )
            continue
        payloads.append(parsed_payload)

    return payloads
