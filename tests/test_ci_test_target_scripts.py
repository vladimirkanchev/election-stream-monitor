"""Tests for CI target-manifest helpers and CI structural guards."""

from __future__ import annotations

import importlib
from pathlib import Path
import sys
from typing import Any


SCRIPTS_DIR = Path(__file__).resolve().parent.parent / ".github" / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

check_ci_test_paths_exist = importlib.import_module("check_ci_test_paths_exist")
check_ci_target_drift = importlib.import_module("check_ci_target_drift")
check_main_pr_consistency = importlib.import_module("check_main_pr_consistency")
ci_target_manifest = importlib.import_module("ci_target_manifest")


def test_ci_owned_test_paths_keep_inline_and_policy_inventory() -> None:
    manifest = ci_target_manifest.load_ci_target_manifest()
    inventory_paths = ci_target_manifest.ci_owned_test_paths()
    inline_paths = ci_target_manifest.workflow_inline_ci_test_paths()
    manifest_groups = check_main_pr_consistency.manifest_policy_groups()
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
    assert manifest_groups == (
        "backend_contract",
        "mcp_fastapi_parity",
        "frontend_contract",
    )
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


def test_workflow_reader_groups_handle_multiline_shell_invocations(
    tmp_path: Path,
) -> None:
    workflow_text = """
    run: |
      PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest -q \\
        $(python3 .github/scripts/read_ci_test_targets.py backend_contract --separator space) \\
        $(python .github/scripts/read_ci_test_targets.py mcp_fastapi_parity --separator space)
    run: npm run test -- $(python3 ../.github/scripts/read_ci_test_targets.py frontend_contract --separator space --strip-prefix frontend/)
    """
    workflow_path = tmp_path / "workflow-snippet.yml"
    workflow_path.write_text(workflow_text)
    groups = ci_target_manifest.workflow_reader_groups(workflow_path)

    assert groups == (
        "backend_contract",
        "mcp_fastapi_parity",
        "frontend_contract",
    )


def _alignment_contract(
    *,
    protected_groups: tuple[str, ...] = (
        "backend_contract",
        "mcp_fastapi_parity",
        "frontend_contract",
    ),
    doc_requirements: tuple[Any, ...] = (),
) -> Any:
    """Build one narrow protected-lane alignment contract for focused tests."""
    return ci_target_manifest.AlignmentContract(
        protected_workflow_groups=protected_groups,
        doc_requirements=doc_requirements,
    )


def _patch_drift_inputs(
    monkeypatch,
    contract: Any,
    *,
    workflow_groups: set[str] | None = None,
    policy_groups: set[str] | None = None,
) -> set[str]:
    """Patch the drift checker to one controlled alignment scenario."""
    expected_groups = set(contract.protected_workflow_groups)
    monkeypatch.setattr(check_ci_target_drift, "alignment_contract", lambda: contract)
    monkeypatch.setattr(
        check_ci_target_drift,
        "_consistency_workflow_groups",
        lambda: expected_groups if workflow_groups is None else workflow_groups,
    )
    monkeypatch.setattr(
        check_ci_target_drift,
        "_consistency_groups",
        lambda: expected_groups if policy_groups is None else policy_groups,
    )
    return expected_groups


def test_ci_target_drift_check_passes_for_matching_alignment(
    monkeypatch,
    capsys,
) -> None:
    contract = _alignment_contract()
    _patch_drift_inputs(monkeypatch, contract)
    monkeypatch.setattr(
        check_ci_target_drift,
        "_validate_doc_alignment",
        lambda requirement: [],
    )

    assert check_ci_target_drift.main() == 0
    captured = capsys.readouterr()
    assert captured.err == ""
    assert captured.out.strip() == "ci target drift check passed"


def test_ci_target_drift_check_reports_workflow_alignment_mismatch(
    monkeypatch,
    capsys,
) -> None:
    contract = _alignment_contract()
    workflow_groups = {"backend_contract", "frontend_contract"}

    _patch_drift_inputs(
        monkeypatch,
        contract,
        workflow_groups=workflow_groups,
        policy_groups=workflow_groups,
    )
    monkeypatch.setattr(
        check_ci_target_drift,
        "_validate_doc_alignment",
        lambda requirement: [],
    )

    assert check_ci_target_drift.main() == 1
    captured = capsys.readouterr()
    assert "Main workflow contract-lane usage drifted" in captured.err


def test_ci_target_drift_check_reports_policy_alignment_mismatch(
    monkeypatch,
    capsys,
) -> None:
    contract = _alignment_contract()
    policy_groups = {"backend_contract", "mcp_fastapi_parity"}

    _patch_drift_inputs(
        monkeypatch,
        contract,
        policy_groups=policy_groups,
    )
    monkeypatch.setattr(
        check_ci_target_drift,
        "_validate_doc_alignment",
        lambda requirement: [],
    )

    assert check_ci_target_drift.main() == 1
    captured = capsys.readouterr()
    assert "Consistency-script manifest-group usage drifted" in captured.err


def test_ci_target_drift_check_reports_doc_alignment_mismatch(
    monkeypatch,
    capsys,
) -> None:
    contract = _alignment_contract(
        doc_requirements=(
            ci_target_manifest.DocAlignmentRequirement(
                path=ci_target_manifest.REPO_ROOT / "docs" / "README.md",
                required_tokens=("missing-ci-ownership-token",),
            ),
        ),
    )
    _patch_drift_inputs(monkeypatch, contract)

    assert check_ci_target_drift.main() == 1
    captured = capsys.readouterr()
    assert "missing manifest ownership references" in captured.err
