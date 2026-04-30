"""Temp-file materialization helpers for the concrete HTTP/HLS loader.

Keep this module focused on filesystem mechanics:

- atomically writing one fetched segment into the temp directory
- computing the current temp-directory byte footprint

Higher-level budget enforcement and loader state updates stay in the concrete
loader shell.
"""

from __future__ import annotations

from pathlib import Path


def _write_api_stream_temp_file(temp_path: Path, payload: bytes) -> None:
    """Atomically materialize one fetched segment into the session temp directory."""
    partial_path = temp_path.with_suffix(f"{temp_path.suffix}.part")
    try:
        if partial_path.exists():
            partial_path.unlink()
        if temp_path.exists():
            temp_path.unlink()
        partial_path.write_bytes(payload)
        partial_path.replace(temp_path)
    except OSError:
        partial_path.unlink(missing_ok=True)
        temp_path.unlink(missing_ok=True)
        raise


def _count_file_bytes_in_directory(directory: Path) -> int:
    """Return the current byte footprint of regular files in one temp directory."""
    return sum(candidate.stat().st_size for candidate in directory.glob("*") if candidate.is_file())
