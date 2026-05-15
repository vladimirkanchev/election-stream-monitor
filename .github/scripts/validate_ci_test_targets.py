#!/usr/bin/env python3
"""Validate the CI target manifest structure, boundary, and target hygiene."""

from __future__ import annotations

import sys

from ci_target_manifest import CiTargetManifest, ManifestError, REPO_ROOT

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
RETIRED_TARGET_PATHS = (
    "tests/test_session_runner_api_stream_basic.py",
    "tests/test_alert_query_service.py",
    "tests/test_alert_timeline_service.py",
    "tests/test_alert_incident_summary_service.py",
    "tests/test_mcp_server_alerts.py",
    "tests/test_mcp_server_incidents.py",
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
    """Return human-readable failures for the parsed manifest."""
    try:
        manifest = CiTargetManifest.load()
    except ManifestError as exc:
        return [str(exc)]

    if "group_naming" not in manifest.raw:
        return ["Manifest is missing the 'group_naming' object."]

    failures = []
    failures.extend(
        _check_equal(
            actual=(manifest.format_type,),
            expected=(REQUIRED_FORMAT_TYPE,),
            failure_message="Manifest format drifted from the approved JSON format.",
        )
    )
    failures.extend(
        _check_equal(
            actual=manifest.ownership_boundary.included_target_groups,
            expected=REQUIRED_INCLUDED_GROUPS,
            failure_message=(
                "Manifest included target groups drifted from the approved CI-critical boundary."
            ),
        )
    )
    failures.extend(
        _check_equal(
            actual=manifest.ownership_boundary.excluded_target_categories,
            expected=REQUIRED_EXCLUDED_CATEGORIES,
            failure_message=(
                "Manifest excluded target categories drifted from the approved non-manifest boundary."
            ),
        )
    )
    failures.extend(
        _check_equal(
            actual=manifest.ownership_boundary.current_consumers,
            expected=REQUIRED_CONSUMERS,
            failure_message=(
                "Manifest consumer inventory drifted from the approved current CI/docs consumers."
            ),
        )
    )
    failures.extend(_validate_targets(manifest))
    failures.extend(_validate_target_paths(manifest))
    return failures


def main() -> int:
    """Run the manifest validation command used by CI workflow and docs guards."""
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
