"""Regression coverage for the weekly-media index schema, bounds, and redaction."""

from __future__ import annotations

import importlib
import json
from pathlib import Path
import sys

import pytest


SCRIPTS_DIR = Path(__file__).resolve().parent.parent / ".github" / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

result_index = importlib.import_module("build_weekly_media_result_index")


def _write_junit(path: Path, testcases: str) -> None:
    """Write the smallest JUnit document needed by one result-index test."""
    path.write_text(f"<testsuites><testsuite>{testcases}</testsuite></testsuites>")


def test_result_index_projects_safe_outcomes_without_failure_text(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The index should retain outcomes without copying pytest traceback text."""
    junit_path = tmp_path / "results.xml"
    _write_junit(
        junit_path,
        """
        <testcase classname="tests.test_media" name="test_passes" time="0.123" />
        <testcase classname="tests.test_media" name="test_fails[/private/path?api_key=secret-token]" time="1.234">
          <failure>postgresql://operator:secret-token@db/internal and traceback text must not be copied</failure>
        </testcase>
        <testcase classname="tests.test_media" name="test_errors" time="2.0"><error /></testcase>
        <testcase classname="tests.test_media" name="test_skips" time="0.2"><skipped /></testcase>
        """,
    )
    monkeypatch.setattr(
        result_index,
        "_environment_versions",
        lambda: {
            "python": "3.12",
            "ffmpeg": "7",
            "ffprobe": "7",
            "opencv": "4",
            "numpy": "2",
        },
    )

    index = result_index.build_result_index(junit_path)

    assert index["summary"] == {
        "total": 4,
        "passed": 1,
        "failed": 1,
        "errored": 1,
        "skipped": 1,
        "duration_seconds": 3.557,
    }
    assert index["failed_tests"] == [
        {
            "test_id": "tests.test_media::test_fails[parameterized]",
            "outcome": "failed",
            "duration_seconds": 1.234,
        },
        {
            "test_id": "tests.test_media::test_errors",
            "outcome": "errored",
            "duration_seconds": 2.0,
        },
    ]
    assert "secret-token" not in json.dumps(index)
    assert "/private/path" not in json.dumps(index)
    assert "postgresql://" not in json.dumps(index)
    assert index["related_artifacts"]["preflight_log"] == "weekly-media-preflight.log"


def test_result_index_bounds_and_orders_slowest_tests(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Timing telemetry should retain only the slowest normalized test entries."""
    junit_path = tmp_path / "results.xml"
    case_count = result_index.MAX_SLOWEST_TESTS + 2
    _write_junit(
        junit_path,
        "".join(
            f'<testcase classname="tests.test_media" name="test_{index}" time="{index}" />'
            for index in range(case_count)
        ),
    )
    monkeypatch.setattr(result_index, "_environment_versions", lambda: {})

    index = result_index.build_result_index(junit_path)
    slowest_tests = index["slowest_tests"]

    assert len(slowest_tests) == result_index.MAX_SLOWEST_TESTS
    assert [entry["duration_seconds"] for entry in slowest_tests] == list(
        reversed([float(index) for index in range(2, case_count)])
    )


def test_result_index_projects_safe_skip_categories(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Skipped cases should expose allowlisted categories rather than raw reasons."""
    junit_path = tmp_path / "results.xml"
    _write_junit(
        junit_path,
        """
        <testcase classname="tests.test_media" name="test_optional" time="0.1">
          <skipped message="Representative asset is unavailable at /private/path" />
        </testcase>
        <testcase classname="tests.test_media" name="test_tool" time="0.1">
          <skipped message="ffmpeg is unavailable" />
        </testcase>
        <testcase classname="tests.test_media" name="test_unknown" time="0.1">
          <skipped message="secret-token" />
        </testcase>
        """,
    )
    monkeypatch.setattr(result_index, "_environment_versions", lambda: {})

    index = result_index.build_result_index(junit_path)

    assert index["skip_reasons"] == {
        "media_tool_unavailable": 1,
        "optional_representative_media": 1,
        "unclassified": 1,
    }
    assert "secret-token" not in json.dumps(index)
    assert "/private/path" not in json.dumps(index)


def test_environment_versions_keep_only_reviewed_media_and_detector_lab_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The result index should retain a small reproducible toolchain projection."""
    monkeypatch.setattr(result_index, "_command_version", lambda command: command)

    versions = result_index._environment_versions()

    assert set(versions) == {"python", "ffmpeg", "ffprobe", "opencv", "numpy"}
    assert versions["ffmpeg"] == "ffmpeg"
    assert versions["ffprobe"] == "ffprobe"
    assert all(isinstance(version, str) and version for version in versions.values())


def test_result_index_rejects_unsafe_junit_identity_parts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unexpected JUnit attributes must not become diagnostic identifiers."""
    junit_path = tmp_path / "results.xml"
    _write_junit(
        junit_path,
        '<testcase classname="/private/path" name="../../secret" time="0"><failure /></testcase>',
    )
    monkeypatch.setattr(result_index, "_environment_versions", lambda: {})

    index = result_index.build_result_index(junit_path)

    assert index["failed_tests"] == [
        {"test_id": "unknown", "outcome": "failed", "duration_seconds": 0.0}
    ]


def test_result_index_bounds_failed_test_entries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A high-failure run should retain a bounded summary instead of every traceback."""
    junit_path = tmp_path / "results.xml"
    _write_junit(
        junit_path,
        "".join(
            f'<testcase classname="tests.test_media" name="test_{index}" time="0.1">'
            "<failure /></testcase>"
            for index in range(result_index.MAX_FAILED_TESTS + 1)
        ),
    )
    monkeypatch.setattr(result_index, "_environment_versions", lambda: {})

    index = result_index.build_result_index(junit_path)

    assert len(index["failed_tests"]) == result_index.MAX_FAILED_TESTS
    assert index["failed_tests_truncated"] is True


@pytest.mark.parametrize("duration", ["-1", "nan", "inf", "invalid"])
def test_result_index_normalizes_invalid_durations(
    duration: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Malformed JUnit timing must not produce negative or non-JSON values."""
    junit_path = tmp_path / "results.xml"
    _write_junit(
        junit_path,
        f'<testcase classname="tests.test_media" name="test_case" time="{duration}" />',
    )
    monkeypatch.setattr(result_index, "_environment_versions", lambda: {})

    index = result_index.build_result_index(junit_path)

    assert index["summary"]["duration_seconds"] == 0.0


def test_write_result_index_rejects_oversized_payload(tmp_path: Path) -> None:
    """The result-index artifact must stay within the published size limit."""
    with pytest.raises(ValueError, match="64 KiB"):
        result_index.write_result_index(
            {"payload": "x" * result_index.MAX_INDEX_BYTES},
            tmp_path / "results.json",
        )
