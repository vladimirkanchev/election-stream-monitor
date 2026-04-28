#!/usr/bin/env python3
"""Lightweight main-PR consistency checks for docs and workflow-sensitive changes."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]

DOC_PATHS = (
    "README.md",
    "frontend/README.md",
    "docs/",
)

WORKFLOW_PATHS = (
    ".github/workflows/",
    "frontend/package.json",
)

CONTRACT_PATHS = (
    "src/source_validation.py",
    "src/session_io.py",
    "src/stream_loader_contracts.py",
    "src/api/routers/sessions.py",
    "frontend/src/bridge/contract.ts",
    "frontend/src/bridge/contractErrors.ts",
    "frontend/src/bridge/contractDetectors.ts",
    "frontend/src/bridge/contractSessionSnapshot.ts",
    "docs/contracts.md",
)


def _changed_files(diff_range: str) -> list[str]:
    result = subprocess.run(
        ["git", "diff", "--name-only", diff_range],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def _matches_any(path: str, prefixes: tuple[str, ...]) -> bool:
    return any(path == prefix or path.startswith(prefix) for prefix in prefixes)


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: check_main_pr_consistency.py <diff-range>", file=sys.stderr)
        return 2

    changed = _changed_files(sys.argv[1])
    changed_set = set(changed)

    docs_changed = any(_matches_any(path, DOC_PATHS) for path in changed)
    workflow_sensitive = any(_matches_any(path, WORKFLOW_PATHS) for path in changed)
    contract_sensitive = any(path in CONTRACT_PATHS for path in changed_set)

    failures: list[str] = []

    if workflow_sensitive and not docs_changed:
        failures.append(
            "Workflow or package CI entrypoints changed without any docs update "
            "(expected one of README.md, frontend/README.md, or docs/*)."
        )

    if contract_sensitive and "docs/contracts.md" not in changed_set:
        failures.append(
            "Contract-sensitive code changed without updating docs/contracts.md."
        )

    if failures:
        print("main-pr-consistency check failed:", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        print("changed files:", file=sys.stderr)
        for path in changed:
            print(f"  {path}", file=sys.stderr)
        return 1

    print("main-pr-consistency check passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
