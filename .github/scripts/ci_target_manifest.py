#!/usr/bin/env python3
"""Shared manifest-loading helpers for CI target scripts.

The CI hardening scripts all read the same manifest. This module keeps that
parsing logic in one place so workflow readers, validators, drift checks, and
policy checks share the same assumptions.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = REPO_ROOT / ".github" / "ci_test_targets.json"


class ManifestError(ValueError):
    """Raised when the CI target manifest is missing required structure."""


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


@dataclass(frozen=True)
class OwnershipBoundary:
    """Approved ownership boundary declared inside the CI target manifest."""

    included_target_groups: tuple[str, ...]
    excluded_target_categories: tuple[str, ...]
    current_consumers: tuple[str, ...]


@dataclass(frozen=True)
class CiTargetManifest:
    """Parsed CI target manifest with stable, consumer-friendly accessors."""

    path: Path
    raw: dict[str, object]
    format_type: str
    targets: dict[str, tuple[str, ...]]
    ownership_boundary: OwnershipBoundary

    @classmethod
    def load(cls, path: Path = MANIFEST_PATH) -> "CiTargetManifest":
        """Load and normalize the canonical CI target manifest from disk."""
        raw = json.loads(path.read_text())
        if not isinstance(raw, dict):
            raise ManifestError("CI target manifest root must be an object.")

        format_data = _require_mapping(raw.get("format"), "format")
        targets_data = _require_mapping(raw.get("targets"), "targets")
        boundary_data = _require_mapping(
            raw.get("ownership_boundary"),
            "ownership_boundary",
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

        return cls(
            path=path,
            raw=raw,
            format_type=str(format_data.get("type", "")),
            targets=targets,
            ownership_boundary=boundary,
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
