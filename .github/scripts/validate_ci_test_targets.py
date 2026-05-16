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
RETIRED_TARGET_PATHS = (
    "tests/test_session_runner_api_stream_basic.py",
    "tests/test_alert_query_service.py",
    "tests/test_alert_timeline_service.py",
    "tests/test_alert_incident_summary_service.py",
    "tests/test_mcp_server_alerts.py",
    "tests/test_mcp_server_incidents.py",
)

BOUNDARY_RULES = (
    (
        "format_type",
        (REQUIRED_FORMAT_TYPE,),
        "Manifest format drifted from the approved JSON format.",
    ),
    (
        "ownership_boundary.included_target_groups",
        REQUIRED_INCLUDED_GROUPS,
        "Manifest included target groups drifted from the approved CI-critical boundary.",
    ),
    (
        "ownership_boundary.excluded_target_categories",
        REQUIRED_EXCLUDED_CATEGORIES,
        "Manifest excluded target categories drifted from the approved non-manifest boundary.",
    ),
    (
        "ownership_boundary.current_consumers",
        REQUIRED_CONSUMERS,
        "Manifest consumer inventory drifted from the approved current CI/docs consumers.",
    ),
    (
        "path_existence_boundary.included_path_categories",
        REQUIRED_PATH_EXISTENCE_INCLUDED_CATEGORIES,
        "Manifest path-existence included categories drifted from the approved self-check scope.",
    ),
    (
        "path_existence_boundary.excluded_path_categories",
        REQUIRED_PATH_EXISTENCE_EXCLUDED_CATEGORIES,
        "Manifest path-existence excluded categories drifted from the approved self-check scope.",
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


def _manifest_tuple(manifest: CiTargetManifest, field_name: str) -> tuple[str, ...]:
    """Return one manifest tuple field used by boundary validation."""
    if field_name == "format_type":
        return (manifest.format_type,)

    if field_name.startswith("path_existence_boundary."):
        boundary = manifest.raw["path_existence_boundary"]
        boundary_field = field_name.removeprefix("path_existence_boundary.")
        return tuple(boundary[boundary_field])

    boundary_field = field_name.removeprefix("ownership_boundary.")
    return getattr(manifest.ownership_boundary, boundary_field)


def _validate_boundary_rules(manifest: CiTargetManifest) -> list[str]:
    """Return failures for the approved manifest boundary contract."""
    failures: list[str] = []

    for field_name, expected, failure_message in BOUNDARY_RULES:
        failures.extend(
            _check_equal(
                actual=_manifest_tuple(manifest, field_name),
                expected=expected,
                failure_message=failure_message,
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
    paths that intentionally remain inline in `ci.yml`. The same validator now
    also protects the narrower scope of the upcoming path-existence self-check,
    which should stay limited to CI-owned test paths listed in the inventory
    and excluded from source/doc ownership rules.
    """
    try:
        manifest = load_ci_target_manifest()
    except ManifestError as exc:
        return [str(exc)]

    failures = []
    failures.extend(_require_group_naming(manifest))
    failures.extend(_validate_boundary_rules(manifest))
    failures.extend(_validate_targets(manifest))
    failures.extend(_validate_target_paths(manifest))
    return failures


def main() -> int:
    """Run the manifest validation command used by CI workflow and docs guards.

    The current workflow expectation is that `test-and-build` resolves shared
    contract targets through the reader, while one small integration smoke
    command remains an explicit local inline invocation. The same command also
    keeps the path-existence inventory and scope boundary stable for the next
    CI hardening step.
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
