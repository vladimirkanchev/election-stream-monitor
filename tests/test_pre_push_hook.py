"""Focused tests for the optional lightweight pre-push hook.

Keep this slice narrow:
- docs/workflow-only push -> `docs-check`
- runtime/test push -> `test-fast`
- unrelated push -> skip
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent
PRE_PUSH_HOOK = REPO_ROOT / "scripts" / "git-hooks" / "pre-push"
CAPTURE_ONLY_ENV = {"PRE_PUSH_CAPTURE_ONLY": "1"}

HOOK_ROUTING_CASES = (
    (
        "docs_only",
        ["docs/testing-and-validation.md", "README.md", ".github/pull_request_template.md"],
        "would run just docs-check",
    ),
    (
        "runtime_or_test",
        ["src/session_service.py", "tests/test_session_service_start.py"],
        "would run just test-fast",
    ),
    (
        "unrelated",
        ["notes/todo.txt"],
        "no matching guarded paths",
    ),
)


def _run_pre_push_hook(changed_files: list[str]) -> subprocess.CompletedProcess[str]:
    """Run the hook in capture mode for one pushed-file scenario."""
    return subprocess.run(
        ["bash", str(PRE_PUSH_HOOK)],
        cwd=REPO_ROOT,
        env={
            **CAPTURE_ONLY_ENV,
            "PRE_PUSH_TEST_CHANGED_FILES": "\n".join(changed_files),
        },
        check=False,
        capture_output=True,
        text=True,
    )


def _assert_successful_routing(
    changed_files: list[str], expected_output_snippet: str
) -> None:
    """Assert one hook routing decision in capture mode."""
    completed = _run_pre_push_hook(changed_files)

    assert completed.returncode == 0
    assert expected_output_snippet in completed.stdout


@pytest.mark.parametrize(
    ("_case_name", "changed_files", "expected_output_snippet"),
    HOOK_ROUTING_CASES,
)
def test_pre_push_hook_routes_changes_to_the_expected_lane(
    _case_name: str,
    changed_files: list[str],
    expected_output_snippet: str,
) -> None:
    _assert_successful_routing(changed_files, expected_output_snippet)
