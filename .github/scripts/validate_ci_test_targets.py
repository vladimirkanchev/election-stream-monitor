#!/usr/bin/env python3
"""Validate the CI target manifest structure, boundary, and target hygiene.

This validator protects the current ownership split in `ci.yml`: broad shared
contract consumers belong in manifest-backed target groups, while very small
one-off smoke paths are allowed to stay inline outside the manifest.

It also protects the explicit inventory and scope boundary for the
path-existence self-check, so that guard stays limited to CI-owned test paths
instead of growing into a generic repo linter.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import sys

from ci_target_manifest import (
    CiTargetManifest,
    ManifestError,
    REPO_ROOT,
    load_ci_target_manifest,
)

REQUIRED_INCLUDED_GROUPS = (
    "backend_contract",
    "mcp_fastapi_parity",
    "frontend_contract",
    "weekly_slow_media",
    "weekly_api_stream_deep",
    "weekly_lifecycle",
)

REQUIRED_EXCLUDED_CATEGORIES = (
    "full fast-lane backend selectors such as pytest -m filters",
    "simple one-off smoke jobs",
    "lint, typecheck, packaging, and audit jobs",
    "job trigger path filters",
)

REQUIRED_CONSUMERS = (
    ".github/workflows/ci.yml",
    ".github/workflows/weekly-validation.yml",
    ".github/scripts/check_main_pr_consistency.py",
    "docs/testing-and-validation.md",
)

REQUIRED_FORMAT_TYPE = "json"
REQUIRED_PATH_EXISTENCE_INCLUDED_CATEGORIES = (
    "manifest target entries",
    "inline workflow test paths",
    "policy-only test paths",
)
REQUIRED_PATH_EXISTENCE_EXCLUDED_CATEGORIES = (
    "non-test source paths",
    "docs expectations",
    "glob-like selectors if they appear later",
)
REQUIRED_ALIGNMENT_PROTECTED_WORKFLOW_GROUPS = (
    "backend_contract",
    "mcp_fastapi_parity",
    "frontend_contract",
)
REQUIRED_ALIGNMENT_EXCLUDED_CATEGORIES = (
    "weekly-only manifest groups",
    "tiny inline smoke paths",
    "non-manifest workflow behavior",
)
REQUIRED_LANE_CATEGORIES = (
    "fast_synthetic",
    "contract_boundary",
    "weekly_slow_real_media",
)
EXPECTED_LANE_GROUPS = {
    "fast_synthetic": (),
    "contract_boundary": (
        "backend_contract",
        "mcp_fastapi_parity",
        "frontend_contract",
    ),
    "weekly_slow_real_media": (
        "weekly_slow_media",
        "weekly_api_stream_deep",
        "weekly_lifecycle",
    ),
}
RETIRED_TARGET_PATHS = (
    "tests/test_session_runner_api_stream_basic.py",
    "tests/test_alert_query_service.py",
    "tests/test_alert_timeline_service.py",
    "tests/test_alert_incident_summary_service.py",
    "tests/test_mcp_server_alerts.py",
    "tests/test_mcp_server_incidents.py",
)

@dataclass(frozen=True)
class BoundaryRule:
    """One approved manifest tuple boundary checked by the validator."""

    actual: Callable[[CiTargetManifest], tuple[str, ...]]
    expected: tuple[str, ...]
    failure_message: str


BOUNDARY_RULES = (
    BoundaryRule(
        actual=lambda manifest: (manifest.format_type,),
        expected=(REQUIRED_FORMAT_TYPE,),
        failure_message="Manifest format drifted from the approved JSON format.",
    ),
    BoundaryRule(
        actual=lambda manifest: manifest.ownership_boundary.included_target_groups,
        expected=REQUIRED_INCLUDED_GROUPS,
        failure_message=(
            "Manifest included target groups drifted from the approved CI-critical boundary."
        ),
    ),
    BoundaryRule(
        actual=lambda manifest: manifest.ownership_boundary.excluded_target_categories,
        expected=REQUIRED_EXCLUDED_CATEGORIES,
        failure_message=(
            "Manifest excluded target categories drifted from the approved non-manifest boundary."
        ),
    ),
    BoundaryRule(
        actual=lambda manifest: manifest.ownership_boundary.current_consumers,
        expected=REQUIRED_CONSUMERS,
        failure_message=(
            "Manifest consumer inventory drifted from the approved current CI/docs consumers."
        ),
    ),
    BoundaryRule(
        actual=lambda manifest: manifest.path_existence_boundary.included_path_categories,
        expected=REQUIRED_PATH_EXISTENCE_INCLUDED_CATEGORIES,
        failure_message=(
            "Manifest path-existence included categories drifted from the approved self-check scope."
        ),
    ),
    BoundaryRule(
        actual=lambda manifest: manifest.path_existence_boundary.excluded_path_categories,
        expected=REQUIRED_PATH_EXISTENCE_EXCLUDED_CATEGORIES,
        failure_message=(
            "Manifest path-existence excluded categories drifted from the approved self-check scope."
        ),
    ),
    BoundaryRule(
        actual=lambda manifest: manifest.alignment_boundary.protected_workflow_groups,
        expected=REQUIRED_ALIGNMENT_PROTECTED_WORKFLOW_GROUPS,
        failure_message=(
            "Manifest alignment protected workflow groups drifted from the approved contract-lane boundary."
        ),
    ),
    BoundaryRule(
        actual=lambda manifest: manifest.alignment_boundary.excluded_alignment_categories,
        expected=REQUIRED_ALIGNMENT_EXCLUDED_CATEGORIES,
        failure_message=(
            "Manifest alignment excluded categories drifted from the approved narrow contract."
        ),
    ),
)


def _check_equal(
    actual: tuple[str, ...],
    expected: tuple[str, ...],
    failure_message: str,
) -> list[str]:
    """Return one failure when a manifest tuple drifts from its approved value."""
    if actual == expected:
        return []
    return [failure_message]


def _require_group_naming(manifest: CiTargetManifest) -> list[str]:
    """Return a failure when the manifest loses stable group-naming metadata."""
    if "group_naming" in manifest.raw:
        return []
    return ["Manifest is missing the 'group_naming' object."]


def _validate_targets(manifest: CiTargetManifest) -> list[str]:
    """Return failures for required stable target groups."""
    failures: list[str] = []

    for group_name in REQUIRED_INCLUDED_GROUPS:
        if group_name not in manifest.targets:
            failures.append(f"Manifest targets are missing required group '{group_name}'.")
            continue
        if not manifest.group_targets(group_name):
            failures.append(f"Manifest target group '{group_name}' must not be empty.")

    return failures


def _validate_lane_categories(manifest: CiTargetManifest) -> list[str]:
    """Return failures for required canonical CI lane categories."""
    failures: list[str] = []

    for category_name in REQUIRED_LANE_CATEGORIES:
        try:
            category = manifest.lane_category(category_name)
        except ManifestError:
            failures.append(
                f"Manifest lane categories are missing required category '{category_name}'."
            )
            continue

        if not category.includes:
            failures.append(
                f"Manifest lane category '{category_name}' must define at least one include note."
            )
        if not category.excludes:
            failures.append(
                f"Manifest lane category '{category_name}' must define at least one exclude note."
            )

    return failures


def _validate_group_lane_categories(manifest: CiTargetManifest) -> list[str]:
    """Return failures for required lane ownership on each manifest group."""
    failures: list[str] = []

    for group_name in REQUIRED_INCLUDED_GROUPS:
        if group_name not in manifest.targets:
            continue

        try:
            category_name = manifest.group_lane_category_name(group_name)
        except ManifestError as exc:
            failures.append(str(exc))
            continue

        if category_name not in REQUIRED_LANE_CATEGORIES:
            failures.append(
                f"Manifest group '{group_name}' points to unknown lane category '{category_name}'."
            )

    return failures


def _validate_lane_ownership_rules(manifest: CiTargetManifest) -> list[str]:
    """Return failures for the enforced lane-ownership split."""
    failures: list[str] = []
    lane_failures = {
        "contract_boundary": (
            "Manifest contract_boundary lane groups drifted from the protected PR contract groups."
        ),
        "weekly_slow_real_media": (
            "Manifest weekly_slow_real_media lane groups drifted from the approved weekly-only groups."
        ),
        "fast_synthetic": (
            "Manifest fast_synthetic lane must not own shared manifest groups."
        ),
    }
    actual_lane_groups = manifest.lane_group_map()

    for category_name, expected_groups in EXPECTED_LANE_GROUPS.items():
        if actual_lane_groups.get(category_name) != expected_groups:
            failures.append(lane_failures[category_name])

    return failures


def _validate_boundary_rules(manifest: CiTargetManifest) -> list[str]:
    """Return failures for the approved manifest boundary contract."""
    failures: list[str] = []

    for rule in BOUNDARY_RULES:
        failures.extend(
            _check_equal(
                actual=rule.actual(manifest),
                expected=rule.expected,
                failure_message=rule.failure_message,
            )
        )

    return failures


def _validate_target_paths(manifest: CiTargetManifest) -> list[str]:
    """Return failures for target existence, uniqueness, and retired names."""
    failures: list[str] = []
    seen_paths: set[str] = set()
    duplicate_paths: set[str] = set()
    referenced_paths = manifest.all_target_paths()

    for manifest_path in referenced_paths:
        if manifest_path in seen_paths:
            duplicate_paths.add(manifest_path)
        seen_paths.add(manifest_path)
        resolved_path = REPO_ROOT / manifest_path
        if not resolved_path.exists():
            failures.append(
                f"Manifest target path '{manifest_path}' does not exist in the repo."
            )

    for duplicate_path in sorted(duplicate_paths):
        failures.append(
            f"Manifest target path '{duplicate_path}' is duplicated across groups."
        )

    for retired_path in RETIRED_TARGET_PATHS:
        if retired_path in seen_paths:
            failures.append(
                f"Manifest still references stale retired path '{retired_path}'."
            )

    return failures


def _validate_manifest() -> list[str]:
    """Return human-readable failures for the parsed manifest.

    This keeps the step-3 boundary explicit: the manifest must stay complete
    for broad shared consumers without growing to include tiny local smoke
    paths that intentionally remain inline in `ci.yml`. It also protects the
    narrower scope of the live path-existence self-check, which should stay
    limited to CI-owned test paths listed in the inventory and excluded from
    source/doc ownership rules.
    """
    try:
        manifest = load_ci_target_manifest()
    except ManifestError as exc:
        return [str(exc)]

    failures = []
    failures.extend(_require_group_naming(manifest))
    failures.extend(_validate_boundary_rules(manifest))
    failures.extend(_validate_lane_categories(manifest))
    failures.extend(_validate_group_lane_categories(manifest))
    failures.extend(_validate_lane_ownership_rules(manifest))
    failures.extend(_validate_targets(manifest))
    failures.extend(_validate_target_paths(manifest))
    return failures


def main() -> int:
    """Run the manifest validation command used by CI workflow and docs guards.

    The current workflow expectation is that `test-and-build` resolves shared
    contract targets through the reader, while one small integration smoke
    command remains an explicit local inline invocation. The same command also
    keeps the path-existence inventory and scope boundary stable for the live
    CI-owned test-path existence guard.
    """
    failures = _validate_manifest()
    if failures:
        print("ci_test_targets manifest validation failed:", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1

    print("ci_test_targets manifest validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
