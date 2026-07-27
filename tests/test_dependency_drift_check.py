"""Focused tests for the lightweight dependency-drift guard."""

from __future__ import annotations

import importlib
from pathlib import Path
import sys


SCRIPTS_DIR = Path(__file__).resolve().parent.parent / ".github" / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

check_dependency_drift = importlib.import_module("check_dependency_drift")


def _assert_message_contains(classification: str, expected: str) -> None:
    """Assert one dependency-drift classification message fragment."""
    message = check_dependency_drift.dependency_drift_message(classification)
    assert expected in message


def test_no_dependency_change_is_clean() -> None:
    classification = check_dependency_drift.classify_dependency_drift(
        ["README.md", "docs/testing-and-validation.md"]
    )

    assert classification == check_dependency_drift.CLASS_NONE
    _assert_message_contains(classification, "no dependency metadata changes")


def test_paired_dependency_change_is_allowed() -> None:
    classification = check_dependency_drift.classify_dependency_drift(
        ["pyproject.toml", "uv.lock", "README.md"]
    )

    assert classification == check_dependency_drift.CLASS_PAIRED
    _assert_message_contains(classification, "both changed")


def test_pyproject_only_change_stays_advisory() -> None:
    classification = check_dependency_drift.classify_dependency_drift(
        ["pyproject.toml", "docs/README.md"]
    )

    assert classification == check_dependency_drift.CLASS_PYPROJECT_ONLY
    _assert_message_contains(classification, "lock refresh was not needed")


def test_lock_only_change_is_flagged() -> None:
    classification = check_dependency_drift.classify_dependency_drift(
        ["uv.lock", "tests/test_detector_lab_runner.py"]
    )

    assert classification == check_dependency_drift.CLASS_LOCK_ONLY
    _assert_message_contains(classification, "incidental local drift")
