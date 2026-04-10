"""Tests for buffered CSV persistence."""

from pathlib import Path

from stores import BufferedCsvStore


def test_buffered_csv_store_flushes_rows_to_disk(tmp_path: Path) -> None:
    """Flush should persist buffered rows and clear the in-memory buffer."""
    file_path = tmp_path / "metrics.csv"
    store = BufferedCsvStore(
        columns=["source_name", "processing_sec"],
        file_path=file_path,
        buffer_size=10,
    )

    store.add_row({"source_name": "segment_0001.ts", "processing_sec": 0.12})
    store.add_row({"source_name": "segment_0002.ts", "processing_sec": 0.34})
    store.flush()

    assert len(store) == 0
    assert file_path.exists()

    lines = file_path.read_text(encoding="utf-8").strip().splitlines()
    assert lines[0] == "source_name,processing_sec"
    assert len(lines) == 3


def test_buffered_csv_store_ignores_invalid_rows(tmp_path: Path) -> None:
    """Invalid or empty rows should not be appended to the store."""
    store = BufferedCsvStore(
        columns=["source_name", "processing_sec"],
        file_path=tmp_path / "metrics.csv",
        buffer_size=10,
    )

    store.add_rows([{}, {"source_name": "ok.ts", "processing_sec": 0.1}])

    assert len(store) == 1


def test_buffered_csv_store_auto_flushes_at_buffer_limit(tmp_path: Path) -> None:
    """Store should write automatically once the configured buffer limit is reached."""
    file_path = tmp_path / "metrics.csv"
    store = BufferedCsvStore(
        columns=["source_name", "processing_sec"],
        file_path=file_path,
        buffer_size=2,
    )

    store.add_row({"source_name": "segment_0001.ts", "processing_sec": 0.12})
    store.add_row({"source_name": "segment_0002.ts", "processing_sec": 0.34})

    assert len(store) == 0
    assert file_path.exists()

    lines = file_path.read_text(encoding="utf-8").strip().splitlines()
    assert lines[0] == "source_name,processing_sec"
    assert len(lines) == 3


def test_buffered_csv_store_raises_and_keeps_buffer_when_flush_fails(
    monkeypatch, tmp_path: Path
) -> None:
    """Flush failures should remain visible and keep buffered rows intact for retry."""
    file_path = tmp_path / "metrics.csv"
    store = BufferedCsvStore(
        columns=["source_name", "processing_sec"],
        file_path=file_path,
        buffer_size=10,
    )
    store.add_row({"source_name": "segment_0001.ts", "processing_sec": 0.12})

    def fail_to_csv(*args, **kwargs):  # type: ignore[no-untyped-def]
        _ = (args, kwargs)
        raise OSError("disk full")

    monkeypatch.setattr(store.df, "to_csv", fail_to_csv)

    try:
        store.flush()
    except OSError as error:
        assert "disk full" in str(error)
    else:
        raise AssertionError("Expected CSV flush failure to propagate")

    assert len(store) == 1
