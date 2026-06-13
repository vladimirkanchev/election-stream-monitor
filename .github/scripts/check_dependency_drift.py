#!/usr/bin/env python3
"""Lightweight guard for suspicious dependency metadata drift."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from pathlib import Path
import subprocess
import sys


REPO_ROOT = Path(__file__).resolve().parents[2]
PYPROJECT_FILE = "pyproject.toml"
LOCK_FILE = "uv.lock"

CLASS_NONE = "none"
CLASS_PAIRED = "paired"
CLASS_PYPROJECT_ONLY = "pyproject-only"
CLASS_LOCK_ONLY = "lock-only"


def _git_changed_paths(args: Sequence[str]) -> tuple[str, ...]:
    """Return changed repo-relative paths for one git diff invocation."""
    result = subprocess.run(
        ["git", *args],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return tuple(path for path in result.stdout.splitlines() if path)


def changed_paths() -> tuple[str, ...]:
    """Return the smallest useful current change set for dependency checks.

    Prefer staged paths when they exist so local review matches the next
    commit. Fall back to the working tree when the user wants a cheap
    read-only drift check before staging.
    """
    staged = _git_changed_paths(["diff", "--cached", "--name-only", "--diff-filter=ACMR"])
    if staged:
        return staged
    return _git_changed_paths(["diff", "--name-only", "HEAD", "--diff-filter=ACMR"])


def classify_dependency_drift(paths: Iterable[str]) -> str:
    """Classify the current dependency metadata change shape."""
    changed = set(paths)
    pyproject_changed = PYPROJECT_FILE in changed
    lock_changed = LOCK_FILE in changed

    if pyproject_changed and lock_changed:
        return CLASS_PAIRED
    if lock_changed:
        return CLASS_LOCK_ONLY
    if pyproject_changed:
        return CLASS_PYPROJECT_ONLY
    return CLASS_NONE


def dependency_drift_message(classification: str) -> str:
    """Return the operator-facing message for the detected classification."""
    if classification == CLASS_NONE:
        return "dependency drift check passed: no dependency metadata changes detected"
    if classification == CLASS_PAIRED:
        return (
            "dependency drift check passed: `pyproject.toml` and `uv.lock` both changed; "
            "keep the PR or commit explanation explicit"
        )
    if classification == CLASS_PYPROJECT_ONLY:
        return (
            "dependency drift check passed: `pyproject.toml` changed without `uv.lock`; "
            "make sure the PR or commit explains why a lock refresh was not needed"
        )
    if classification == CLASS_LOCK_ONLY:
        return (
            "dependency drift check failed: `uv.lock` changed without `pyproject.toml`; "
            "this often means incidental local drift, so remove it or explain clearly why it belongs"
        )
    raise ValueError(f"unknown dependency drift classification: {classification}")


def main() -> int:
    """Run the lightweight dependency-drift guard."""
    classification = classify_dependency_drift(changed_paths())
    print(dependency_drift_message(classification))
    return 1 if classification == CLASS_LOCK_ONLY else 0


if __name__ == "__main__":
    sys.exit(main())
