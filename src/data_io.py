"""Local file discovery, loading, and replay helpers for video inputs."""

import time
from pathlib import Path
from typing import Callable, Optional

import config
from logger import logger


# pylint: disable=too-many-branches
def stream_local_prefix(
    prefix: str,
    on_segment: Optional[Callable[[Path, str], None]] = None,
    poll_interval: float = 2.0,
    max_segments: Optional[int] = None,
) -> None:
    """
    Replay local input files in timestamp order and dispatch them for analysis.

    The input directory and file suffix filter are selected from
    ``config.DATA_SOURCE``. Every discovered file is loaded first, then passed
    to ``on_segment`` if a callback is provided.

    Args:
        prefix: Folder name under the configured input root.
        on_segment: Optional callback that receives ``(file_path, prefix)``.
        poll_interval: Delay between dispatched files, in seconds.
        max_segments: Optional upper bound on processed files for the run.
    """
    if config.DATA_SOURCE == "video_segments":
        base_dir = config.VIDEO_INPUT_FOLDER / prefix
        patterns = ("*.ts",)
    elif config.DATA_SOURCE == "video_files":
        base_dir = config.VIDEO_INPUT_FOLDER / prefix
        patterns = ("*.mp4",)
    else:
        raise ValueError(
            f"Unsupported DATA_SOURCE={config.DATA_SOURCE!r}. "
            "Expected 'video_segments' or 'video_files'."
        )

    if not base_dir.exists():
        logger.error("Local directory not found: %s", base_dir)
        return

    logger.info("Starting local stream from: %s", base_dir)

    # Sort by modification time to simulate stream arrival order
    all_files = sorted(
        [file_path for pattern in patterns for file_path in base_dir.glob(pattern)],
        key=lambda p: p.stat().st_mtime,
    )
    seen = set()
    count = 0

    for file_path in all_files:
        if file_path.name in seen:
            continue
        seen.add(file_path.name)
        count += 1

        start_time = time.time()
        logger.info("Processing file: %s", file_path.name)

        data = load_video_file(file_path.name, prefix)

        if data is None:
            logger.warning("Skipped empty or unreadable file: %s", file_path.name)
            continue

        duration_sec = time.time() - start_time
        logger.info(
            "Loaded %s (%d bytes) in %.2fs", file_path.name, len(data), duration_sec
        )

        # Run the analysis callback for the current file.
        if on_segment:
            try:
                on_segment(file_path, prefix)
            except OSError as err:
                logger.error("Error in on_segment for %s: %s", file_path.name, err)

        if max_segments and count >= max_segments:
            logger.info("Reached max segment limit: %d", max_segments)
            break

        time.sleep(poll_interval)

    logger.info("Completed local playback simulation for prefix: %s", prefix)


def load_video_file(key: str, prefix: str) -> bytes | None:
    """Load one local video file as raw bytes.

    Args:
        key: File name or path-like key. Only the final file name is used.
        prefix: Folder under ``config.VIDEO_INPUT_FOLDER`` where the file lives.

    Returns:
        The file content as ``bytes``, or ``None`` if the file cannot be read.
    """
    try:
        local_path = config.VIDEO_INPUT_FOLDER / prefix / Path(key).name
        with open(local_path, "rb") as file:
            data = file.read()
        logger.debug("Loaded %s (%d bytes)", local_path, len(data))
        return data
    except OSError as err:
        logger.error("Failed to load %s: %s", key, err)
        return None
