#!/usr/bin/env python3
"""Check drift between the CI target manifest and its workflow, policy, and doc consumers.

This guard now verifies both:
- the broader manifest-to-consumer alignment
- the narrower alignment between the main workflow contract lane and the
  manifest-backed main PR consistency policy

It also relies on the current `ci.yml` ownership boundary: broad shared
contract consumers should be manifest-backed, while the tiny local integration
smoke path intentionally remains an inline workflow test. Fast backend CI
stays synthetic, while weekly validation owns the slow and real-media lanes.
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

from ci_target_manifest import (
    ManifestError,
    REPO_ROOT,
    load_ci_target_manifest,
)


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

DOC_REQUIRED_TOKENS = (
    ".github/ci_test_targets.json",
    ".github/scripts/read_ci_test_targets.py",
    ".github/scripts/validate_ci_test_targets.py",
)


def _workflow_groups(path: Path) -> set[str]:
    """Return the manifest groups consumed by one workflow file.

    This intentionally sees only shared reader-backed consumers, not the tiny
    local smoke command that remains inline in `ci.yml`.
    """
    return set(READ_TARGET_PATTERN.findall(path.read_text()))


def _all_workflow_groups() -> set[str]:
    """Return every manifest group consumed by workflow files."""
    return set().union(*(_workflow_groups(path) for path in WORKFLOW_PATHS))


def _consistency_workflow_groups() -> set[str]:
    """Return the manifest groups used by the main CI workflow contract lane.

    This is the workflow-side alignment target for the main PR consistency
    policy. Weekly-only groups are intentionally excluded because that policy
    check should track the protected contract lane, not every workflow in the
    repo.

    At the current workflow shape, this means the shared reader-backed
    `test-and-build` contract groups in `ci.yml`, not the synthetic fast
    backend lane or the weekly heavy-validation lanes.
    """
    return _workflow_groups(CI_WORKFLOW_PATH)


def _parse_consistency_module() -> ast.Module:
    """Return the parsed consistency-policy module."""
    return ast.parse(CONSISTENCY_SCRIPT_PATH.read_text())


def _tuple_constants(module: ast.Module) -> dict[str, tuple[str, ...]]:
    """Return top-level tuple constants from the consistency script."""
    tuple_constants: dict[str, tuple[str, ...]] = {}

    for node in module.body:
        if not isinstance(node, ast.Assign):
            continue
        if len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name):
            continue
        if not isinstance(node.value, ast.Tuple):
            continue

        constant_values = _string_tuple(node.value)
        if constant_values:
            tuple_constants[node.targets[0].id] = constant_values

    return tuple_constants


def _string_tuple(node: ast.Tuple) -> tuple[str, ...]:
    """Return one AST tuple of string constants, or an empty tuple."""
    values: list[str] = []

    for item in node.elts:
        if not isinstance(item, ast.Constant) or not isinstance(item.value, str):
            return ()
        values.append(item.value)

    return tuple(values)


def _consistency_groups() -> set[str]:
    """Return the manifest groups consumed by manifest-backed policy gates.

    The main consistency script now names some groups through top-level tuple
    constants, and the gates themselves now use clearer field names, so this
    reader accepts both inline tuples and named constants.
    """
    module = _parse_consistency_module()
    tuple_constants = _tuple_constants(module)
    groups: set[str] = set()

    for node in ast.walk(module):
        if not isinstance(node, ast.Call):
            continue
        if not isinstance(node.func, ast.Name) or node.func.id != "ContractGate":
            continue

        for keyword in node.keywords:
            if keyword.arg != "manifest_groups":
                continue
            if isinstance(keyword.value, ast.Tuple):
                groups.update(_string_tuple(keyword.value))
                continue
            if isinstance(keyword.value, ast.Name):
                groups.update(tuple_constants.get(keyword.value.id, ()))

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
    missing_groups = sorted(manifest_groups - _doc_mentions(doc_path, manifest_groups))
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
    """Run the final manifest-consumer drift pass for the CI hardening slice.

    In particular, this verifies that the main PR consistency policy consumes
    the same stable manifest groups as the reader-backed `test-and-build`
    contract lane, while the manifest remains the owner of the shared target
    language.
    """
    failures: list[str] = []

    try:
        manifest_groups = set(load_ci_target_manifest().group_names())
    except ManifestError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    workflow_groups = _all_workflow_groups()
    consistency_workflow_groups = _consistency_workflow_groups()
    consistency_groups = _consistency_groups()

    if workflow_groups != manifest_groups:
        failures.append(
            "Workflow manifest-group usage drifted from the manifest target groups "
            f"(manifest={sorted(manifest_groups)}, workflows={sorted(workflow_groups)})."
        )

    if consistency_groups != consistency_workflow_groups:
        failures.append(
            "Consistency-script manifest-group usage drifted from the main workflow contract lane "
            f"(workflow={sorted(consistency_workflow_groups)}, actual={sorted(consistency_groups)})."
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
