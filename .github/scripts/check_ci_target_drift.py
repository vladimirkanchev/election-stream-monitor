#!/usr/bin/env python3
"""Check drift between the CI target manifest and its workflow, policy, and doc consumers.

This guard now verifies both:
- the broader manifest-to-consumer alignment
- the narrower alignment between the main workflow contract lane and the
  manifest-backed main PR consistency policy

Current enforced alignment contract:
- workflow-to-manifest
  - the shared reader-backed contract groups in `ci.yml` `test-and-build`
    must match the protected alignment group set
- policy-to-workflow
  - manifest groups consumed by manifest-backed `ContractGate` entries in
    `check_main_pr_consistency.py` must match the shared reader-backed
    `test-and-build` contract groups in `ci.yml`
- docs-to-manifest
  - CI-facing docs must keep the high-signal ownership references that match
    their role

It also relies on the current `ci.yml` ownership boundary: broad shared
contract consumers should be manifest-backed, while the tiny local integration
smoke path intentionally remains an inline workflow test. Fast backend CI
stays synthetic, while weekly validation owns the slow and real-media lanes.
The path-existence self-check is narrower: it covers CI-owned test paths only,
not the wider source/doc ownership rules this drift check reasons about.
"""

from __future__ import annotations

from dataclasses import dataclass
import sys
from pathlib import Path

import check_main_pr_consistency

from ci_target_manifest import (
    DocAlignmentRequirement,
    ManifestError,
    REPO_ROOT,
    alignment_contract,
    workflow_reader_groups,
)


CI_WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "ci.yml"


@dataclass(frozen=True)
class DriftCheckResult:
    """Final workflow/policy/docs alignment result for the protected lane."""

    failures: tuple[str, ...]

    @property
    def ok(self) -> bool:
        """Return whether the protected-lane alignment contract still holds."""
        return not self.failures


def _sorted_groups(groups: set[str]) -> list[str]:
    """Return a stable sorted rendering of one manifest-group set."""
    return sorted(groups)


def _relative_doc_path(path: Path) -> str:
    """Return one doc path relative to the repo root for readable failures."""
    return str(path.relative_to(REPO_ROOT))


def _workflow_groups(path: Path) -> set[str]:
    """Return the manifest groups consumed by one workflow file.

    This intentionally sees only shared reader-backed consumers, not the tiny
    local smoke command that remains inline in `ci.yml`. The shared helper
    normalizes multiline shell formatting first so light workflow formatting
    changes do not affect the extracted group set, and it also tolerates
    `python` vs `python3` call-site variation.
    """
    return set(workflow_reader_groups(path))


def _consistency_workflow_groups() -> set[str]:
    """Return the manifest groups used by the main CI workflow contract lane.

    This is the workflow-side alignment target for the main PR consistency
    policy. Weekly-only groups are intentionally excluded because that policy
    check should track the protected contract lane, not every workflow in the
    repo.

    At the current workflow shape, this means the shared reader-backed
    `test-and-build` contract groups in `ci.yml`, not weekly-only groups,
    the synthetic fast backend lane, or the inline smoke path.
    """
    return _workflow_groups(CI_WORKFLOW_PATH)


def _consistency_groups() -> set[str]:
    """Return the manifest groups consumed by manifest-backed policy gates.

    Read the groups from the explicit policy-owner helper instead of scraping
    `ContractGate(...)` internals. That keeps the drift check less sensitive
    to future internal refactors of the policy script.
    """
    return set(check_main_pr_consistency.manifest_policy_groups())


def _doc_mentions(path: Path, values: tuple[str, ...]) -> set[str]:
    """Return which required manifest groups are named in one CI-facing doc."""
    text = path.read_text()
    return {value for value in values if value in text}


def _missing_doc_tokens(path: Path, required_tokens: tuple[str, ...]) -> list[str]:
    """Return missing manifest-reference tokens for one CI-facing doc."""
    text = path.read_text()
    return [token for token in required_tokens if token not in text]


def _validate_doc_alignment(
    requirement: DocAlignmentRequirement,
) -> list[str]:
    """Return documentation drift failures for one CI-facing doc."""
    failures: list[str] = []
    doc_path = requirement.path
    missing_groups = sorted(
        set(requirement.required_groups) - _doc_mentions(doc_path, requirement.required_groups)
    )
    if missing_groups:
        failures.append(
            f"{_relative_doc_path(doc_path)} is missing required alignment group references: {', '.join(missing_groups)}."
        )

    missing_tokens = _missing_doc_tokens(doc_path, requirement.required_tokens)
    if missing_tokens:
        failures.append(
            f"{_relative_doc_path(doc_path)} is missing manifest ownership references: {', '.join(missing_tokens)}."
        )

    return failures


def _group_drift_failures(
    expected_alignment_groups: set[str],
    workflow_groups: set[str],
    policy_groups: set[str],
) -> list[str]:
    """Return workflow/policy group alignment failures for the protected lane."""
    failures: list[str] = []

    if workflow_groups != expected_alignment_groups:
        failures.append(
            "Main workflow contract-lane usage drifted from the protected alignment groups "
            f"(expected={_sorted_groups(expected_alignment_groups)}, workflow={_sorted_groups(workflow_groups)})."
        )

    if policy_groups != workflow_groups:
        failures.append(
            "Consistency-script manifest-group usage drifted from the main workflow contract lane "
            f"(workflow={_sorted_groups(workflow_groups)}, actual={_sorted_groups(policy_groups)})."
        )

    return failures


def run_drift_check() -> DriftCheckResult:
    """Return the protected-lane manifest-consumer drift result.

    This is the narrow alignment contract used in protected lanes after
    manifest validation and CI-owned test-path existence checks, but before
    broader policy or contract execution.
    """
    contract = alignment_contract()
    expected_alignment_groups = set(contract.protected_workflow_groups)
    workflow_groups = _consistency_workflow_groups()
    policy_groups = _consistency_groups()

    failures = _group_drift_failures(
        expected_alignment_groups,
        workflow_groups,
        policy_groups,
    )
    for requirement in contract.doc_requirements:
        failures.extend(_validate_doc_alignment(requirement))

    return DriftCheckResult(failures=tuple(failures))


def main() -> int:
    """Run the final manifest-consumer drift pass for the CI hardening slice.

    In particular, this verifies that the main PR consistency policy consumes
    the same protected stable manifest groups as the reader-backed
    `test-and-build` contract lane, while the manifest remains the owner of
    the shared target language through one explicit alignment model.
    """
    try:
        result = run_drift_check()
    except ManifestError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    if not result.ok:
        print("ci target drift check failed:", file=sys.stderr)
        for failure in result.failures:
            print(f"- {failure}", file=sys.stderr)
        return 1

    print("ci target drift check passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
