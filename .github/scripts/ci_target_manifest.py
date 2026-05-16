#!/usr/bin/env python3
"""Shared manifest-loading helpers for CI target scripts.

The CI hardening scripts all read the same manifest. This module keeps that
parsing logic in one place so workflow readers, validators, drift checks, and
policy checks share the same assumptions.

At the current repo shape, the manifest already covers the broad shared
`ci.yml` contract consumers. The remaining tiny smoke path stays inline on
purpose, so consumers can rely on this module for shared target groups without
turning every workflow test invocation into manifest data. That keeps only
genuinely small one-off workflow lists outside the shared selector surface.

The manifest also records the current path-owning CI surface and the intended
scope of the future path-existence self-check: CI-owned test paths belong in
that guard, while non-test source files and docs rules stay outside it.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import cache
import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = REPO_ROOT / ".github" / "ci_test_targets.json"


class ManifestError(ValueError):
    """Raised when the CI target manifest is missing required structure."""


def _load_json_object(path: Path) -> dict[str, object]:
    """Load one manifest file and require an object root."""
    raw = json.loads(path.read_text())
    if not isinstance(raw, dict):
        raise ManifestError("CI target manifest root must be an object.")
    return raw


def _require_mapping(raw: object, field_name: str) -> dict[str, object]:
    """Return one manifest object field as a dict."""
    if not isinstance(raw, dict):
        raise ManifestError(f"CI target manifest is missing the '{field_name}' object.")
    return raw


def _require_string_list(raw: object, field_name: str) -> tuple[str, ...]:
    """Return one manifest list field as a tuple of strings."""
    if not isinstance(raw, list):
        raise ManifestError(f"CI target manifest field '{field_name}' must be a list.")
    return tuple(str(item) for item in raw)


def _ordered_unique_paths(relative_paths: tuple[str, ...]) -> tuple[str, ...]:
    """Return one path tuple with duplicates removed and order preserved."""
    ordered_unique_paths: list[str] = []
    seen_paths: set[str] = set()

    for relative_path in relative_paths:
        if relative_path in seen_paths:
            continue
        seen_paths.add(relative_path)
        ordered_unique_paths.append(relative_path)

    return tuple(ordered_unique_paths)


@dataclass(frozen=True)
class OwnershipBoundary:
    """Approved ownership boundary declared inside the CI target manifest."""

    included_target_groups: tuple[str, ...]
    excluded_target_categories: tuple[str, ...]
    current_consumers: tuple[str, ...]


@dataclass(frozen=True)
class PathExistenceInventory:
    """Current CI-owned test-path surface for the existence self-check."""

    workflow_manifest_groups: tuple[str, ...]
    workflow_inline_test_paths: tuple[str, ...]
    policy_manifest_groups: tuple[str, ...]
    policy_only_test_paths: tuple[str, ...]


@dataclass(frozen=True)
class CiTargetManifest:
    """Parsed CI target manifest with stable, consumer-friendly accessors.

    The manifest models only the shared CI-critical target groups. It does not
    try to absorb every small one-off workflow test path. Its raw data also
    carries the current path-existence inventory and boundary notes that the
    validator protects.
    """

    path: Path
    raw: dict[str, object]
    format_type: str
    targets: dict[str, tuple[str, ...]]
    ownership_boundary: OwnershipBoundary
    path_existence_inventory: PathExistenceInventory

    @classmethod
    def load(cls, path: Path = MANIFEST_PATH) -> "CiTargetManifest":
        """Load and normalize the canonical CI target manifest from disk."""
        raw = _load_json_object(path)
        format_data = _require_mapping(raw.get("format"), "format")
        targets_data = _require_mapping(raw.get("targets"), "targets")
        boundary_data = _require_mapping(
            raw.get("ownership_boundary"),
            "ownership_boundary",
        )
        path_existence_data = _require_mapping(
            raw.get("path_existence_inventory"),
            "path_existence_inventory",
        )

        targets = {
            group_name: _require_string_list(group_value, f"targets.{group_name}")
            for group_name, group_value in targets_data.items()
        }

        boundary = OwnershipBoundary(
            included_target_groups=_require_string_list(
                boundary_data.get("included_target_groups"),
                "ownership_boundary.included_target_groups",
            ),
            excluded_target_categories=_require_string_list(
                boundary_data.get("excluded_target_categories"),
                "ownership_boundary.excluded_target_categories",
            ),
            current_consumers=_require_string_list(
                boundary_data.get("current_consumers"),
                "ownership_boundary.current_consumers",
            ),
        )

        path_existence_inventory = PathExistenceInventory(
            workflow_manifest_groups=_require_string_list(
                path_existence_data.get("workflow_manifest_groups"),
                "path_existence_inventory.workflow_manifest_groups",
            ),
            workflow_inline_test_paths=_require_string_list(
                path_existence_data.get("workflow_inline_test_paths"),
                "path_existence_inventory.workflow_inline_test_paths",
            ),
            policy_manifest_groups=_require_string_list(
                path_existence_data.get("policy_manifest_groups"),
                "path_existence_inventory.policy_manifest_groups",
            ),
            policy_only_test_paths=_require_string_list(
                path_existence_data.get("policy_only_test_paths"),
                "path_existence_inventory.policy_only_test_paths",
            ),
        )

        return cls(
            path=path,
            raw=raw,
            format_type=str(format_data.get("type", "")),
            targets=targets,
            ownership_boundary=boundary,
            path_existence_inventory=path_existence_inventory,
        )

    def group_names(self) -> tuple[str, ...]:
        """Return the stable top-level manifest group names."""
        return tuple(self.targets.keys())

    def group_targets(self, group_name: str) -> tuple[str, ...]:
        """Return one stable manifest target group by name."""
        try:
            return self.targets[group_name]
        except KeyError as exc:
            raise ManifestError(
                f"Unknown CI target manifest group: {group_name}"
            ) from exc

    def all_target_paths(self) -> tuple[str, ...]:
        """Return every target path across every stable manifest group."""
        return tuple(
            target_path
            for group_name in self.group_names()
            for target_path in self.targets[group_name]
        )

    def path_existence_paths(self) -> tuple[str, ...]:
        """Return every CI-owned test path covered by the existence guard."""
        inventory = self.path_existence_inventory
        workflow_group_paths = tuple(
            target_path
            for group_name in inventory.workflow_manifest_groups
            for target_path in self.group_targets(group_name)
        )
        policy_group_paths = tuple(
            target_path
            for group_name in inventory.policy_manifest_groups
            for target_path in self.group_targets(group_name)
        )
        return (
            workflow_group_paths
            + inventory.workflow_inline_test_paths
            + policy_group_paths
            + inventory.policy_only_test_paths
        )

    def workflow_inline_test_paths(self) -> tuple[str, ...]:
        """Return the explicit inline workflow test-path exceptions."""
        return self.path_existence_inventory.workflow_inline_test_paths

    def unique_path_existence_paths(self) -> tuple[str, ...]:
        """Return the deduplicated CI-owned test paths for the existence guard."""
        return _ordered_unique_paths(self.path_existence_paths())


@cache
def load_ci_target_manifest() -> CiTargetManifest:
    """Return the cached canonical CI target manifest for Python-side consumers."""
    return CiTargetManifest.load()


def manifest_group_targets(group_name: str) -> tuple[str, ...]:
    """Return one stable target group through the shared manifest access seam."""
    return load_ci_target_manifest().group_targets(group_name)


def ci_owned_test_paths() -> tuple[str, ...]:
    """Return the deduplicated CI-owned test-path inventory."""
    return load_ci_target_manifest().unique_path_existence_paths()


def workflow_inline_ci_test_paths() -> tuple[str, ...]:
    """Return the explicit inline workflow test-path exceptions."""
    return load_ci_target_manifest().workflow_inline_test_paths()
