"""Focused tests for the lightweight dependency-drift guard."""

from __future__ import annotations

import importlib
import re
import sys
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / ".github" / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

check_dependency_drift = importlib.import_module("check_dependency_drift")
PYPROJECT_PATH = REPO_ROOT / "pyproject.toml"
REQUIREMENTS_PATH = REPO_ROOT / "requirements.txt"
UV_LOCK_PATH = REPO_ROOT / "uv.lock"
PROJECT_NAME = "election-stream-monitor"
FOCUSED_EXTRA_TOOLS = {
    "detectorlab": frozenset({"numpy", "opencv-python-headless"}),
    "test": frozenset({"httpx", "pytest", "pyyaml"}),
    "lint": frozenset({"black", "ruff"}),
    "security": frozenset({"bandit", "pip-audit"}),
    "typecheck": frozenset({"mypy", "pyright"}),
}
ENGINEERING_TOOLS = frozenset().union(*FOCUSED_EXTRA_TOOLS.values(), {"pre-commit"})


def _package_names(requirements: list[str]) -> frozenset[str]:
    """Return normalized distribution names without parsing version policy."""
    return frozenset(
        re.split(r"[<>=!~;\[]", requirement, maxsplit=1)[0].lower()
        for requirement in requirements
    )


def _project_metadata() -> dict[str, object]:
    """Load the project metadata governed by the dependency policy."""
    with PYPROJECT_PATH.open("rb") as pyproject_file:
        return tomllib.load(pyproject_file)["project"]


def _lock_metadata() -> dict[str, object]:
    """Load the locked dependency metadata without resolving packages."""
    with UV_LOCK_PATH.open("rb") as lock_file:
        return tomllib.load(lock_file)


def _locked_project_metadata(lock: dict[str, object]) -> dict[str, object]:
    """Return the editable root package recorded by uv.lock."""
    return next(
        package for package in lock["package"] if package["name"] == PROJECT_NAME
    )


def _locked_package_names(requirements: list[dict[str, object]]) -> frozenset[str]:
    """Return distribution names from one lockfile dependency collection."""
    return frozenset(str(requirement["name"]) for requirement in requirements)


def _assert_message_contains(classification: str, expected: str) -> None:
    """Assert one dependency-drift classification message fragment."""
    message = check_dependency_drift.dependency_drift_message(classification)
    assert expected in message


def test_no_dependency_change_is_clean() -> None:
    """Non-dependency edits must not produce a dependency warning."""
    classification = check_dependency_drift.classify_dependency_drift(
        ["README.md", "docs/testing-and-validation.md"]
    )

    assert classification == check_dependency_drift.CLASS_NONE
    _assert_message_contains(classification, "no dependency metadata changes")


def test_paired_dependency_change_is_allowed() -> None:
    """Paired declared-source and lockfile updates are an expected change shape."""
    classification = check_dependency_drift.classify_dependency_drift(
        ["pyproject.toml", "uv.lock", "README.md"]
    )

    assert classification == check_dependency_drift.CLASS_PAIRED
    _assert_message_contains(classification, "both changed")


def test_pyproject_only_change_stays_advisory() -> None:
    """Source-only changes need an explanation but do not fail this guard."""
    classification = check_dependency_drift.classify_dependency_drift(
        ["pyproject.toml", "docs/README.md"]
    )

    assert classification == check_dependency_drift.CLASS_PYPROJECT_ONLY
    _assert_message_contains(classification, "lock refresh was not needed")


def test_lock_only_change_is_flagged() -> None:
    """A lock-only change remains a likely incidental-drift signal."""
    classification = check_dependency_drift.classify_dependency_drift(
        ["uv.lock", "tests/test_detector_lab_runner.py"]
    )

    assert classification == check_dependency_drift.CLASS_LOCK_ONLY
    _assert_message_contains(classification, "incidental local drift")


def test_runtime_dependencies_exclude_engineering_tools() -> None:
    """Base installation must not directly acquire contributor tooling."""
    project = _project_metadata()

    assert ENGINEERING_TOOLS.isdisjoint(_package_names(project["dependencies"]))


def test_focused_extras_retain_required_tools() -> None:
    """Keep CI and contributor tools in their named extras."""
    extras = _project_metadata()["optional-dependencies"]

    for extra, required_tools in FOCUSED_EXTRA_TOOLS.items():
        assert required_tools <= _package_names(extras[extra])

    assert "bandit" not in _package_names(extras["lint"])


def test_dev_extra_composes_focused_extras() -> None:
    """Keep contributor setup from duplicating focused-extra version policy."""
    extras = _project_metadata()["optional-dependencies"]
    dev_requirements = extras["dev"]

    assert _package_names(dev_requirements) == {PROJECT_NAME, "pre-commit"}
    assert (
        f"{PROJECT_NAME}[detectorlab,lint,security,test,typecheck]"
        in dev_requirements
    )


def test_repository_has_no_unmanaged_requirements_snapshot() -> None:
    """Keep dependency resolution owned by project metadata and uv.lock."""
    assert not REQUIREMENTS_PATH.exists()


def test_lock_metadata_matches_dependency_ownership() -> None:
    """Keep the resolved root package aligned with declared extras."""
    project = _project_metadata()
    lock = _lock_metadata()
    locked_project = _locked_project_metadata(lock)
    extras = project["optional-dependencies"]
    locked_extras = locked_project["optional-dependencies"]

    assert project["requires-python"] == lock["requires-python"]
    assert set(extras) == set(locked_extras)
    assert ENGINEERING_TOOLS.isdisjoint(
        _locked_package_names(locked_project["dependencies"])
    )
    for extra, required_tools in FOCUSED_EXTRA_TOOLS.items():
        assert required_tools <= _locked_package_names(locked_extras[extra])
