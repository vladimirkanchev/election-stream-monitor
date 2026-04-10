"""Thread-safe buffered CSV stores for analysis results."""

import threading
from pathlib import Path

import pandas as pd

import config
from logger import logger


class BufferedCsvStore:
    """Thread-safe in-memory buffer that flushes rows to a CSV file.

    The store accepts flat dictionaries, aligns them to the configured column
    order, buffers them in memory, and writes them to disk in batches.
    """

    def __init__(
        self,
        columns: list[str],
        file_path: str | Path,
        buffer_size: int = 500,
    ) -> None:
        """Initialize the buffered CSV store.

        Args:
            columns: Ordered CSV columns expected for this output type.
            file_path: Destination CSV file.
            buffer_size: Number of buffered rows before auto-flushing.
        """
        self.columns = columns
        self.df = pd.DataFrame(columns=self.columns)
        self.buffer_size = buffer_size
        self.file_path = Path(file_path)
        self.lock = threading.Lock()

    def add_row(self, row: dict) -> None:
        """Append one result row to the buffer."""
        self.add_rows([row])

    def add_rows(self, rows: list[dict]) -> None:
        """Append multiple result rows and auto-flush if needed."""
        if not rows:
            return

        with self.lock:
            valid_rows = [
                row
                for row in rows
                if isinstance(row, dict)
                and row
                and any(column in row for column in self.columns)
            ]
            if not valid_rows:
                logger.debug("No valid rows to append.")
                return

            new_df = pd.DataFrame.from_records(valid_rows)
            if new_df.dropna(how="all").empty:
                logger.debug("Skipped adding empty rows (all NaN).")
                return

            new_df = new_df.reindex(columns=self.columns, fill_value=None)
            frames = [frame for frame in (self.df, new_df) if not frame.empty]
            self.df = pd.concat(frames, ignore_index=True)

            logger.debug(
                "Appended %d rows (buffer size now %d).", len(valid_rows), len(self.df)
            )
            if len(self.df) >= self.buffer_size:
                self._flush()

    def flush(self) -> None:
        """Write all currently buffered rows to disk immediately."""
        with self.lock:
            if not self.df.empty:
                self._flush()

    def __len__(self) -> int:
        """Return the number of rows currently held in memory."""
        with self.lock:
            return len(self.df)

    def _flush(self) -> None:
        """Write buffered rows to the target CSV and clear the buffer."""
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        write_header = not self.file_path.exists()
        try:
            self.df.to_csv(
                self.file_path,
                mode="a",
                header=write_header,
                index=False,
            )
            logger.info("Flushed %d rows -> %s", len(self.df), self.file_path)
            self.df = pd.DataFrame(columns=self.columns)
        except OSError as err:
            logger.error("Failed to flush buffer to %s: %s", self.file_path, err)
            raise


black_frame_store = BufferedCsvStore(
    columns=config.VIDEO_METRICS_COLUMNS,
    buffer_size=config.STORE_BUFFER_SIZE,
    file_path=config.VIDEO_METRICS_PATH,
)
blur_metrics_store = BufferedCsvStore(
    columns=config.BLUR_METRICS_COLUMNS,
    buffer_size=config.STORE_BUFFER_SIZE,
    file_path=config.BLUR_METRICS_PATH,
)
