"""Focused regression coverage for the non-decoding weekly media preflight."""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / ".github" / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

preflight = importlib.import_module("check_weekly_media_preflight")


def _write_metadata(
    root: Path,
    *,
    fixture_path: str = "video_files/valid.mp4",
    validity: str = "valid",
) -> None:
    """Write the smallest catalog and local truth inputs for one preflight case."""
    media_root = root / "tests" / "fixtures" / "media"
    media_root.mkdir(parents=True)
    (media_root / "fixture_catalog.json").write_text(
        json.dumps(
            {
                "video_files": [
                    {"path": fixture_path, "validity": validity},
                ],
                "video_segments": [],
            }
        )
    )
    (media_root / "ground_truth.json").write_text(
        json.dumps(
            {
                "local_session_cases": [
                    {"fixture": {"kind": "checked_in", "path": fixture_path}},
                ]
            }
        )
    )


def _write_valid_mp4(root: Path, relative_path: str = "video_files/valid.mp4") -> None:
    """Write a minimal header suitable for this integrity-only preflight."""
    path = root / "tests" / "fixtures" / "media" / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\x00\x00\x00\x18ftypisom" + b"\x00" * 48)


def _allow_required_tools(monkeypatch) -> None:
    """Keep fixture tests independent from tools installed on the test host."""
    monkeypatch.setattr(preflight.shutil, "which", lambda tool_name: "/usr/bin/tool")
    monkeypatch.setattr(preflight, "_tool_failure", lambda tool_name: None)


def _write_hls_fixture(root: Path, *, include_segment: bool) -> None:
    """Write one minimal playlist with an optional referenced TS segment."""
    fixture_dir = root / "tests" / "fixtures" / "media" / "video_segments" / "valid"
    fixture_dir.mkdir(parents=True)
    (fixture_dir / "index.m3u8").write_text(
        "#EXTM3U\n#EXTINF:1.0,\nsegment_0000.ts\n",
        encoding="utf-8",
    )
    if include_segment:
        (fixture_dir / "segment_0000.ts").write_bytes(b"\x47" + b"\x00" * 63)


def test_preflight_accepts_valid_checked_in_media_and_ignores_representative_assets(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Missing optional representative media must not affect weekly readiness."""
    _write_metadata(tmp_path)
    _write_valid_mp4(tmp_path)
    _allow_required_tools(monkeypatch)

    assert preflight.collect_preflight_failures(tmp_path) == []


def test_preflight_classifies_missing_required_fixture(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """A missing checked-in fixture should fail before detector execution."""
    _write_metadata(tmp_path)
    _allow_required_tools(monkeypatch)

    failures = preflight.collect_preflight_failures(tmp_path)

    assert [(failure.subject, failure.reason) for failure in failures] == [
        ("tests/fixtures/media/video_files/valid.mp4", "required fixture is missing"),
    ]


def test_preflight_classifies_unresolved_lfs_pointer(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """An LFS pointer should produce an actionable checkout failure."""
    _write_metadata(tmp_path)
    pointer_path = tmp_path / "tests" / "fixtures" / "media" / "video_files" / "valid.mp4"
    pointer_path.parent.mkdir(parents=True)
    pointer_path.write_bytes(preflight.LFS_POINTER_PREFIX + b"\noid sha256:deadbeef\n")
    _allow_required_tools(monkeypatch)

    failures = preflight.collect_preflight_failures(tmp_path)

    assert failures[0].subject == "tests/fixtures/media/video_files/valid.mp4"
    assert "Git LFS pointer is unresolved" in failures[0].reason


def test_preflight_classifies_missing_required_tools(tmp_path: Path, monkeypatch) -> None:
    """Missing FFmpeg tools should remain environment failures, not test skips."""
    _write_metadata(tmp_path)
    _write_valid_mp4(tmp_path)
    monkeypatch.setattr(preflight.shutil, "which", lambda tool_name: None)

    failures = preflight.collect_preflight_failures(tmp_path)

    assert {(failure.subject, failure.reason) for failure in failures} == {
        ("ffmpeg", "required tool is missing from PATH"),
        ("ffprobe", "required tool is missing from PATH"),
    }


def test_preflight_reports_invalid_metadata_without_absolute_paths(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Metadata parse failures should be actionable without runner paths."""
    _write_metadata(tmp_path)
    catalog_path = tmp_path / "tests" / "fixtures" / "media" / "fixture_catalog.json"
    catalog_path.write_text("not-json", encoding="utf-8")
    _allow_required_tools(monkeypatch)

    failures = preflight.collect_preflight_failures(tmp_path)

    assert failures == [
        preflight.PreflightFailure(
            "fixture metadata",
            "tests/fixtures/media/fixture_catalog.json is not valid JSON",
        )
    ]
    assert str(tmp_path) not in failures[0].reason


def test_preflight_checks_playlist_references_instead_of_unrelated_segments(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """A valid HLS root must contain every segment named by its playlist."""
    _write_metadata(tmp_path, fixture_path="video_segments/valid")
    _write_hls_fixture(tmp_path, include_segment=False)
    unrelated_segment = (
        tmp_path
        / "tests"
        / "fixtures"
        / "media"
        / "video_segments"
        / "valid"
        / "unrelated.ts"
    )
    unrelated_segment.write_bytes(b"\x47" + b"\x00" * 63)
    _allow_required_tools(monkeypatch)

    failures = preflight.collect_preflight_failures(tmp_path)

    assert failures == [
        preflight.PreflightFailure(
            "tests/fixtures/media/video_segments/valid/segment_0000.ts",
            "required fixture is missing",
        )
    ]


def test_preflight_preserves_intentionally_missing_playlist_reference(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Catalog-declared malformed HLS may retain its reviewed missing segment."""
    _write_metadata(
        tmp_path,
        fixture_path="video_segments/valid",
        validity="malformed",
    )
    _write_hls_fixture(tmp_path, include_segment=False)
    fixture_dir = (
        tmp_path / "tests" / "fixtures" / "media" / "video_segments" / "valid"
    )
    (fixture_dir / "segment_0001.ts").write_bytes(b"\x47" + b"\x00" * 63)
    _allow_required_tools(monkeypatch)

    assert preflight.collect_preflight_failures(tmp_path) == []
