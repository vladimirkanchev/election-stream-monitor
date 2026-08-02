#!/usr/bin/env python3
"""Build a bounded weekly-media result index from internal pytest JUnit XML.

The output retains only outcomes, normalized identities, bounded timing and
skip telemetry, tool versions, and artifact names. Raw JUnit XML and pytest
failure text remain outside the uploaded failure bundle.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import re
import subprocess
import sys
from typing import TypedDict
import xml.etree.ElementTree as ElementTree


SCHEMA_VERSION = "weekly_media_result_index_v2"
TARGET = "weekly_slow_media"
MAX_FAILED_TESTS = 24
MAX_SLOWEST_TESTS = 10
MAX_INDEX_BYTES = 64 * 1024
SAFE_CLASSNAME = re.compile(r"^[A-Za-z0-9_]+(?:\.[A-Za-z0-9_]+)*$")
SAFE_TEST_NAME = re.compile(r"^[A-Za-z0-9_]+")


class TestResultEntry(TypedDict):
    """One normalized test outcome retained in bounded weekly telemetry."""

    test_id: str
    outcome: str
    duration_seconds: float


def _command_version(command: str) -> str:
    """Return one safe version line for a known local media tool."""
    try:
        result = subprocess.run(
            [command, "-version"],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return "unavailable"
    if result.returncode != 0:
        return "unavailable"
    return result.stdout.splitlines()[0] if result.stdout else "unavailable"


def _environment_versions() -> dict[str, str]:
    """Return the small allowlisted environment projection for one result index."""
    try:
        import cv2
    except ImportError:
        opencv_version = "unavailable"
    else:
        opencv_version = str(cv2.__version__)

    try:
        import numpy
    except ImportError:
        numpy_version = "unavailable"
    else:
        numpy_version = str(numpy.__version__)

    return {
        "python": sys.version.split()[0],
        "ffmpeg": _command_version("ffmpeg"),
        "ffprobe": _command_version("ffprobe"),
        "opencv": opencv_version,
        "numpy": numpy_version,
    }


def _duration_seconds(raw_duration: str | None) -> float:
    """Normalize a JUnit testcase duration without preserving malformed input."""
    try:
        duration = float(raw_duration or 0)
    except ValueError:
        return 0.0
    if not math.isfinite(duration) or duration < 0:
        return 0.0
    return round(duration, 3)


def _test_outcome(testcase: ElementTree.Element) -> str:
    """Classify one pytest JUnit testcase without retaining failure text."""
    if testcase.find("error") is not None:
        return "errored"
    if testcase.find("failure") is not None:
        return "failed"
    if testcase.find("skipped") is not None:
        return "skipped"
    return "passed"


def _test_id(testcase: ElementTree.Element) -> str:
    """Return a normalized pytest identity without parameter values or paths."""
    class_name = testcase.get("classname", "").strip()
    name = testcase.get("name", "").strip()
    class_part = class_name if SAFE_CLASSNAME.fullmatch(class_name) else ""
    name_match = SAFE_TEST_NAME.match(name)
    if name_match is None:
        return "unknown"

    name_part = name_match.group()
    if "[" in name:
        name_part = f"{name_part}[parameterized]"
    return "::".join(part for part in (class_part, name_part) if part)


def _skip_category(testcase: ElementTree.Element) -> str | None:
    """Return a safe category for one skipped testcase without its raw reason."""
    skipped = testcase.find("skipped")
    if skipped is None:
        return None

    reason = " ".join(
        value
        for value in (skipped.get("message"), skipped.text)
        if isinstance(value, str)
    ).casefold()
    if "representative" in reason:
        return "optional_representative_media"
    if any(tool in reason for tool in ("ffmpeg", "ffprobe", "opencv")):
        return "media_tool_unavailable"
    return "unclassified"


def _test_result_entry(
    testcase: ElementTree.Element,
    outcome: str,
    duration_seconds: float,
) -> TestResultEntry:
    """Project one testcase into the shared bounded diagnostic shape."""
    return {
        "test_id": _test_id(testcase),
        "outcome": outcome,
        "duration_seconds": duration_seconds,
    }


def build_result_index(junit_path: Path) -> dict[str, object]:
    """Build the allowlisted weekly result summary from internal JUnit XML."""
    try:
        root = ElementTree.parse(junit_path).getroot()
    except (ElementTree.ParseError, OSError) as exc:
        raise ValueError("Unable to read pytest JUnit result XML.") from exc

    outcomes = {"passed": 0, "failed": 0, "errored": 0, "skipped": 0}
    failed_tests: list[TestResultEntry] = []
    slow_tests: list[TestResultEntry] = []
    skip_reasons: dict[str, int] = {}
    duration_seconds = 0.0
    for testcase in root.findall(".//testcase"):
        outcome = _test_outcome(testcase)
        duration = _duration_seconds(testcase.get("time"))
        test_entry = _test_result_entry(testcase, outcome, duration)
        outcomes[outcome] += 1
        duration_seconds += duration
        slow_tests.append(test_entry)
        if skip_category := _skip_category(testcase):
            skip_reasons[skip_category] = skip_reasons.get(skip_category, 0) + 1
        if outcome in {"failed", "errored"} and len(failed_tests) < MAX_FAILED_TESTS:
            failed_tests.append(test_entry)

    return {
        "schema_version": SCHEMA_VERSION,
        "target": TARGET,
        "environment": _environment_versions(),
        "summary": {
            "total": sum(outcomes.values()),
            **outcomes,
            "duration_seconds": round(duration_seconds, 3),
        },
        "failed_tests": failed_tests,
        "failed_tests_truncated": outcomes["failed"] + outcomes["errored"]
        > len(failed_tests),
        "slowest_tests": sorted(
            slow_tests,
            key=lambda entry: (
                -entry["duration_seconds"],
                entry["test_id"],
            ),
        )[:MAX_SLOWEST_TESTS],
        "skip_reasons": dict(sorted(skip_reasons.items())),
        "related_artifacts": {
            "preflight_log": "weekly-media-preflight.log",
            "detector_lab": "detector-lab-real-media/",
            "ground_truth": "ground-truth-failures/",
        },
    }


def write_result_index(index: dict[str, object], output_path: Path) -> None:
    """Write one bounded result index or reject an unexpectedly large payload."""
    serialized = f"{json.dumps(index, indent=2, sort_keys=True)}\n".encode()
    if len(serialized) > MAX_INDEX_BYTES:
        raise ValueError("Weekly media result index exceeded its 64 KiB limit.")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(serialized)


def _arguments() -> argparse.Namespace:
    """Parse the workflow-only result-index inputs."""
    parser = argparse.ArgumentParser(
        description="Build a sanitized weekly media pytest result index."
    )
    parser.add_argument("--junitxml", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    """Write the index printed on every run and retained after failures."""
    arguments = _arguments()
    write_result_index(
        build_result_index(arguments.junitxml),
        arguments.output,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
