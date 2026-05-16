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

The manifest also records:
- the current path-owning CI surface for the path-existence guard
- the narrow workflow/policy alignment boundary for the protected contract lane
- the high-signal CI-facing doc requirements used by the drift checker

That keeps path-existence and alignment checks small, explicit, and shared.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import cache
import json
from pathlib import Path
import re


REPO_ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = REPO_ROOT / ".github" / "ci_test_targets.json"
READ_TARGET_PATTERN = re.compile(
    r"(?:^|[\s(])python(?:3)?\s+\S*read_ci_test_targets\.py\s+([a-z_]+)"
)


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


def _doc_alignment_requirements(
    protected_workflow_groups: tuple[str, ...],
) -> tuple["DocAlignmentRequirement", ...]:
    """Return the high-signal CI-facing doc requirements for drift checks."""
    return (
        DocAlignmentRequirement(
            path=REPO_ROOT / "docs" / "testing-and-validation.md",
            required_tokens=(
                ".github/ci_test_targets.json",
                ".github/scripts/read_ci_test_targets.py",
                ".github/scripts/check_ci_target_drift.py",
                ".github/scripts/check_main_pr_consistency.py",
            ),
            required_groups=protected_workflow_groups,
        ),
        DocAlignmentRequirement(
            path=REPO_ROOT / "docs" / "README.md",
            required_tokens=(
                ".github/ci_test_targets.json",
                ".github/scripts/ci_target_manifest.py",
                ".github/scripts/check_ci_target_drift.py",
                ".github/scripts/check_main_pr_consistency.py",
            ),
        ),
        DocAlignmentRequirement(
            path=REPO_ROOT / "docs" / "contracts.md",
            required_tokens=(
                ".github/ci_test_targets.json",
                ".github/scripts/check_ci_target_drift.py",
                ".github/scripts/check_main_pr_consistency.py",
            ),
        ),
    )


def _normalize_workflow_shell_text(raw_text: str) -> str:
    """Return workflow shell text normalized for reader-command extraction."""
    return raw_text.replace("\\\n", " ").replace("\n", " ")


@dataclass(frozen=True)
class OwnershipBoundary:
    """Approved ownership boundary declared inside the CI target manifest."""

    included_target_groups: tuple[str, ...]
    excluded_target_categories: tuple[str, ...]
    current_consumers: tuple[str, ...]


@dataclass(frozen=True)
class AlignmentBoundary:
    """Approved narrow workflow/policy alignment boundary in the CI target manifest."""

    protected_workflow_groups: tuple[str, ...]
    excluded_alignment_categories: tuple[str, ...]


@dataclass(frozen=True)
class DocAlignmentRequirement:
    """High-signal ownership references required in one CI-facing doc."""

    path: Path
    required_tokens: tuple[str, ...]
    required_groups: tuple[str, ...] = ()


@dataclass(frozen=True)
class AlignmentContract:
    """Shared alignment model consumed by the drift checker.

    This keeps the protected workflow groups and the high-signal CI-facing
    doc ownership checks in one shared place so the drift checker can gather
    inputs, compare them, and report failures without carrying those
    assumptions inline.
    """

    protected_workflow_groups: tuple[str, ...]
    doc_requirements: tuple[DocAlignmentRequirement, ...]


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
    alignment_boundary: AlignmentBoundary
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
        alignment_data = _require_mapping(
            raw.get("alignment_boundary"),
            "alignment_boundary",
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

        alignment_boundary = AlignmentBoundary(
            protected_workflow_groups=_require_string_list(
                alignment_data.get("protected_workflow_groups"),
                "alignment_boundary.protected_workflow_groups",
            ),
            excluded_alignment_categories=_require_string_list(
                alignment_data.get("excluded_alignment_categories"),
                "alignment_boundary.excluded_alignment_categories",
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
            alignment_boundary=alignment_boundary,
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

    def alignment_contract(self) -> AlignmentContract:
        """Return the shared workflow/policy/docs alignment contract.

        The protected-lane equality stays intentionally narrow:
        `backend_contract`, `mcp_fastapi_parity`, and `frontend_contract`.
        Weekly-only groups and the inline smoke path remain outside that rule.
        """
        return AlignmentContract(
            protected_workflow_groups=self.alignment_boundary.protected_workflow_groups,
            doc_requirements=_doc_alignment_requirements(
                self.alignment_boundary.protected_workflow_groups
            ),
        )


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


def protected_alignment_groups() -> tuple[str, ...]:
    """Return the protected contract-lane groups used by workflow/policy alignment."""
    return load_ci_target_manifest().alignment_boundary.protected_workflow_groups


def alignment_contract() -> AlignmentContract:
    """Return the shared workflow/policy/docs alignment contract."""
    return load_ci_target_manifest().alignment_contract()


def workflow_reader_groups(path: Path) -> tuple[str, ...]:
    """Return manifest groups consumed through the shared workflow reader.

    The extraction intentionally targets shell invocations of
    `read_ci_test_targets.py` and normalizes multiline workflow commands so
    light formatting changes do not alter the discovered group set. It also
    tolerates `python` vs `python3` call-site variation.
    """
    normalized_text = _normalize_workflow_shell_text(path.read_text())
    return tuple(dict.fromkeys(READ_TARGET_PATTERN.findall(normalized_text)))
