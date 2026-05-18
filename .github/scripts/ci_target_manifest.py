#!/usr/bin/env python3
"""Shared manifest-loading helpers for CI target scripts.

All CI ownership helpers read the same manifest. This module keeps manifest
parsing and normalized access in one place so workflow readers, validators,
drift checks, path-existence checks, and policy checks share the same model.

`.github/ci_test_targets.json` is the canonical owner of:
- shared target groups
- lane-category definitions
- path-existence inventory and boundary notes
- split-suite registration metadata
- protected workflow/policy alignment metadata

Small one-off workflow test paths can still stay inline when they are truly
local exceptions, such as the tiny integration smoke path.

For the short maintainer-facing map of these ownership rules, see
`docs/ci-maintainer-guide.md`.
"""

from __future__ import annotations

from dataclasses import dataclass
from fnmatch import fnmatch
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


def _require_string_mapping(raw: object, field_name: str) -> dict[str, str]:
    """Return one manifest object field as a string-to-string dict."""
    mapping = _require_mapping(raw, field_name)
    return {str(key): str(value) for key, value in mapping.items()}


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


def _group_paths(
    targets: dict[str, tuple[str, ...]],
    group_names: tuple[str, ...],
) -> tuple[str, ...]:
    """Return the flattened target paths for one ordered manifest-group tuple."""
    return tuple(
        target_path
        for group_name in group_names
        for target_path in targets[group_name]
    )


def _doc_alignment_requirements(
    protected_workflow_groups: tuple[str, ...],
) -> tuple["DocAlignmentRequirement", ...]:
    """Return the high-signal CI-facing doc requirements for drift checks.

    These docs are intentionally checked for a small set of ownership facts,
    not for a full duplicate of every CI rule.
    """
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
class LaneCategoryDefinition:
    """One canonical CI lane category with explicit include/exclude notes."""

    name: str
    includes: tuple[str, ...]
    excludes: tuple[str, ...]


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
class PathExistenceBoundary:
    """Approved scope boundary for the CI-owned path-existence self-check."""

    included_path_categories: tuple[str, ...]
    excluded_path_categories: tuple[str, ...]


@dataclass(frozen=True)
class GuardedSplitSuiteArea:
    """One guarded area where new split test files require CI registration."""

    name: str
    patterns: tuple[str, ...]
    registration_surfaces: tuple[str, ...]
    rationale: str


@dataclass(frozen=True)
class SplitSuiteRegistrationContract:
    """Shared rules for when a new guarded split suite counts as registered."""

    manifest_owned_rule: str
    policy_owned_rule: str
    docs_rule: str
    excluded_cases: tuple[str, ...]


@dataclass(frozen=True)
class SplitSuiteDetectionStrategy:
    """Shared changed-files strategy for the live split-suite registration guard."""

    mode: str
    source: str
    rationale: str
    rejected_alternatives: tuple[str, ...]


@dataclass(frozen=True)
class SplitSuiteDocsEnforcement:
    """High-signal rules for when split-suite registration should require docs."""

    required_when: tuple[str, ...]
    excluded_cases: tuple[str, ...]
    rationale: str


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
    path_existence_boundary: PathExistenceBoundary
    guarded_split_suite_areas: dict[str, GuardedSplitSuiteArea]
    split_suite_registration_contract: SplitSuiteRegistrationContract
    split_suite_detection_strategy: SplitSuiteDetectionStrategy
    split_suite_docs_enforcement: SplitSuiteDocsEnforcement
    lane_categories: dict[str, LaneCategoryDefinition]
    group_lane_categories: dict[str, str]

    @classmethod
    def load(cls, path: Path = MANIFEST_PATH) -> "CiTargetManifest":
        """Load and normalize the canonical CI target manifest from disk."""
        raw = _load_json_object(path)
        format_data = _require_mapping(raw.get("format"), "format")

        return cls(
            path=path,
            raw=raw,
            format_type=str(format_data.get("type", "")),
            targets=_parse_targets(raw),
            ownership_boundary=_parse_ownership_boundary(raw),
            alignment_boundary=_parse_alignment_boundary(raw),
            path_existence_inventory=_parse_path_existence_inventory(raw),
            path_existence_boundary=_parse_path_existence_boundary(raw),
            guarded_split_suite_areas=_parse_guarded_split_suite_areas(raw),
            split_suite_registration_contract=_parse_split_suite_registration_contract(raw),
            split_suite_detection_strategy=_parse_split_suite_detection_strategy(raw),
            split_suite_docs_enforcement=_parse_split_suite_docs_enforcement(raw),
            lane_categories=_parse_lane_categories(raw),
            group_lane_categories=_parse_group_lane_categories(raw),
        )

    def group_names(self) -> tuple[str, ...]:
        """Return the stable top-level manifest group names."""
        return tuple(self.targets.keys())

    def lane_category_names(self) -> tuple[str, ...]:
        """Return the canonical lane-category names in manifest order."""
        return tuple(self.lane_categories.keys())

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
        workflow_group_paths = _group_paths(
            self.targets,
            inventory.workflow_manifest_groups,
        )
        policy_group_paths = _group_paths(
            self.targets,
            inventory.policy_manifest_groups,
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

    def guarded_split_suite_area(
        self,
        area_name: str,
    ) -> GuardedSplitSuiteArea:
        """Return one guarded split-suite area by stable name."""
        try:
            return self.guarded_split_suite_areas[area_name]
        except KeyError as exc:
            raise ManifestError(
                f"Unknown guarded split-suite area: {area_name}"
            ) from exc

    def guarded_split_suite_area_names(self) -> tuple[str, ...]:
        """Return the guarded split-suite area names in manifest order."""
        return tuple(self.guarded_split_suite_areas.keys())

    def matching_guarded_split_suite_areas(
        self,
        relative_path: str,
    ) -> tuple[GuardedSplitSuiteArea, ...]:
        """Return the guarded split-suite areas matched by one repo-relative path.

        This is the main matching seam used by the live split-suite
        registration guard.
        """
        return tuple(
            area
            for area in self.guarded_split_suite_areas.values()
            if any(fnmatch(relative_path, pattern) for pattern in area.patterns)
        )

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

    def lane_category(self, category_name: str) -> LaneCategoryDefinition:
        """Return one canonical CI lane category by stable name."""
        try:
            return self.lane_categories[category_name]
        except KeyError as exc:
            raise ManifestError(
                f"Unknown CI lane category: {category_name}"
            ) from exc

    def group_lane_category_name(self, group_name: str) -> str:
        """Return the canonical lane category name for one manifest group."""
        if group_name not in self.targets:
            raise ManifestError(f"Unknown CI target manifest group: {group_name}")
        try:
            return self.group_lane_categories[group_name]
        except KeyError as exc:
            raise ManifestError(
                f"Manifest group '{group_name}' is missing a lane-category assignment."
            ) from exc

    def group_lane_category(self, group_name: str) -> LaneCategoryDefinition:
        """Return the canonical lane category assigned to one manifest group."""
        return self.lane_category(self.group_lane_category_name(group_name))

    def lane_groups(self, category_name: str) -> tuple[str, ...]:
        """Return the manifest groups assigned to one canonical lane category."""
        self.lane_category(category_name)
        return tuple(
            group_name
            for group_name in self.group_names()
            if self.group_lane_category_name(group_name) == category_name
        )

    def lane_group_map(self) -> dict[str, tuple[str, ...]]:
        """Return the manifest-group ownership split keyed by lane category."""
        return {
            category_name: self.lane_groups(category_name)
            for category_name in self.lane_category_names()
        }


def _parse_targets(raw: dict[str, object]) -> dict[str, tuple[str, ...]]:
    """Return the normalized stable target groups from the manifest."""
    targets_data = _require_mapping(raw.get("targets"), "targets")
    return {
        group_name: _require_string_list(group_value, f"targets.{group_name}")
        for group_name, group_value in targets_data.items()
    }


def _parse_ownership_boundary(raw: dict[str, object]) -> OwnershipBoundary:
    """Return the approved CI ownership boundary from the manifest."""
    boundary_data = _require_mapping(raw.get("ownership_boundary"), "ownership_boundary")
    return OwnershipBoundary(
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


def _parse_alignment_boundary(raw: dict[str, object]) -> AlignmentBoundary:
    """Return the approved protected-lane alignment boundary from the manifest."""
    boundary_data = _require_mapping(raw.get("alignment_boundary"), "alignment_boundary")
    return AlignmentBoundary(
        protected_workflow_groups=_require_string_list(
            boundary_data.get("protected_workflow_groups"),
            "alignment_boundary.protected_workflow_groups",
        ),
        excluded_alignment_categories=_require_string_list(
            boundary_data.get("excluded_alignment_categories"),
            "alignment_boundary.excluded_alignment_categories",
        ),
    )


def _parse_path_existence_inventory(
    raw: dict[str, object],
) -> PathExistenceInventory:
    """Return the current CI-owned test-path inventory from the manifest."""
    inventory_data = _require_mapping(
        raw.get("path_existence_inventory"),
        "path_existence_inventory",
    )
    return PathExistenceInventory(
        workflow_manifest_groups=_require_string_list(
            inventory_data.get("workflow_manifest_groups"),
            "path_existence_inventory.workflow_manifest_groups",
        ),
        workflow_inline_test_paths=_require_string_list(
            inventory_data.get("workflow_inline_test_paths"),
            "path_existence_inventory.workflow_inline_test_paths",
        ),
        policy_manifest_groups=_require_string_list(
            inventory_data.get("policy_manifest_groups"),
            "path_existence_inventory.policy_manifest_groups",
        ),
        policy_only_test_paths=_require_string_list(
            inventory_data.get("policy_only_test_paths"),
            "path_existence_inventory.policy_only_test_paths",
        ),
    )


def _parse_path_existence_boundary(
    raw: dict[str, object],
) -> PathExistenceBoundary:
    """Return the approved scope boundary for the existence self-check."""
    boundary_data = _require_mapping(
        raw.get("path_existence_boundary"),
        "path_existence_boundary",
    )
    return PathExistenceBoundary(
        included_path_categories=_require_string_list(
            boundary_data.get("included_path_categories"),
            "path_existence_boundary.included_path_categories",
        ),
        excluded_path_categories=_require_string_list(
            boundary_data.get("excluded_path_categories"),
            "path_existence_boundary.excluded_path_categories",
        ),
    )


def _parse_guarded_split_suite_areas(
    raw: dict[str, object],
) -> dict[str, GuardedSplitSuiteArea]:
    """Return the guarded split-suite registration areas from the manifest."""
    areas_data = _require_mapping(
        raw.get("guarded_split_suite_areas"),
        "guarded_split_suite_areas",
    )
    guarded_areas: dict[str, GuardedSplitSuiteArea] = {}

    for area_name, area_value in areas_data.items():
        if not isinstance(area_value, dict):
            raise ManifestError(
                "CI target manifest field "
                f"'guarded_split_suite_areas.{area_name}' must be an object."
            )
        guarded_areas[area_name] = GuardedSplitSuiteArea(
            name=area_name,
            patterns=_require_string_list(
                area_value.get("patterns"),
                f"guarded_split_suite_areas.{area_name}.patterns",
            ),
            registration_surfaces=_require_string_list(
                area_value.get("registration_surfaces"),
                f"guarded_split_suite_areas.{area_name}.registration_surfaces",
            ),
            rationale=str(area_value.get("rationale", "")).strip(),
        )

    return guarded_areas


def _parse_split_suite_registration_contract(
    raw: dict[str, object],
) -> SplitSuiteRegistrationContract:
    """Return the shared registration contract for new guarded split suites."""
    contract_data = _require_mapping(
        raw.get("split_suite_registration_contract"),
        "split_suite_registration_contract",
    )
    return SplitSuiteRegistrationContract(
        manifest_owned_rule=str(contract_data.get("manifest_owned_rule", "")).strip(),
        policy_owned_rule=str(contract_data.get("policy_owned_rule", "")).strip(),
        docs_rule=str(contract_data.get("docs_rule", "")).strip(),
        excluded_cases=_require_string_list(
            contract_data.get("excluded_cases"),
            "split_suite_registration_contract.excluded_cases",
        ),
    )


def _parse_split_suite_detection_strategy(
    raw: dict[str, object],
) -> SplitSuiteDetectionStrategy:
    """Return the shared detection strategy for guarded split-suite checks."""
    strategy_data = _require_mapping(
        raw.get("split_suite_detection_strategy"),
        "split_suite_detection_strategy",
    )
    return SplitSuiteDetectionStrategy(
        mode=str(strategy_data.get("mode", "")).strip(),
        source=str(strategy_data.get("source", "")).strip(),
        rationale=str(strategy_data.get("rationale", "")).strip(),
        rejected_alternatives=_require_string_list(
            strategy_data.get("rejected_alternatives"),
            "split_suite_detection_strategy.rejected_alternatives",
        ),
    )


def _parse_split_suite_docs_enforcement(
    raw: dict[str, object],
) -> SplitSuiteDocsEnforcement:
    """Return the shared docs-enforcement boundary for split-suite registration."""
    docs_data = _require_mapping(
        raw.get("split_suite_docs_enforcement"),
        "split_suite_docs_enforcement",
    )
    return SplitSuiteDocsEnforcement(
        required_when=_require_string_list(
            docs_data.get("required_when"),
            "split_suite_docs_enforcement.required_when",
        ),
        excluded_cases=_require_string_list(
            docs_data.get("excluded_cases"),
            "split_suite_docs_enforcement.excluded_cases",
        ),
        rationale=str(docs_data.get("rationale", "")).strip(),
    )


def _parse_lane_categories(
    raw: dict[str, object],
) -> dict[str, LaneCategoryDefinition]:
    """Return the canonical lane-category definitions from the manifest."""
    lane_categories_data = _require_mapping(raw.get("lane_categories"), "lane_categories")
    lane_categories: dict[str, LaneCategoryDefinition] = {}

    for category_name, category_value in lane_categories_data.items():
        if not isinstance(category_value, dict):
            raise ManifestError(
                f"CI target manifest field 'lane_categories.{category_name}' must be an object."
            )
        lane_categories[category_name] = LaneCategoryDefinition(
            name=category_name,
            includes=_require_string_list(
                category_value.get("includes"),
                f"lane_categories.{category_name}.includes",
            ),
            excludes=_require_string_list(
                category_value.get("excludes"),
                f"lane_categories.{category_name}.excludes",
            ),
        )

    return lane_categories


def _parse_group_lane_categories(raw: dict[str, object]) -> dict[str, str]:
    """Return the shared manifest-group to lane-category mapping."""
    return _require_string_mapping(
        raw.get("group_lane_categories"),
        "group_lane_categories",
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


def shared_manifest_test_paths() -> tuple[str, ...]:
    """Return every shared manifest-backed test path."""
    return load_ci_target_manifest().all_target_paths()


def workflow_inline_ci_test_paths() -> tuple[str, ...]:
    """Return the explicit inline workflow test-path exceptions."""
    return load_ci_target_manifest().workflow_inline_test_paths()


def guarded_split_suite_areas() -> tuple[GuardedSplitSuiteArea, ...]:
    """Return the guarded split-suite registration areas in manifest order."""
    manifest = load_ci_target_manifest()
    return tuple(
        manifest.guarded_split_suite_area(area_name)
        for area_name in manifest.guarded_split_suite_area_names()
    )


def matching_guarded_split_suite_areas(
    relative_path: str,
) -> tuple[GuardedSplitSuiteArea, ...]:
    """Return the guarded split-suite areas matched by one repo-relative path."""
    return load_ci_target_manifest().matching_guarded_split_suite_areas(relative_path)


def alignment_contract() -> AlignmentContract:
    """Return the shared workflow/policy/docs alignment contract."""
    return load_ci_target_manifest().alignment_contract()


def ci_lane_category(category_name: str) -> LaneCategoryDefinition:
    """Return one canonical CI lane category from the manifest owner seam."""
    return load_ci_target_manifest().lane_category(category_name)


def manifest_group_lane_category_name(group_name: str) -> str:
    """Return the lane-category name assigned to one manifest group."""
    return load_ci_target_manifest().group_lane_category_name(group_name)


def manifest_lane_groups(category_name: str) -> tuple[str, ...]:
    """Return the manifest groups assigned to one canonical lane category."""
    return load_ci_target_manifest().lane_groups(category_name)


def workflow_reader_groups(path: Path) -> tuple[str, ...]:
    """Return manifest groups consumed through the shared workflow reader.

    The extraction intentionally targets shell invocations of
    `read_ci_test_targets.py` and normalizes multiline workflow commands so
    light formatting changes do not alter the discovered group set. It also
    tolerates `python` vs `python3` call-site variation.
    """
    normalized_text = _normalize_workflow_shell_text(path.read_text())
    return tuple(dict.fromkeys(READ_TARGET_PATTERN.findall(normalized_text)))
