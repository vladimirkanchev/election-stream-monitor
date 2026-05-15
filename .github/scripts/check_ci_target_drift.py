#!/usr/bin/env python3
"""Check drift between the CI target manifest and its workflow, policy, and doc consumers."""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

from ci_target_manifest import CiTargetManifest, ManifestError, REPO_ROOT


CI_WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "ci.yml"
WEEKLY_WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "weekly-validation.yml"
CONSISTENCY_SCRIPT_PATH = REPO_ROOT / ".github" / "scripts" / "check_main_pr_consistency.py"
DOC_PATHS = (
    REPO_ROOT / "docs" / "testing-and-validation.md",
    REPO_ROOT / "docs" / "README.md",
    REPO_ROOT / "docs" / "contracts.md",
)
WORKFLOW_PATHS = (
    CI_WORKFLOW_PATH,
    WEEKLY_WORKFLOW_PATH,
)

READ_TARGET_PATTERN = re.compile(r"read_ci_test_targets\.py\s+([a-z_]+)")

EXPECTED_CONSISTENCY_GROUPS = {
    "backend_contract",
    "mcp_fastapi_parity",
    "frontend_contract",
}

DOC_REQUIRED_TOKENS = (
    ".github/ci_test_targets.json",
    ".github/scripts/read_ci_test_targets.py",
    ".github/scripts/validate_ci_test_targets.py",
)


def _workflow_groups(path: Path) -> set[str]:
    """Return the manifest groups consumed by one workflow file."""
    return set(READ_TARGET_PATTERN.findall(path.read_text()))


def _consistency_groups() -> set[str]:
    """Return the manifest groups consumed by the main consistency script."""
    text = CONSISTENCY_SCRIPT_PATH.read_text()
    module = ast.parse(text)
    groups: set[str] = set()

    for node in ast.walk(module):
        if not isinstance(node, ast.Call):
            continue
        if not isinstance(node.func, ast.Name) or node.func.id != "ContractGate":
            continue

        for keyword in node.keywords:
            if keyword.arg != "manifest_test_groups":
                continue
            if not isinstance(keyword.value, ast.Tuple):
                continue
            for item in keyword.value.elts:
                if isinstance(item, ast.Constant) and isinstance(item.value, str):
                    groups.add(item.value)

    return groups


def _doc_mentions(path: Path, values: set[str]) -> set[str]:
    """Return which stable manifest groups are named in one CI-facing doc."""
    text = path.read_text()
    return {value for value in values if value in text}


def _missing_doc_tokens(path: Path) -> list[str]:
    """Return missing manifest-reference tokens for one CI-facing doc."""
    text = path.read_text()
    return [token for token in DOC_REQUIRED_TOKENS if token not in text]


def _validate_doc_alignment(doc_path: Path, manifest_groups: set[str]) -> list[str]:
    """Return documentation drift failures for one CI-facing doc."""
    failures: list[str] = []
    mentioned = _doc_mentions(doc_path, manifest_groups)
    missing_groups = sorted(manifest_groups - mentioned)
    if missing_groups:
        failures.append(
            f"{doc_path.relative_to(REPO_ROOT)} is missing manifest group references: {', '.join(missing_groups)}."
        )

    missing_tokens = _missing_doc_tokens(doc_path)
    if missing_tokens:
        failures.append(
            f"{doc_path.relative_to(REPO_ROOT)} is missing manifest ownership references: {', '.join(missing_tokens)}."
        )

    return failures


def main() -> int:
    """Run the final manifest-consumer drift pass for the CI hardening slice."""
    failures: list[str] = []

    try:
        manifest_groups = set(CiTargetManifest.load().group_names())
    except ManifestError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    workflow_groups = set().union(*(_workflow_groups(path) for path in WORKFLOW_PATHS))
    consistency_groups = _consistency_groups()

    if workflow_groups != manifest_groups:
        failures.append(
            "Workflow manifest-group usage drifted from the manifest target groups "
            f"(manifest={sorted(manifest_groups)}, workflows={sorted(workflow_groups)})."
        )

    if consistency_groups != EXPECTED_CONSISTENCY_GROUPS:
        failures.append(
            "Consistency-script manifest-group usage drifted from the approved shared groups "
            f"(expected={sorted(EXPECTED_CONSISTENCY_GROUPS)}, actual={sorted(consistency_groups)})."
        )

    for doc_path in DOC_PATHS:
        failures.extend(_validate_doc_alignment(doc_path, manifest_groups))

    if failures:
        print("ci target drift check failed:", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1

    print("ci target drift check passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
