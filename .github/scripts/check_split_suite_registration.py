#!/usr/bin/env python3
"""Validate registration of added or renamed guarded split test suites.

This guard turns the repo's split-suite discipline into an executable CI rule:
- it looks only at added or renamed files in protected PR CI
- it narrows that set to guarded split-suite areas from the manifest
- it verifies that each guarded file is registered through the expected
  CI ownership surface before broader policy or contract lanes run

Registration surfaces:
- `shared_manifest`
  - the file is present in one shared manifest-backed target group
- `policy_owned`
  - the file is covered by the main-PR policy owner seam
- `local_only_policy`
  - the file is covered by the local-only main-PR policy seam
- `focused_detector_recipe`
  - the file is selected by one of the reviewed focused detector recipes
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import subprocess
import sys

from check_main_pr_consistency import (
    local_only_policy_test_paths,
    policy_owned_test_paths,
)
from ci_target_manifest import (
    GuardedSplitSuiteArea,
    ManifestError,
    REPO_ROOT,
    load_ci_target_manifest,
    shared_manifest_test_paths,
)


SHARED_MANIFEST = "shared_manifest"
POLICY_OWNED = "policy_owned"
LOCAL_ONLY_POLICY = "local_only_policy"
FOCUSED_DETECTOR_RECIPE = "focused_detector_recipe"
JUSTFILE_PATH = REPO_ROOT / "justfile"
FOCUSED_DETECTOR_RECIPES = (
    "test-detectors",
    "test-detector-lab",
    "test-real-media",
)
REGISTRATION_SURFACES = (
    SHARED_MANIFEST,
    POLICY_OWNED,
    LOCAL_ONLY_POLICY,
    FOCUSED_DETECTOR_RECIPE,
)


@dataclass(frozen=True)
class RegistrationInventories:
    """Current ownership inventories consulted by the split-suite registration guard."""

    shared_manifest_paths: frozenset[str]
    policy_owned_paths: frozenset[str]
    local_only_policy_paths: frozenset[str]
    focused_detector_recipe_paths: frozenset[str]

    def registered_surfaces(self, relative_path: str) -> frozenset[str]:
        """Return the ownership surfaces that currently register one file."""
        registered_surfaces: set[str] = set()

        if relative_path in self.shared_manifest_paths:
            registered_surfaces.add(SHARED_MANIFEST)
        if relative_path in self.policy_owned_paths:
            registered_surfaces.add(POLICY_OWNED)
        if relative_path in self.local_only_policy_paths:
            registered_surfaces.add(LOCAL_ONLY_POLICY)
        if relative_path in self.focused_detector_recipe_paths:
            registered_surfaces.add(FOCUSED_DETECTOR_RECIPE)

        return frozenset(registered_surfaces)


@dataclass(frozen=True)
class RegistrationStatus:
    """Registration status for one added or renamed guarded split-suite file.

    A guarded file is valid when at least one accepted registration surface for
    its matched guarded area already owns it.
    """

    relative_path: str
    matched_areas: tuple[GuardedSplitSuiteArea, ...]
    registered_surfaces: frozenset[str]

    def accepted_surfaces(self) -> tuple[str, ...]:
        """Return accepted surfaces in first-seen guarded-area order."""
        ordered_accepted_surfaces: list[str] = []
        seen_surfaces: set[str] = set()

        for area in self.matched_areas:
            for surface in area.registration_surfaces:
                if surface in seen_surfaces:
                    continue
                seen_surfaces.add(surface)
                ordered_accepted_surfaces.append(surface)

        return tuple(ordered_accepted_surfaces)

    def accepted_surface_status(self) -> dict[str, bool]:
        """Return accepted surfaces mapped to their current registration status."""
        return {
            surface: self.is_registered(surface)
            for surface in self.accepted_surfaces()
        }

    @property
    def ok(self) -> bool:
        """Return whether the guarded file satisfies one accepted surface."""
        return bool(self.registered_surfaces.intersection(self.accepted_surfaces()))

    def is_registered(self, surface: str) -> bool:
        """Return whether one ownership surface currently registers this file."""
        return surface in self.registered_surfaces


def _parse_args() -> argparse.Namespace:
    """Return CLI arguments for the split-suite registration guard."""
    parser = argparse.ArgumentParser(
        description="Validate CI registration for added or renamed guarded split suites."
    )
    parser.add_argument(
        "diff_range",
        nargs="?",
        help="Git diff range used to detect added or renamed files.",
    )
    parser.add_argument(
        "--changed-file",
        action="append",
        default=[],
        dest="changed_files",
        help="Explicit changed file for focused local validation or tests.",
    )
    return parser.parse_args()


def _added_or_renamed_files(diff_range: str) -> tuple[str, ...]:
    """Return added paths and renamed destinations from one git diff range."""
    result = subprocess.run(
        [
            "git",
            "diff",
            "--name-status",
            "--find-renames=50%",
            "--diff-filter=AR",
            diff_range,
        ],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    changed_paths: list[str] = []

    for line in result.stdout.splitlines():
        status, *paths = line.split("\t")
        if status == "A" and len(paths) == 1:
            changed_paths.append(paths[0])
        elif status.startswith("R") and len(paths) == 2:
            changed_paths.append(paths[1])

    return tuple(changed_paths)


def _changed_files_from_args(args: argparse.Namespace) -> tuple[str, ...]:
    """Return explicit paths or Git-discovered additions and rename targets."""
    explicit_changed_files = tuple(args.changed_files)
    if explicit_changed_files:
        return explicit_changed_files
    if args.diff_range:
        return _added_or_renamed_files(args.diff_range)
    raise ValueError(
        "Provide either <diff-range> or at least one --changed-file value."
    )


def recipe_test_paths(recipe_name: str) -> frozenset[str]:
    """Return direct test-file targets from one checked-in `just` recipe."""
    lines = JUSTFILE_PATH.read_text(encoding="utf-8").splitlines()
    recipe_header = f"{recipe_name}:"

    try:
        recipe_start = lines.index(recipe_header) + 1
    except ValueError as exc:
        raise ManifestError(
            f"Focused recipe '{recipe_name}' is missing from justfile."
        ) from exc

    recipe_body: list[str] = []
    for line in lines[recipe_start:]:
        if line and not line[0].isspace():
            break
        recipe_body.append(line)

    return frozenset(
        target
        for line in recipe_body
        for target in line.partition("#")[0].split()
        if target.startswith("tests/")
    )


def focused_detector_recipe_test_paths() -> frozenset[str]:
    """Return all direct test targets owned by focused detector recipes."""
    return frozenset().union(
        *(recipe_test_paths(recipe_name) for recipe_name in FOCUSED_DETECTOR_RECIPES)
    )


def _registration_inventories() -> RegistrationInventories:
    """Return the current ownership inventories used by the registration guard."""
    return RegistrationInventories(
        shared_manifest_paths=frozenset(shared_manifest_test_paths()),
        policy_owned_paths=frozenset(policy_owned_test_paths()),
        local_only_policy_paths=frozenset(local_only_policy_test_paths()),
        focused_detector_recipe_paths=focused_detector_recipe_test_paths(),
    )


def _registration_statuses(
    changed_files: tuple[str, ...],
) -> tuple[RegistrationStatus, ...]:
    """Return registration statuses for added or renamed guarded split suites.

    Unguarded changed files are ignored on purpose so the guard stays narrow.
    """
    manifest = load_ci_target_manifest()
    inventories = _registration_inventories()

    statuses: list[RegistrationStatus] = []

    for relative_path in changed_files:
        matched_areas = manifest.matching_guarded_split_suite_areas(relative_path)
        if not matched_areas:
            continue

        statuses.append(
            RegistrationStatus(
                relative_path=relative_path,
                matched_areas=matched_areas,
                registered_surfaces=inventories.registered_surfaces(relative_path),
            )
        )

    return tuple(statuses)


def _format_area_names(matched_areas: tuple[GuardedSplitSuiteArea, ...]) -> str:
    """Return a stable readable rendering of matched guarded-area names."""
    return ", ".join(area.name for area in matched_areas)


def _surface_status_suffix(status: RegistrationStatus) -> str:
    """Return a compact surface-status suffix for one registration failure."""
    return ", ".join(
        f"{surface}={status.is_registered(surface)}"
        for surface in REGISTRATION_SURFACES
    )


def _registration_failures(
    statuses: tuple[RegistrationStatus, ...],
) -> list[str]:
    """Return targeted failures for guarded files with no accepted registration."""
    failures: list[str] = []

    for status in statuses:
        if status.ok:
            continue
        accepted_surfaces = ", ".join(status.accepted_surfaces())
        failures.append(
            "Guarded split suite "
            f"'{status.relative_path}' matched area(s) "
            f"{_format_area_names(status.matched_areas)} but is missing accepted "
            f"registration (expected one of: {accepted_surfaces}; "
            f"{_surface_status_suffix(status)})."
        )

    return failures


def collect_registration_statuses(
    changed_files: tuple[str, ...],
) -> tuple[RegistrationStatus, ...]:
    """Return guarded-file registration statuses for one changed-file batch."""
    return _registration_statuses(changed_files)


def registration_failures(
    changed_files: tuple[str, ...],
) -> list[str]:
    """Return targeted failures for one changed-file batch.

    Unguarded files are ignored because the split-suite guard is intentionally
    scoped only to the guarded registration surface.
    """
    return _registration_failures(collect_registration_statuses(changed_files))


def main() -> int:
    """Run the shared split-suite registration guard."""
    try:
        changed_files = _changed_files_from_args(_parse_args())
        statuses = collect_registration_statuses(changed_files)
    except (ManifestError, ValueError, subprocess.CalledProcessError) as exc:
        print(str(exc), file=sys.stderr)
        return 1

    failures = _registration_failures(statuses)
    if failures:
        print("split-suite registration check failed:", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1

    print(
        "split-suite registration check passed "
        f"(guarded files={len(statuses)})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
