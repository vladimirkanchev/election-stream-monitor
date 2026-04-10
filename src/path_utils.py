"""Path resolution helpers for local app-facing inputs."""

from __future__ import annotations

from pathlib import Path

import config


def resolve_app_input_path(input_path: str | Path) -> Path:
    """Resolve a user-facing path into a concrete local filesystem path.

    The frontend currently uses repo-style paths such as ``/data/streams/segments``.
    If such a path does not exist on the host filesystem, treat it as relative to
    the project root. For local debugging the same remapping also applies to
    ``tests/...`` fixture paths.
    """
    candidate = Path(input_path).expanduser()
    if candidate.exists():
        return candidate

    candidate_text = str(input_path).strip()
    for repo_prefix in ("/data/", "data/", "/tests/", "tests/"):
        if candidate_text.startswith(repo_prefix):
            project_relative = config.PROJECT_ROOT / candidate_text.lstrip("/")
            return project_relative

    return candidate
