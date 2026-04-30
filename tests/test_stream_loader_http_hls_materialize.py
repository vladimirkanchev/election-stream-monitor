"""Direct tests for the HTTP/HLS temp-materialization helper module.

These cases keep the loader-level suites focused on live-loader behavior while
locking down the atomic-write and byte-accounting helpers directly.
"""

from pathlib import Path

import pytest

from stream_loader_http_hls_materialize import (
    _count_file_bytes_in_directory,
    _write_api_stream_temp_file,
)


def test_write_api_stream_temp_file_atomically_replaces_existing_payload(tmp_path: Path) -> None:
    """Atomic materialization should replace the target file without leaving a part file behind."""
    target = tmp_path / "segment.ts"
    target.write_text("old")

    _write_api_stream_temp_file(target, b"new-payload")

    assert target.read_bytes() == b"new-payload"
    assert not target.with_suffix(".ts.part").exists()


def test_write_api_stream_temp_file_replaces_stale_partial_and_existing_target(
    tmp_path: Path,
) -> None:
    """Atomic materialization should tolerate an already-stale part file cleanly."""
    target = tmp_path / "segment.ts"
    target.write_text("old")
    target.with_suffix(".ts.part").write_text("stale")

    _write_api_stream_temp_file(target, b"replacement")

    assert target.read_bytes() == b"replacement"
    assert not target.with_suffix(".ts.part").exists()


def test_write_api_stream_temp_file_cleans_up_partial_file_on_failure(tmp_path: Path, monkeypatch) -> None:
    """Atomic materialization should remove partial output if writing fails."""
    target = tmp_path / "segment.ts"

    def fail_write_bytes(self, payload: bytes) -> int:
        raise OSError("disk full")

    monkeypatch.setattr(Path, "write_bytes", fail_write_bytes)

    with pytest.raises(OSError, match="disk full"):
        _write_api_stream_temp_file(target, b"payload")

    assert not target.exists()
    assert not target.with_suffix(".ts.part").exists()


def test_count_file_bytes_in_directory_counts_regular_files_only(tmp_path: Path) -> None:
    """Byte accounting should ignore nested directories and only sum regular files."""
    (tmp_path / "a.bin").write_bytes(b"abc")
    (tmp_path / "b.bin").write_bytes(b"de")
    (tmp_path / "nested").mkdir()
    (tmp_path / "nested" / "ignored.bin").write_bytes(b"zzz")

    assert _count_file_bytes_in_directory(tmp_path) == 5
