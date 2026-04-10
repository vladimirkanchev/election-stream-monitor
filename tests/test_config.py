"""Sanity checks for active project configuration."""

from pathlib import Path

import config


def test_config_uses_supported_data_source() -> None:
    """DATA_SOURCE should stay within the supported runtime modes."""
    assert config.DATA_SOURCE in {"video_segments", "video_files", "api_stream"}


def test_config_paths_and_schemas_are_defined() -> None:
    """Configured output paths and schemas should be present and non-empty."""
    assert isinstance(config.VIDEO_METRICS_PATH, Path)
    assert isinstance(config.VIDEO_INPUT_FOLDER, Path)
    assert config.VIDEO_METRICS_COLUMNS
    assert config.BLUR_METRICS_COLUMNS
