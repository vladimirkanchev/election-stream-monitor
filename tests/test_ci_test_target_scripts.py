"""Focused tests for CI manifest helpers, path guards, and drift checks.

This file keeps the repo's CI-hardening seams readable in one place:
- manifest-backed target and lane ownership helpers
- CI-owned test-path existence coverage
- protected-lane alignment behavior
- high-signal `changes` filter assumptions in `ci.yml`
"""

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

PROTECTED_ALIGNMENT_GROUPS = (
    "backend_contract",
    "mcp_fastapi_parity",
    "frontend_contract",
)
WEEKLY_LANE_GROUPS = (
    "weekly_slow_media",
    "weekly_api_stream_deep",
    "weekly_lifecycle",
)
LOCAL_ONLY_POLICY_TEST_PATHS = (
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
REFINED_CONTRACT_FILTER_PATHS = (
    "src/stream_loader.py",
    "src/stream_loader_http_hls.py",
    "src/session_runner.py",
    "src/session_runner_progress.py",
    "src/session_service.py",
    "frontend/src/hooks/useMonitoringSession*.tsx",
    "frontend/src/hooks/usePlaybackSource*.tsx",
    "frontend/src/uiErrors.ts",
)
DOCS_CONSISTENCY_NON_MAIN_PR_IF = (
    "github.base_ref != 'main' && (needs.changes.outputs.docs == 'true' || "
    "needs.changes.outputs.workflow == 'true' || "
    "needs.changes.outputs.contract == 'true')"
)
PATH_EXISTENCE_SUMMARY_LABELS = (
    "all ci-owned test paths",
    "inline workflow exceptions",
    "policy-only expectations",
    "local-only policy expectations",
)


def _current_ci_workflow_text() -> str:
    """Return the current workflow text used by focused `changes` assertions."""
    return (ci_target_manifest.REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text()


def _assert_contains_all(text: str, expected_snippets: tuple[str, ...]) -> None:
    """Assert that one text blob contains every expected snippet."""
    for snippet in expected_snippets:
        assert snippet in text


def _path_summaries_by_label() -> dict[str, Any]:
    """Return current existence-guard summaries keyed by their stable labels."""
    return {
        summary.label: summary
        for summary in check_ci_test_paths_exist._path_summaries()
    }


def _patch_clean_doc_alignment(monkeypatch) -> None:
    """Patch the drift checker so tests can focus on workflow/policy scenarios."""
    monkeypatch.setattr(
        check_ci_target_drift,
        "_validate_doc_alignment",
        lambda requirement: [],
    )


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
    assert local_only_policy_paths == LOCAL_ONLY_POLICY_TEST_PATHS
    assert manifest.path_existence_inventory.policy_only_test_paths == policy_paths
    assert manifest.path_existence_boundary.included_path_categories == (
        "manifest target entries",
        "inline workflow test paths",
        "policy-only test paths",
    )
    assert manifest_groups == PROTECTED_ALIGNMENT_GROUPS
    assert set(manifest.path_existence_inventory.workflow_manifest_groups) == {
        *PROTECTED_ALIGNMENT_GROUPS,
        *WEEKLY_LANE_GROUPS,
    }


def test_manifest_lane_ownership_matches_current_ci_split() -> None:
    manifest = ci_target_manifest.load_ci_target_manifest()
    lane_group_map = manifest.lane_group_map()

    assert lane_group_map["contract_boundary"] == PROTECTED_ALIGNMENT_GROUPS
    assert lane_group_map["weekly_slow_real_media"] == WEEKLY_LANE_GROUPS
    assert lane_group_map["fast_synthetic"] == ()
    assert (
        ci_target_manifest.manifest_lane_groups("contract_boundary")
        == PROTECTED_ALIGNMENT_GROUPS
    )
    assert (
        manifest.group_lane_category_name("backend_contract") == "contract_boundary"
    )
    assert (
        manifest.group_lane_category_name("weekly_slow_media")
        == "weekly_slow_real_media"
    )


def test_lane_category_helpers_expose_metadata_and_fail_cleanly() -> None:
    category = ci_target_manifest.ci_lane_category("contract_boundary")

    assert category.name == "contract_boundary"
    assert "reader-backed test-and-build ownership" in category.includes
    assert "weekly-only slow or real-media suites" in category.excludes
    assert (
        ci_target_manifest.manifest_group_lane_category_name("frontend_contract")
        == "contract_boundary"
    )
    assert (
        ci_target_manifest.load_ci_target_manifest().group_lane_category(
            "frontend_contract"
        ).name
        == "contract_boundary"
    )

    try:
        ci_target_manifest.ci_lane_category("unknown_lane")
    except ci_target_manifest.ManifestError as exc:
        assert "Unknown CI lane category" in str(exc)
    else:
        raise AssertionError("Expected ManifestError for unknown lane category")

    try:
        ci_target_manifest.manifest_group_lane_category_name("unknown_group")
    except ci_target_manifest.ManifestError as exc:
        assert "Unknown CI target manifest group" in str(exc)
    else:
        raise AssertionError("Expected ManifestError for unknown manifest group")


def test_ci_owned_test_path_existence_guard_passes_on_current_repo() -> None:
    summaries = _path_summaries_by_label()

    for label in PATH_EXISTENCE_SUMMARY_LABELS:
        assert summaries[label].missing_paths == ()
    assert check_ci_test_paths_exist._policy_inventory_drift_failures() == []


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


def test_ci_workflow_changes_filter_keeps_refined_high_signal_contract_scope() -> None:
    workflow_text = _current_ci_workflow_text()

    _assert_contains_all(
        workflow_text,
        (
            "frontend:",
            "- 'frontend/**'",
            "- '!frontend/README.md'",
            *tuple(f"- '{path}'" for path in REFINED_CONTRACT_FILTER_PATHS),
            DOCS_CONSISTENCY_NON_MAIN_PR_IF,
        ),
    )


def _alignment_contract(
    *,
    protected_groups: tuple[str, ...] = PROTECTED_ALIGNMENT_GROUPS,
    doc_requirements: tuple[Any, ...] = (),
) -> Any:
    """Build one narrow protected-lane alignment contract for drift tests."""
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
    """Patch the drift checker to one controlled protected-lane scenario."""
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
    _patch_clean_doc_alignment(monkeypatch)

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
    _patch_clean_doc_alignment(monkeypatch)

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
    _patch_clean_doc_alignment(monkeypatch)

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
