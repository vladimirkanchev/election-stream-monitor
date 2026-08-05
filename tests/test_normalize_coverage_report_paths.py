"""Focused tests for sanitizing coverage artifact path metadata."""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / ".github" / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

coverage_paths = importlib.import_module("normalize_coverage_report_paths")


def test_normalizers_make_coverage_report_paths_relative(tmp_path: Path) -> None:
    """Coverage artifacts retain source context without runner paths."""
    repository_root = tmp_path / "repository"
    source_path = repository_root / "frontend" / "src" / "App.tsx"
    source_path.parent.mkdir(parents=True)
    source_path.write_text("export {}\n")

    json_report = tmp_path / "coverage-summary.json"
    json_report.write_text(
        json.dumps({"total": {}, str(source_path): {"lines": {"pct": 100}}})
    )
    lcov_report = tmp_path / "lcov.info"
    lcov_report.write_text(f"TN:\nSF:{source_path}\nDA:1,1\nend_of_record\n")
    xml_report = tmp_path / "coverage.xml"
    xml_report.write_text(
        "<coverage><sources><source>"
        f"{repository_root / 'src'}"
        "</source></sources><packages><package><classes>"
        f"<class filename=\"{source_path}\" />"
        "</classes></package></packages></coverage>"
    )

    coverage_paths.normalize_json_summary(json_report, repository_root)
    coverage_paths.normalize_lcov(lcov_report, repository_root)
    coverage_paths.normalize_cobertura(xml_report, repository_root)

    assert set(json.loads(json_report.read_text())) == {"total", "frontend/src/App.tsx"}
    assert "SF:frontend/src/App.tsx" in lcov_report.read_text()
    xml_text = xml_report.read_text()
    assert "<source>src</source>" in xml_text
    assert 'filename="frontend/src/App.tsx"' in xml_text
    assert str(repository_root) not in xml_text


def test_normalizers_reject_paths_outside_the_repository(tmp_path: Path) -> None:
    """An external report path must not be uploaded as coverage evidence."""
    with pytest.raises(coverage_paths.CoveragePathError, match="outside"):
        coverage_paths.relative_path("/tmp/other-project/src/module.py", tmp_path)
    with pytest.raises(coverage_paths.CoveragePathError, match="escapes"):
        coverage_paths.relative_path("../other-project/src/module.py", tmp_path)
