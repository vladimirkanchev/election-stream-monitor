"""Tests for the manual api_stream local validation helper."""

from __future__ import annotations

import importlib.util
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "api_stream_local_validation.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("api_stream_local_validation", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_manual_trial_expectations_include_standardized_validation_sections() -> None:
    """Manual trial output should always include source, status, logs, and cleanup expectations."""
    module = _load_module()
    expectations = module.load_expectations()
    case = expectations["cases"][0]

    trial = module.build_manual_trial_expectations(
        case,
        live_url="http://127.0.0.1:8765/index.m3u8",
    )

    assert trial["source_input"] == "http://127.0.0.1:8765/index.m3u8"
    assert trial["expected_status"] == case["expected_final_status"]
    assert trial["expected_logs"] == case["expected_log_snippets"]
    assert trial["expected_cleanup"] == case["expected_cleanup_checks"]
