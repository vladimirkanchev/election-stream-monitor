"""Tests for CI target-manifest helpers and the path-existence guard."""

from __future__ import annotations

import importlib
from pathlib import Path
import sys


SCRIPTS_DIR = Path(__file__).resolve().parent.parent / ".github" / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

check_ci_test_paths_exist = importlib.import_module("check_ci_test_paths_exist")
check_main_pr_consistency = importlib.import_module("check_main_pr_consistency")
ci_target_manifest = importlib.import_module("ci_target_manifest")


def test_ci_owned_test_paths_keep_inline_and_policy_inventory() -> None:
    manifest = ci_target_manifest.load_ci_target_manifest()
    inventory_paths = ci_target_manifest.ci_owned_test_paths()
    inline_paths = ci_target_manifest.workflow_inline_ci_test_paths()
    policy_paths = check_main_pr_consistency.policy_only_test_paths()
    local_only_policy_paths = check_main_pr_consistency.local_only_policy_test_paths()

    assert inventory_paths
    assert len(inventory_paths) == len(set(inventory_paths))
    assert "tests/test_e2e_local_session.py" in inventory_paths
    assert inline_paths == ("tests/test_e2e_local_session.py",)
    assert (
        "frontend/src/bridge/contract.session-snapshot.shape.test.ts"
        in inventory_paths
    )
    assert "frontend/electron/playbackSourcePolicy.test.mjs" in policy_paths
    assert local_only_policy_paths == (
        "frontend/electron/playbackSourcePolicy.test.mjs",
        "frontend/electron/localMediaRequestPolicy.test.mjs",
        "frontend/electron/bridgeResponses.test.mjs",
        "frontend/electron/fastApiFallback.test.mjs",
        "frontend/electron/fastApiRuntimePolicy.test.mjs",
        "frontend/electron/fastApiClient.test.mjs",
        "frontend/electron/fastApiProcessManager.test.mjs",
        "frontend/electron/fastApiStartupOrchestrator.test.mjs",
        "frontend/electron/localMediaResponses.test.mjs",
    )
    assert manifest.path_existence_inventory.policy_only_test_paths == policy_paths
    assert set(manifest.path_existence_inventory.workflow_manifest_groups) == {
        "backend_contract",
        "mcp_fastapi_parity",
        "frontend_contract",
        "weekly_slow_media",
        "weekly_api_stream_deep",
        "weekly_lifecycle",
    }


def test_ci_owned_test_path_existence_guard_passes_on_current_repo() -> None:
    summaries = {
        summary.label: summary
        for summary in check_ci_test_paths_exist._path_summaries()
    }

    assert summaries["all ci-owned test paths"].missing_paths == ()
    assert summaries["inline workflow exceptions"].missing_paths == ()
    assert check_ci_test_paths_exist._policy_inventory_drift_failures() == []
    assert summaries["policy-only expectations"].missing_paths == ()
    assert summaries["local-only policy expectations"].missing_paths == ()
