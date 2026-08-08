"""Regression coverage for bounded Dependabot update proposals."""

from __future__ import annotations

import tomllib
from pathlib import Path

import yaml

DEPENDABOT_PATH = Path(".github/dependabot.yml")
PYPROJECT_PATH = Path("pyproject.toml")
EXPECTED_ECOSYSTEM_DIRECTORIES = {
    ("uv", "/"),
    ("npm", "/frontend"),
    ("github-actions", "/"),
}
PYTHON_ENGINEERING_PACKAGES = {
    "pytest",
    "pytest-cov",
    "httpx",
    "pyyaml",
    "black",
    "ruff",
    "bandit",
    "pip-audit",
    "mypy",
    "pyright",
    "pre-commit",
}


def _dependabot_config() -> dict[str, object]:
    """Load the checked-in Dependabot policy without relying on YAML layout."""
    return yaml.safe_load(DEPENDABOT_PATH.read_text(encoding="utf-8"))


def _updates_by_ecosystem(
    config: dict[str, object],
) -> dict[tuple[str, str], dict[str, object]]:
    """Index update entries by their ecosystem and manifest directory."""
    updates = config["updates"]
    assert isinstance(updates, list)

    return {
        (str(update["package-ecosystem"]), str(update["directory"])): update
        for update in updates
    }


def _single_group(update: dict[str, object]) -> dict[str, object]:
    """Return the one reviewed group without depending on its YAML key or order."""
    groups = update["groups"]
    assert isinstance(groups, dict)
    assert len(groups) == 1
    return next(iter(groups.values()))


def _optional_dependency_names() -> set[str]:
    """Return normalized optional package names from project metadata."""
    with PYPROJECT_PATH.open("rb") as pyproject_file:
        project = tomllib.load(pyproject_file)["project"]

    extras = project["optional-dependencies"]
    return {
        requirement.split("[", maxsplit=1)[0].split(">", maxsplit=1)[0].lower()
        for requirements in extras.values()
        for requirement in requirements
        if not requirement.startswith("election-stream-monitor[")
    }


def test_dependabot_covers_the_reviewed_dependency_owners() -> None:
    """Keep Python, frontend, and workflow updates on their owned manifests."""
    config = _dependabot_config()
    updates = _updates_by_ecosystem(config)

    assert config["version"] == 2
    assert set(updates) == EXPECTED_ECOSYSTEM_DIRECTORIES
    for update in updates.values():
        assert update["target-branch"] == "main"
        assert update["schedule"]["interval"] == "weekly"
        assert update["open-pull-requests-limit"] == 3


def test_dependabot_groups_only_non_major_version_updates() -> None:
    """Keep security and major updates separate for focused review."""
    updates = _updates_by_ecosystem(_dependabot_config())

    for update in updates.values():
        groups = update["groups"]
        assert isinstance(groups, dict)
        for group in groups.values():
            assert group["applies-to"] == "version-updates"
            assert set(group["update-types"]) == {"minor", "patch"}


def test_dependabot_python_group_stays_limited_to_engineering_packages() -> None:
    """Prevent broad Python grouping from hiding runtime dependency changes."""
    updates = _updates_by_ecosystem(_dependabot_config())
    python_group = _single_group(updates[("uv", "/")])

    patterns = {str(pattern).lower() for pattern in python_group["patterns"]}
    assert patterns == PYTHON_ENGINEERING_PACKAGES
    assert patterns <= _optional_dependency_names()


def test_dependabot_frontend_group_stays_development_only() -> None:
    """Keep production frontend dependency changes separately diagnosable."""
    updates = _updates_by_ecosystem(_dependabot_config())
    frontend_group = _single_group(updates[("npm", "/frontend")])

    assert frontend_group["dependency-type"] == "development"
    assert frontend_group["patterns"] == ["*"]


def test_dependabot_does_not_configure_credentials_or_automatic_remediation() -> None:
    """Keep update proposals credential-free and subject to normal review."""
    config = _dependabot_config()
    updates = _updates_by_ecosystem(config)

    assert "registries" not in config
    for update in updates.values():
        assert "registries" not in update
        assert "insecure-external-code-execution" not in update
        assert "auto-merge" not in update
        assert "automerge" not in update
