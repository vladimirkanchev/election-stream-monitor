#!/usr/bin/env python3
"""Validate that every CI-owned test path still exists in the repo.

This is a narrow structural guard for the current CI path owners:
- manifest-backed workflow groups
- inline workflow test-path exceptions
- policy-only test paths from the main PR consistency script

It also checks that the manifest's policy-only inventory still matches the
real policy owner in `check_main_pr_consistency.py`, and it reports local-only
gate expectations as their own validated slice.

It intentionally does not validate non-test source paths or docs expectations.

Responsibility split:
- `validate_ci_test_targets.py` protects manifest structure and scope boundary
- this script protects existence of CI-owned test paths inside that boundary
- `check_ci_target_drift.py` protects alignment between manifest, workflows,
  policy, and docs consumers
"""

from __future__ import annotations

from dataclasses import dataclass
import sys

from check_main_pr_consistency import (
    local_only_policy_test_paths,
    policy_only_test_paths,
)
from ci_target_manifest import (
    ManifestError,
    REPO_ROOT,
    ci_owned_test_paths,
    load_ci_target_manifest,
    workflow_inline_ci_test_paths,
)


@dataclass(frozen=True)
class PathCheckSummary:
    """Validation result for one owned CI test-path slice."""

    label: str
    referenced_paths: tuple[str, ...]
    missing_paths: tuple[str, ...]

    @property
    def referenced_count(self) -> int:
        """Return how many paths belong to this CI-owned slice."""
        return len(self.referenced_paths)

    @property
    def missing_count(self) -> int:
        """Return how many paths are currently missing from this slice."""
        return len(self.missing_paths)


def _missing_repo_paths(relative_paths: tuple[str, ...]) -> tuple[str, ...]:
    """Return missing repo-relative paths from one referenced slice."""
    return tuple(
        relative_path
        for relative_path in relative_paths
        if not (REPO_ROOT / relative_path).exists()
    )


def _build_path_summary(label: str, relative_paths: tuple[str, ...]) -> PathCheckSummary:
    """Return one path-check summary for a CI-owned slice."""
    return PathCheckSummary(
        label=label,
        referenced_paths=relative_paths,
        missing_paths=_missing_repo_paths(relative_paths),
    )


def _policy_inventory_drift_failures() -> list[str]:
    """Return failures when policy-only inventory drifted from its owner."""
    try:
        manifest = load_ci_target_manifest()
    except ManifestError as exc:
        return [str(exc)]

    manifest_policy_paths = manifest.path_existence_inventory.policy_only_test_paths
    actual_policy_paths = policy_only_test_paths()
    if manifest_policy_paths == actual_policy_paths:
        return []

    return [
        "Manifest policy-only path inventory drifted from check_main_pr_consistency.py "
        f"(manifest={list(manifest_policy_paths)}, actual={list(actual_policy_paths)})."
    ]


def _path_summaries() -> tuple[PathCheckSummary, ...]:
    """Return path-check summaries for every owned CI slice."""
    try:
        return (
            _build_path_summary("all ci-owned test paths", ci_owned_test_paths()),
            _build_path_summary(
                "inline workflow exceptions",
                workflow_inline_ci_test_paths(),
            ),
            _build_path_summary(
                "policy-only expectations",
                policy_only_test_paths(),
            ),
            _build_path_summary(
                "local-only policy expectations",
                local_only_policy_test_paths(),
            ),
        )
    except ManifestError as exc:
        return (
            PathCheckSummary(
                label="manifest access failure",
                referenced_paths=(),
                missing_paths=(str(exc),),
            ),
        )


def _format_success_summary(summaries: tuple[PathCheckSummary, ...]) -> str:
    """Return the compact success summary for the existence guard."""
    inline_summary, policy_summary, local_only_summary = summaries[1:]
    return (
        "ci-owned test path existence check passed "
        f"(validated {inline_summary.referenced_count} inline workflow exception(s); "
        f"missing inline exceptions={inline_summary.missing_count}; "
        f"validated {policy_summary.referenced_count} policy-only expectation(s); "
        f"missing policy-only expectations={policy_summary.missing_count}; "
        f"validated {local_only_summary.referenced_count} local-only policy expectation(s); "
        f"missing local-only policy expectations={local_only_summary.missing_count})"
    )


def main() -> int:
    """Run the CI-owned test-path existence guard.

    The success summary keeps the current inline exception slice and the
    narrower policy-owned slices visible so stale local exceptions do not hide
    behind broader manifest-backed coverage.

    In protected CI lanes this runs after manifest structure/scope validation
    and before broader drift or policy checks, so missing-path failures surface
    early and read clearly.
    """
    inventory_drift_failures = _policy_inventory_drift_failures()
    summaries = _path_summaries()
    top_level_missing_paths = summaries[0].missing_paths
    if inventory_drift_failures or top_level_missing_paths:
        print("ci-owned test path existence check failed:", file=sys.stderr)
        for failure in inventory_drift_failures:
            print(f"- {failure}", file=sys.stderr)
        for summary in summaries:
            for relative_path in summary.missing_paths:
                if summary.label == "manifest access failure":
                    print(f"- {relative_path}", file=sys.stderr)
                    continue
                print(
                    f"- Missing {summary.label} path: {relative_path}",
                    file=sys.stderr,
                )
        return 1

    print(_format_success_summary(summaries))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
