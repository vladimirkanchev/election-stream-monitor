"""Focused tests for the lightweight fixture/environment policy guard."""

from __future__ import annotations

import importlib
from pathlib import Path
import sys


SCRIPTS_DIR = Path(__file__).resolve().parent.parent / ".github" / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

check_fixture_environment_policy = importlib.import_module(
    "check_fixture_environment_policy"
)


def _assert_one_failure_message(
    failures: list[check_fixture_environment_policy.PolicyFailure],
    expected_snippet: str,
) -> None:
    """Assert one policy failure with the expected message fragment."""
    assert len(failures) == 1
    assert expected_snippet in failures[0].message


def test_policy_scan_covers_docs_python_tests_and_fixture_metadata() -> None:
    scanned_paths = check_fixture_environment_policy._scanned_relative_paths()

    assert "README.md" in scanned_paths
    assert "docs/testing-and-validation.md" in scanned_paths
    assert "tests/test_detector_lab.py" in scanned_paths
    assert "tests/fixtures/media/ground_truth.json" in scanned_paths


def test_allowed_local_only_reference_files_do_not_fail() -> None:
    failures = check_fixture_environment_policy._local_only_reference_failures(
        relative_path="detector_lab/README.md",
        text="tests/fixtures/media/election_clips/normal_baseline/example.mp4",
    )

    assert failures == []


def test_allowed_local_only_reference_metadata_file_do_not_fail() -> None:
    failures = check_fixture_environment_policy._local_only_reference_failures(
        relative_path="tests/fixtures/media/video_file_second_labels.json",
        text='{"path":"election_clips/normal_baseline/example.mp4"}',
    )

    assert failures == []


def test_docs_file_with_local_only_reference_outside_allowlist_fails() -> None:
    failures = check_fixture_environment_policy._local_only_reference_failures(
        relative_path="docs/random-guide.md",
        text="tests/fixtures/media/election_clips/normal_baseline/example.mp4",
    )

    assert len(failures) == 2
    assert failures[0].relative_path == "docs/random-guide.md"
    assert "local-only fixture path" in failures[0].message


def test_metadata_file_with_local_only_reference_outside_allowlist_fails() -> None:
    failures = check_fixture_environment_policy._local_only_reference_failures(
        relative_path="tests/fixtures/media/custom_labels.json",
        text='{"path":"election_clips/normal_baseline/example.mp4"}',
    )

    assert failures[0].relative_path == "tests/fixtures/media/custom_labels.json"
    _assert_one_failure_message(failures, "local-only fixture path")


def test_python_test_hardcoded_repo_root_fails() -> None:
    failures = check_fixture_environment_policy._hard_coded_repo_root_failures(
        relative_path="tests/test_example.py",
        text='Path("/home/vlad/Projects/election-stream-monitor") / "tests/fixtures/media"',
    )

    _assert_one_failure_message(failures, "hardcodes the developer repo root")


def test_non_test_hardcoded_repo_root_is_ignored() -> None:
    failures = check_fixture_environment_policy._hard_coded_repo_root_failures(
        relative_path="docs/example.md",
        text="cd /home/vlad/Projects/election-stream-monitor",
    )

    assert failures == []


def test_policy_failures_for_file_combines_checks() -> None:
    failures = check_fixture_environment_policy._policy_failures_for_text(
        relative_path="tests/_fixture_policy_tmp_case.py",
        text='Path("/home/vlad/Projects/election-stream-monitor")\n'
        "tests/fixtures/media/election_clips/normal_baseline/example.mp4\n",
    )

    assert len(failures) == 3


def test_current_repo_passes_fixture_environment_policy_check() -> None:
    assert check_fixture_environment_policy.collect_policy_failures() == ()
