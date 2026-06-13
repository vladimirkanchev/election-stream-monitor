#!/usr/bin/env python3
"""Check lightweight fixture and environment policy expectations.

This is a narrow maintainer guard, not a general linter. It only catches the
highest-signal drift:
- local-only fixture references leaking into shared docs/tests/metadata
- Python tests hardcoding the developer repo root
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[2]
DEVELOPER_REPO_ROOT = "/home/vlad/Projects/election-stream-monitor"
LOCAL_ONLY_REFERENCE_SNIPPETS = (
    "tests/fixtures/media/election_clips/",
    "election_clips/normal_baseline/",
)
ALLOWED_LOCAL_ONLY_REFERENCE_PATHS = frozenset(
    {
        "detector_lab/README.md",
        "docs/fixture-environment-policy.md",
        "tests/test_detector_lab.py",
        "tests/test_fixture_environment_policy_check.py",
        "tests/fixtures/media/video_file_second_labels.json",
    }
)
ALLOWED_REPO_ROOT_TEST_PATHS = frozenset(
    {
        "tests/test_fixture_environment_policy_check.py",
    }
)
SCANNED_METADATA_PATHS = (
    "tests/fixtures/media/api_stream_expectations.json",
    "tests/fixtures/media/fixture_catalog.json",
    "tests/fixtures/media/ground_truth.json",
    "tests/fixtures/media/video_file_second_labels.json",
)
SCANNED_DOC_ROOTS = ("docs",)
SCANNED_TEST_ROOTS = ("tests",)
STATIC_SCANNED_PATHS = ("README.md", "detector_lab/README.md")


@dataclass(frozen=True)
class PolicyFailure:
    """One fixture/environment policy failure."""

    relative_path: str
    message: str


def _scanned_relative_paths() -> tuple[str, ...]:
    """Return the repo-relative files covered by this lightweight policy check."""
    relative_paths = set(STATIC_SCANNED_PATHS)
    for doc_root in SCANNED_DOC_ROOTS:
        relative_paths.update(
            str(path.relative_to(REPO_ROOT))
            for path in (REPO_ROOT / doc_root).rglob("*.md")
        )
    for test_root in SCANNED_TEST_ROOTS:
        relative_paths.update(
            str(path.relative_to(REPO_ROOT))
            for path in (REPO_ROOT / test_root).rglob("*.py")
        )
    relative_paths.update(SCANNED_METADATA_PATHS)
    return tuple(sorted(relative_paths))


def _local_only_reference_failures(
    *,
    relative_path: str,
    text: str,
) -> list[PolicyFailure]:
    """Return failures for local-only fixture references outside the allowlist."""
    if relative_path in ALLOWED_LOCAL_ONLY_REFERENCE_PATHS:
        return []

    failures: list[PolicyFailure] = []
    for snippet in LOCAL_ONLY_REFERENCE_SNIPPETS:
        if snippet not in text:
            continue
        failures.append(
            PolicyFailure(
                relative_path=relative_path,
                message=(
                    "references local-only fixture path "
                    f"`{snippet}` outside the explicit allowlist"
                ),
            )
        )
    return failures


def _hard_coded_repo_root_failures(
    *,
    relative_path: str,
    text: str,
) -> list[PolicyFailure]:
    """Return failures for Python tests that hardcode the developer repo root."""
    if not relative_path.startswith("tests/") or not relative_path.endswith(".py"):
        return []
    if relative_path in ALLOWED_REPO_ROOT_TEST_PATHS:
        return []
    if DEVELOPER_REPO_ROOT not in text:
        return []
    return [
        PolicyFailure(
            relative_path=relative_path,
            message=(
                "hardcodes the developer repo root "
                f"`{DEVELOPER_REPO_ROOT}` instead of resolving it dynamically"
            ),
        )
    ]


def _policy_failures_for_file(relative_path: str) -> tuple[PolicyFailure, ...]:
    """Return all fixture/environment policy failures for one repo file."""
    text = (REPO_ROOT / relative_path).read_text(encoding="utf-8")
    return _policy_failures_for_text(relative_path=relative_path, text=text)


def _policy_failures_for_text(
    *,
    relative_path: str,
    text: str,
) -> tuple[PolicyFailure, ...]:
    """Return all fixture/environment policy failures for one text payload."""
    failures = _local_only_reference_failures(relative_path=relative_path, text=text)
    failures.extend(_hard_coded_repo_root_failures(relative_path=relative_path, text=text))
    return tuple(failures)


def collect_policy_failures() -> tuple[PolicyFailure, ...]:
    """Return all current fixture/environment policy failures."""
    failures: list[PolicyFailure] = []
    for relative_path in _scanned_relative_paths():
        failures.extend(_policy_failures_for_file(relative_path))
    return tuple(failures)


def main() -> int:
    """Run the lightweight fixture/environment policy check."""
    failures = collect_policy_failures()
    if failures:
        print("fixture/environment policy check failed:", file=sys.stderr)
        for failure in failures:
            print(
                f"- {failure.relative_path}: {failure.message}",
                file=sys.stderr,
            )
        return 1

    print(
        "fixture/environment policy check passed "
        f"(scanned {len(_scanned_relative_paths())} doc/test/metadata file(s))"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
