"""Main entry point for local video analysis."""

from functools import partial

import config
from data_io import stream_local_prefix
from logger import logger
from processor import process_video_file
from stores import black_frame_store, blur_metrics_store


def main() -> None:
    """Run the local analysis pipeline for the configured input mode.

    This function is the runtime entrypoint for the project. It selects the
    correct input mode from ``config.DATA_SOURCE``, delegates file discovery to
    ``data_io.stream_local_prefix``, and flushes buffered CSV stores before
    exit.
    """
    logger.info("Starting local analysis run...")

    if config.DATA_SOURCE == "video_segments":
        stream_local_prefix(
            prefix="segments",
            on_segment=partial(process_video_file, mode="video_segments"),
            poll_interval=0.5,
            max_segments=900,
        )
        logger.info("Processed video segments.")
    elif config.DATA_SOURCE == "video_files":
        stream_local_prefix(
            prefix="segments",
            on_segment=partial(process_video_file, mode="video_files"),
            poll_interval=0.5,
            max_segments=900,
        )
        logger.info("Processed video files.")
    else:
        raise ValueError(
            f"Unsupported DATA_SOURCE={config.DATA_SOURCE!r}. "
            "Expected 'video_segments' or 'video_files'."
        )

    black_frame_store.flush()
    blur_metrics_store.flush()
    logger.info("Local analysis run completed.")


if __name__ == "__main__":
    main()
