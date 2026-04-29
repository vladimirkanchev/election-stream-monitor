"""Legacy dev-only local analysis harness.

This module is kept only as a lightweight developer tool for the older
file-based local analysis path. It is not part of the canonical runtime
architecture.

The supported runtime flow for the product is:

FastAPI -> session service -> detached ``run-session`` worker -> session runner

This module is therefore not used for:

- session lifecycle ownership
- ``api_stream`` execution
- frontend or Electron flows

Keep this module as a thin legacy wrapper around the older local-file helper
functions. Do not add session/runtime features here; new behavior should live
in the canonical FastAPI/session-service/session-runner path or in a separate
developer script under ``scripts/``.

TODO: remove this module once focused pytest coverage is accepted as the
replacement for the older local-file path. Do not add a new manual tooling
script unless a recurring local detector-debug workflow proves it is needed.
"""

from functools import partial

import config
from data_io import stream_local_prefix
from logger import logger
from processor import process_video_file
from stores import black_frame_store, blur_metrics_store


def main() -> None:
    """Run the legacy local-file analysis harness for supported local modes.

    This helper exists only for narrow developer-oriented smoke runs of the
    older file-based path. It supports ``video_segments`` and ``video_files``
    only, delegates local discovery to ``data_io.stream_local_prefix``, and
    flushes buffered stores before exit.

    It is not part of the canonical runtime architecture and does not own:

    - session lifecycle or session snapshots
    - ``api_stream`` execution
    - worker logging or observability
    - FastAPI or Electron flows

    Keep this function intentionally small. It should remain a thin wrapper
    over existing low-level local-file helpers and should not duplicate
    validation, session, or worker behavior from the supported runtime path.
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
            f"Unsupported DATA_SOURCE={config.DATA_SOURCE!r} for the legacy "
            "local analysis harness. Expected 'video_segments' or "
            "'video_files'; use the FastAPI/session-service runtime for "
            "session, api_stream, and frontend flows."
        )

    black_frame_store.flush()
    blur_metrics_store.flush()
    logger.info("Local analysis run completed.")


if __name__ == "__main__":
    main()
