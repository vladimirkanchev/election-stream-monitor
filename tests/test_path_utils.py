"""Tests for app-facing input path resolution."""

from pathlib import Path

import config
from path_utils import resolve_app_input_path


def test_resolve_repo_style_data_path(monkeypatch, tmp_path: Path) -> None:
    """Repo-style `/data/...` inputs should resolve under the project root."""
    monkeypatch.setattr(config, "PROJECT_ROOT", tmp_path)

    resolved = resolve_app_input_path("/data/streams/segments")

    assert resolved == tmp_path / "data/streams/segments"


def test_resolve_repo_style_test_fixture_path(monkeypatch, tmp_path: Path) -> None:
    """Repo-style `/tests/...` inputs should resolve under the project root."""
    monkeypatch.setattr(config, "PROJECT_ROOT", tmp_path)

    resolved = resolve_app_input_path("/tests/fixtures/media/video_segments/black_trigger")

    assert resolved == tmp_path / "tests/fixtures/media/video_segments/black_trigger"
