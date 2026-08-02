#!/usr/bin/env python3
"""Check weekly checked-in media and tool readiness without decoding media.

This CI-only preflight validates catalog-referenced fixture headers, HLS
references, and required media tools. It deliberately excludes local
representative assets and does not run detector logic.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import shutil
import subprocess
import sys


REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_ROOT = Path("tests/fixtures/media")
CATALOG_PATH = FIXTURE_ROOT / "fixture_catalog.json"
GROUND_TRUTH_PATH = FIXTURE_ROOT / "ground_truth.json"
LFS_POINTER_PREFIX = b"version https://git-lfs.github.com/spec/v1"
REQUIRED_TOOLS = ("ffmpeg", "ffprobe")


@dataclass(frozen=True)
class PreflightFailure:
    """One environment problem that should not be reported as a detector failure."""

    subject: str
    reason: str


@dataclass(frozen=True)
class FixtureRequirement:
    """One required checked-in fixture and its reviewed HLS exception policy."""

    relative_path: str
    allow_missing_references: bool = False


def _load_json(path: Path, display_path: Path) -> object:
    """Load metadata while keeping failures repo-relative and actionable."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"{display_path} is missing") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"{display_path} is not valid JSON") from exc
    except OSError as exc:
        raise ValueError(f"{display_path} could not be read") from exc


def _required_fixtures(repo_root: Path) -> tuple[FixtureRequirement, ...]:
    """Return checked-in fixture paths required by the catalog and ground truth."""
    catalog_path = repo_root / CATALOG_PATH
    ground_truth_path = repo_root / GROUND_TRUTH_PATH
    catalog = _load_json(catalog_path, CATALOG_PATH)
    ground_truth = _load_json(ground_truth_path, GROUND_TRUTH_PATH)

    if not isinstance(catalog, dict) or not isinstance(ground_truth, dict):
        raise ValueError("fixture metadata roots must be JSON objects")

    paths: set[str] = set()
    validity_by_path: dict[str, str] = {}
    for group_name in ("video_files", "video_segments"):
        entries = catalog.get(group_name)
        if not isinstance(entries, list):
            raise ValueError(f"fixture catalog field '{group_name}' must be a list")
        for entry in entries:
            if not isinstance(entry, dict):
                raise ValueError(f"fixture catalog field '{group_name}' has a non-object entry")
            relative_path = entry.get("path")
            validity = entry.get("validity")
            if isinstance(relative_path, str) and isinstance(validity, str):
                validity_by_path[relative_path] = validity
                if validity == "valid":
                    paths.add(relative_path)

    local_cases = ground_truth.get("local_session_cases")
    if not isinstance(local_cases, list):
        raise ValueError("ground truth field 'local_session_cases' must be a list")
    for case in local_cases:
        if not isinstance(case, dict):
            raise ValueError("ground truth has a non-object local session case")
        fixture = case.get("fixture")
        if not isinstance(fixture, dict):
            raise ValueError("ground truth local session case has no fixture object")
        if fixture.get("kind") == "checked_in" and isinstance(fixture.get("path"), str):
            paths.add(fixture["path"])

    return tuple(
        FixtureRequirement(
            relative_path=relative_path,
            allow_missing_references=validity_by_path.get(relative_path) == "malformed",
        )
        for relative_path in sorted(paths)
    )


def _header(path: Path) -> bytes:
    """Read a small header without opening or decoding a full media stream."""
    with path.open("rb") as media_file:
        return media_file.read(64)


def _file_failure(path: Path, display_path: str) -> PreflightFailure | None:
    """Classify one expected media file from existence and header evidence."""
    if not path.is_file():
        return PreflightFailure(display_path, "required fixture is missing")

    header = _header(path)
    if not header:
        return PreflightFailure(display_path, "required fixture is empty")
    if header.startswith(LFS_POINTER_PREFIX):
        return PreflightFailure(
            display_path,
            "Git LFS pointer is unresolved; checkout must fetch media objects",
        )
    if path.suffix == ".mp4" and header[4:8] != b"ftyp":
        return PreflightFailure(display_path, "required MP4 has no ftyp header")
    if path.suffix == ".m3u8" and not header.startswith(b"#EXTM3U"):
        return PreflightFailure(display_path, "required playlist has no EXTM3U header")
    if path.suffix == ".ts" and header[0] != 0x47:
        return PreflightFailure(display_path, "required transport segment has no sync byte")
    return None


def _fixture_failures(
    repo_root: Path,
    requirement: FixtureRequirement,
) -> list[PreflightFailure]:
    """Return lightweight integrity failures for one file or HLS fixture path."""
    relative_path = requirement.relative_path
    relative_fixture_path = Path(relative_path)
    if relative_fixture_path.is_absolute() or ".." in relative_fixture_path.parts:
        return [
            PreflightFailure(
                "fixture metadata",
                "fixture paths must stay relative to tests/fixtures/media",
            )
        ]

    fixture_path = repo_root / FIXTURE_ROOT / relative_fixture_path
    display_path = str(FIXTURE_ROOT / relative_path)

    if fixture_path.is_file():
        failure = _file_failure(fixture_path, display_path)
        return [failure] if failure is not None else []
    if not fixture_path.is_dir():
        return [PreflightFailure(display_path, "required fixture is missing")]

    failures: list[PreflightFailure] = []
    playlist_path = fixture_path / "index.m3u8"
    playlist_failure = _file_failure(playlist_path, f"{display_path}/index.m3u8")
    if playlist_failure is not None:
        failures.append(playlist_failure)

    if playlist_failure is not None:
        return failures

    if not any(fixture_path.glob("*.ts")):
        failures.append(
            PreflightFailure(display_path, "required HLS fixture has no segments")
        )

    try:
        playlist_lines = playlist_path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError):
        return failures + [
            PreflightFailure(display_path, "required playlist could not be read")
        ]
    segment_references = tuple(
        line.strip()
        for line in playlist_lines
        if line.strip() and not line.startswith("#")
    )
    if not segment_references:
        failures.append(PreflightFailure(display_path, "required HLS fixture has no segments"))
    for segment_reference in segment_references:
        relative_segment = Path(segment_reference)
        if relative_segment.is_absolute() or ".." in relative_segment.parts:
            failures.append(
                PreflightFailure(
                    display_path,
                    "required playlist has an unsafe segment reference",
                )
            )
            continue
        segment_path = fixture_path / relative_segment
        if requirement.allow_missing_references and not segment_path.exists():
            continue
        failure = _file_failure(
            segment_path,
            str(FIXTURE_ROOT / relative_fixture_path / relative_segment),
        )
        if failure is not None:
            failures.append(failure)
    return failures


def _tool_failure(tool_name: str) -> PreflightFailure | None:
    """Return a failure when one required media tool is absent or unusable."""
    if shutil.which(tool_name) is None:
        return PreflightFailure(tool_name, "required tool is missing from PATH")
    try:
        result = subprocess.run(
            [tool_name, "-version"],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return PreflightFailure(tool_name, "required tool cannot report its version")
    if result.returncode != 0:
        return PreflightFailure(tool_name, "required tool cannot report its version")
    return None


def collect_preflight_failures(repo_root: Path = REPO_ROOT) -> list[PreflightFailure]:
    """Return all deterministic weekly-media readiness failures."""
    failures: list[PreflightFailure] = []
    try:
        required_fixtures = _required_fixtures(repo_root)
    except (OSError, UnicodeError, ValueError) as exc:
        return [PreflightFailure("fixture metadata", str(exc))]

    for tool_name in REQUIRED_TOOLS:
        failure = _tool_failure(tool_name)
        if failure is not None:
            failures.append(failure)
    for requirement in required_fixtures:
        failures.extend(_fixture_failures(repo_root, requirement))
    return failures


def main() -> int:
    """Print weekly media readiness and return a CI-friendly status."""
    failures = collect_preflight_failures()
    if failures:
        print("weekly media preflight failed:", file=sys.stderr)
        for failure in failures:
            print(f"- {failure.subject}: {failure.reason}", file=sys.stderr)
        return 1

    required_fixtures = _required_fixtures(REPO_ROOT)
    print(
        "weekly media preflight passed "
        f"(checked-in fixture roots={len(required_fixtures)}; "
        "ffmpeg/ffprobe=available; "
        "representative local assets=excluded)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
