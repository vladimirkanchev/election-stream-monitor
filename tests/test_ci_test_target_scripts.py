"""Regression coverage for CI target ownership and helper scripts.

The helper layer owns manifest-backed target groups, focused detector and
weekly-lane registration, CI-owned path checks, and protected-lane drift.
"""

from __future__ import annotations

import importlib
import subprocess
import sys
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / ".github" / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

check_ci_test_paths_exist = importlib.import_module("check_ci_test_paths_exist")
check_ci_target_drift = importlib.import_module("check_ci_target_drift")
check_main_pr_consistency = importlib.import_module("check_main_pr_consistency")
check_split_suite_registration = importlib.import_module(
    "check_split_suite_registration"
)
ci_target_manifest = importlib.import_module("ci_target_manifest")
read_ci_test_targets = importlib.import_module("read_ci_test_targets")
validate_ci_test_targets = importlib.import_module("validate_ci_test_targets")

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
FRONTEND_CONTRACT_TEST_PATHS = (
    "frontend/src/bridge/contract.success.test.ts",
    "frontend/src/bridge/contract.errors.test.ts",
    "frontend/src/bridge/contract.session-snapshot.shape.test.ts",
    "frontend/src/bridge/contract.session-snapshot.malformed.test.ts",
    "frontend/src/bridge/contract.session-snapshot.collections.test.ts",
    "frontend/src/bridge/transport.test.ts",
    "frontend/src/uiErrors.test.ts",
)
FRONTEND_POLICY_ONLY_TEST_PATHS = (
    "frontend/src/hooks/useMonitoringSession.lifecycle.test.tsx",
    "frontend/src/hooks/useMonitoringSession.apiStream.test.tsx",
    "frontend/src/hooks/usePlaybackSource.test.tsx",
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
CI_MAINTAINER_GUIDE_REGRESSION_TOKENS = (
    "tests/test_ci_workflow.py",
    "tests/test_ci_test_target_scripts.py",
    "owns the protected `ci.yml` contract through one narrow workflow reader",
    "owns manifest/helper/ownership drift checks around that workflow",
    "exact `main-gate` direct dependencies",
    "protected frontend `npm run test` and `npm run build` ownership",
    "forced-on behavior for protected `main` PR jobs and work steps",
    "advisory-job classification for standalone `frontend-lint` and",
    "`backend-pyright`",
)
FRONTEND_CONTRACT_WORKFLOW_TOKENS = (
    "mapfile -t frontend_contract_targets",
    "python3 ../.github/scripts/read_ci_test_targets.py frontend_contract",
    "--strip-prefix frontend/",
    'npm run test -- "${frontend_contract_targets[@]}"',
)
REGISTERED_SHARED_MANIFEST_SPLIT_SUITE = "tests/test_api_boundary_contracts.py"
UNREGISTERED_GUARDED_SPLIT_SUITE = "tests/test_api_boundary_new_split.py"
REGISTERED_LOCAL_ONLY_SPLIT_SUITE = "frontend/electron/playbackSourcePolicy.test.mjs"
REGISTERED_FOCUSED_DETECTOR_SPLIT_SUITE = "tests/test_detector_lab_runner.py"
UNREGISTERED_FOCUSED_DETECTOR_SPLIT_SUITE = "tests/test_detector_lab_runner_new.py"
NON_GUARDED_NEW_TEST_FILE = "tests/test_ci_test_target_scripts.py"
GUARDED_OWNER_SEAM_EXEMPLARS = (
    "tests/test_api_boundary_contracts.py",
    "tests/test_stream_loader_contracts.py",
    "frontend/src/bridge/contract.errors.test.ts",
    "frontend/electron/playbackSourcePolicy.test.mjs",
    "tests/test_detector_lab_runner.py",
)
PATH_EXISTENCE_SUMMARY_LABELS = (
    "all ci-owned test paths",
    "inline workflow exceptions",
    "policy-only expectations",
    "local-only policy expectations",
)
SHARED_OR_POLICY_SURFACES = ("shared_manifest", "policy_owned")
LOCAL_ONLY_POLICY_SURFACES = ("local_only_policy",)
FOCUSED_DETECTOR_RECIPE_SURFACES = ("focused_detector_recipe",)


def _current_ci_workflow_text() -> str:
    """Return the current CI workflow text used by focused ownership checks."""
    return (ci_target_manifest.REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text()


def _ci_maintainer_guide_text() -> str:
    """Return the current CI maintainer guide text for focused doc checks."""
    return (ci_target_manifest.REPO_ROOT / "docs" / "ci-maintainer-guide.md").read_text()


def _assert_contains_all(text: str, expected_snippets: tuple[str, ...]) -> None:
    """Assert that one text blob contains every expected snippet."""
    for snippet in expected_snippets:
        assert snippet in text


def _run_cli_main(
    module: Any,
    monkeypatch,
    capsys,
    argv: list[str],
) -> tuple[int, str, str]:
    """Run one script-style `main()` entrypoint with patched argv."""
    monkeypatch.setattr(module.sys, "argv", argv)
    exit_code = module.main()
    captured = capsys.readouterr()
    return exit_code, captured.out, captured.err


def _path_summaries_by_label() -> dict[str, Any]:
    """Return current existence-guard summaries keyed by stable labels."""
    return {
        summary.label: summary
        for summary in check_ci_test_paths_exist._path_summaries()
    }


def _frontend_contract_targets() -> tuple[str, ...]:
    """Return the current shared frontend contract-manifest targets."""
    return ci_target_manifest.manifest_group_targets("frontend_contract")


def _frontend_policy_only_tests() -> tuple[str, ...]:
    """Return the current narrower frontend policy-only test slice."""
    return check_main_pr_consistency.FRONTEND_BRIDGE_POLICY_ONLY_TESTS


def _live_ci_target_manifest() -> Any:
    """Return the current canonical CI target manifest."""
    return ci_target_manifest.load_ci_target_manifest()


def _patch_manifest_loader(monkeypatch, manifest: Any) -> None:
    """Patch manifest-validator loads to one controlled manifest instance."""
    monkeypatch.setattr(
        validate_ci_test_targets,
        "load_ci_target_manifest",
        lambda: manifest,
    )


def _patch_main_pr_changed_files(monkeypatch, changed_files: list[str]) -> None:
    """Patch main-PR consistency checks to one controlled changed-file batch."""
    monkeypatch.setattr(
        check_main_pr_consistency,
        "_changed_files",
        lambda diff_range: changed_files,
    )


def _patch_split_suite_args(
    monkeypatch,
    *,
    diff_range: str | None,
    changed_files: list[str],
) -> None:
    """Patch split-suite CLI args to one controlled invocation."""
    monkeypatch.setattr(
        check_split_suite_registration,
        "_parse_args",
        lambda: SimpleNamespace(
            diff_range=diff_range,
            changed_files=changed_files,
        ),
    )


def _manifest_validation_failures(monkeypatch, manifest: Any) -> list[str]:
    """Return manifest validation failures for one patched manifest."""
    _patch_manifest_loader(monkeypatch, manifest)
    return validate_ci_test_targets._validate_manifest()


def _patch_clean_doc_alignment(monkeypatch) -> None:
    """Patch doc checks away so drift tests can focus on group alignment."""
    monkeypatch.setattr(
        check_ci_target_drift,
        "_validate_doc_alignment",
        lambda requirement: [],
    )


def _registration_status_for(relative_path: str) -> Any:
    """Return one split-suite registration status for one changed file."""
    statuses = _registration_statuses_for((relative_path,))
    assert len(statuses) == 1
    return statuses[0]


def _registration_failure_for(relative_path: str) -> str:
    """Return the single failure message for one unregistered guarded file."""
    failures = check_split_suite_registration.registration_failures((relative_path,))
    assert len(failures) == 1
    return failures[0]


def _registration_statuses_for(changed_files: tuple[str, ...]) -> tuple[Any, ...]:
    """Return guarded split-suite statuses for one changed-file batch."""
    return check_split_suite_registration.collect_registration_statuses(changed_files)


def _assert_registration_passes(
    relative_path: str,
    *,
    accepted_surfaces: tuple[str, ...],
) -> None:
    """Assert that one guarded file registers cleanly through the live owner seams."""
    status = _registration_status_for(relative_path)

    assert status.relative_path == relative_path
    assert status.ok is True
    assert status.accepted_surfaces() == accepted_surfaces
    assert check_split_suite_registration.registration_failures((relative_path,)) == []


def test_ci_owned_test_paths_keep_inline_and_policy_inventory() -> None:
    """The live manifest inventory should keep the expected path split."""
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
    assert (
        "frontend/src/bridge/contract.session-snapshot.shape.test.ts"
        not in policy_paths
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
    """The live manifest should keep the current lane-to-group ownership split."""
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
    """Lane-category helpers should expose live metadata and readable errors."""
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
    """The live repo should satisfy the CI-owned path existence guard."""
    summaries = _path_summaries_by_label()

    for label in PATH_EXISTENCE_SUMMARY_LABELS:
        assert summaries[label].missing_paths == ()
    assert check_ci_test_paths_exist._policy_inventory_drift_failures() == []


def test_ci_owned_test_path_existence_guard_reports_policy_inventory_drift(
    monkeypatch,
) -> None:
    """Policy inventory drift should be reported by the path existence guard."""
    manifest = ci_target_manifest.load_ci_target_manifest()
    manifest_policy_paths = manifest.path_existence_inventory.policy_only_test_paths
    drifted_policy_paths = (
        *manifest_policy_paths[:-1],
        "frontend/src/hooks/syntheticDrift.test.tsx",
    )

    monkeypatch.setattr(
        check_ci_test_paths_exist,
        "policy_only_test_paths",
        lambda: drifted_policy_paths,
    )

    failures = check_ci_test_paths_exist._policy_inventory_drift_failures()

    assert len(failures) == 1
    assert "Manifest policy-only path inventory drifted" in failures[0]
    assert "syntheticDrift.test.tsx" in failures[0]


def test_workflow_reader_groups_handle_multiline_shell_invocations(
    tmp_path: Path,
) -> None:
    """Workflow reader discovery should handle multiline shell commands."""
    workflow_text = """
    run: |
      mapfile -t backend_contract_targets < <(
        python3 .github/scripts/read_ci_test_targets.py backend_contract
      )
      mapfile -t mcp_fastapi_parity_targets < <(
        python .github/scripts/read_ci_test_targets.py mcp_fastapi_parity
      )
      PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest -q \\
        "${backend_contract_targets[@]}" \\
        "${mcp_fastapi_parity_targets[@]}"
    run: |
      mapfile -t frontend_contract_targets < <(
        python3 ../.github/scripts/read_ci_test_targets.py frontend_contract --strip-prefix frontend/
      )
      npm run test -- "${frontend_contract_targets[@]}"
    """
    workflow_path = tmp_path / "workflow-snippet.yml"
    workflow_path.write_text(workflow_text)
    groups = ci_target_manifest.workflow_reader_groups(workflow_path)

    assert groups == (
        "backend_contract",
        "mcp_fastapi_parity",
        "frontend_contract",
    )


def test_workflow_reader_groups_ignore_near_miss_reader_invocations(
    tmp_path: Path,
) -> None:
    """Workflow reader discovery should ignore near-miss command shapes."""
    workflow_text = """
    run: |
      python3 .github/scripts/read_ci_test_targets.sh backend_contract
      node .github/scripts/read_ci_test_targets.py frontend_contract
      python .github/scripts/read_ci_test_targets.py mcp_fastapi_parity --separator space
    """
    workflow_path = tmp_path / "workflow-snippet.yml"
    workflow_path.write_text(workflow_text)

    assert ci_target_manifest.workflow_reader_groups(workflow_path) == (
        "mcp_fastapi_parity",
    )


def test_read_ci_test_targets_cli_supports_space_separator_and_prefix_strip(
    monkeypatch,
    capsys,
) -> None:
    """The target-reader CLI should support space output and prefix stripping."""
    exit_code, out, err = _run_cli_main(
        read_ci_test_targets,
        monkeypatch,
        capsys,
        [
            "read_ci_test_targets.py",
            "frontend_contract",
            "--separator",
            "space",
            "--strip-prefix",
            "frontend/",
        ],
    )
    assert exit_code == 0
    assert err == ""
    assert out.strip().split() == [
        path.removeprefix("frontend/")
        for path in FRONTEND_CONTRACT_TEST_PATHS
    ]


def test_read_ci_test_targets_cli_defaults_to_newline_output(
    monkeypatch,
    capsys,
) -> None:
    """The target-reader CLI should default to newline-separated output."""
    exit_code, out, err = _run_cli_main(
        read_ci_test_targets,
        monkeypatch,
        capsys,
        ["read_ci_test_targets.py", "frontend_contract"],
    )
    assert exit_code == 0
    assert err == ""
    assert out.strip().splitlines() == list(FRONTEND_CONTRACT_TEST_PATHS)


def test_read_ci_test_targets_cli_rejects_deprecated_subgroups(
    monkeypatch,
    capsys,
) -> None:
    """The target-reader CLI should reject the retired subgroup option."""
    exit_code, out, err = _run_cli_main(
        read_ci_test_targets,
        monkeypatch,
        capsys,
        [
            "read_ci_test_targets.py",
            "frontend_contract",
            "--subgroup",
            "legacy",
        ],
    )
    assert exit_code == 1
    assert out == ""
    assert "Nested subgroups are no longer supported" in err


def test_read_ci_test_targets_cli_reports_unknown_groups(
    monkeypatch,
    capsys,
) -> None:
    """The target-reader CLI should report unknown manifest groups clearly."""
    exit_code, out, err = _run_cli_main(
        read_ci_test_targets,
        monkeypatch,
        capsys,
        ["read_ci_test_targets.py", "unknown_group"],
    )
    assert exit_code == 1
    assert out == ""
    assert "Unknown CI target manifest group: unknown_group" in err


def test_frontend_contract_manifest_group_matches_current_shared_lane() -> None:
    """The shared frontend contract lane should keep its current manifest targets."""
    assert _frontend_contract_targets() == FRONTEND_CONTRACT_TEST_PATHS


def test_frontend_bridge_policy_only_tests_stay_narrower_than_shared_lane() -> None:
    """Frontend policy-only tests should stay limited to the hook-level slice."""
    assert _frontend_policy_only_tests() == FRONTEND_POLICY_ONLY_TEST_PATHS
    assert set(_frontend_contract_targets()).isdisjoint(_frontend_policy_only_tests())


def test_ci_workflow_frontend_contract_reader_command_stays_aligned() -> None:
    """The live workflow should pass manifest targets without shell splitting."""
    workflow_text = _current_ci_workflow_text()

    assert all(token in workflow_text for token in FRONTEND_CONTRACT_WORKFLOW_TOKENS)


def test_ci_workflow_changes_filter_keeps_refined_high_signal_contract_scope() -> None:
    """The live workflow should keep the refined high-signal contract filter."""
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


def test_ci_target_manifest_validator_reports_duplicate_target_paths(
    monkeypatch,
) -> None:
    """Duplicate manifest target paths should be reported."""
    manifest = _live_ci_target_manifest()
    duplicated_path = manifest.targets["backend_contract"][0]
    mutated_targets = dict(manifest.targets)
    mutated_targets["frontend_contract"] = (
        *mutated_targets["frontend_contract"],
        duplicated_path,
    )
    mutated = replace(manifest, targets=mutated_targets)

    failures = _manifest_validation_failures(monkeypatch, mutated)

    assert (
        f"Manifest target path '{duplicated_path}' is duplicated across groups."
        in failures
    )


def test_ci_target_manifest_validator_reports_lane_ownership_drift(
    monkeypatch,
) -> None:
    """Lane-category drift should be reported by the manifest validator."""
    manifest = _live_ci_target_manifest()
    mutated_group_lane_categories = dict(manifest.group_lane_categories)
    mutated_group_lane_categories["frontend_contract"] = "weekly_slow_real_media"
    mutated = replace(
        manifest,
        group_lane_categories=mutated_group_lane_categories,
    )

    failures = _manifest_validation_failures(monkeypatch, mutated)

    assert (
        "Manifest contract_boundary lane groups drifted from the protected PR contract groups."
        in failures
    )


def test_ci_target_manifest_validator_reports_retired_target_paths(
    monkeypatch,
) -> None:
    """Retired target paths should still be rejected by the validator."""
    manifest = _live_ci_target_manifest()
    retired_path = validate_ci_test_targets.RETIRED_TARGET_PATHS[0]
    mutated_targets = dict(manifest.targets)
    mutated_targets["backend_contract"] = (
        *mutated_targets["backend_contract"],
        retired_path,
    )
    mutated = replace(manifest, targets=mutated_targets)

    failures = _manifest_validation_failures(monkeypatch, mutated)

    assert f"Manifest still references stale retired path '{retired_path}'." in failures


def test_ci_target_manifest_validator_reports_invalid_guarded_area_metadata(
    monkeypatch,
) -> None:
    """Invalid guarded-area metadata should be reported by the validator."""
    manifest = _live_ci_target_manifest()
    area_name = "frontend_contract_and_hook_boundary"
    mutated_areas = dict(manifest.guarded_split_suite_areas)
    mutated_areas[area_name] = replace(
        mutated_areas[area_name],
        patterns=(),
    )
    mutated = replace(manifest, guarded_split_suite_areas=mutated_areas)

    failures = _manifest_validation_failures(monkeypatch, mutated)

    assert (
        f"Guarded split-suite area '{area_name}' must define at least one pattern."
        in failures
    )


def test_ci_target_manifest_validator_main_reports_failure_output(
    monkeypatch,
    capsys,
) -> None:
    """The manifest validator CLI should print readable failure output."""
    manifest = _live_ci_target_manifest()
    duplicated_path = manifest.targets["backend_contract"][0]
    mutated_targets = dict(manifest.targets)
    mutated_targets["frontend_contract"] = (
        *mutated_targets["frontend_contract"],
        duplicated_path,
    )
    mutated = replace(manifest, targets=mutated_targets)

    _patch_manifest_loader(monkeypatch, mutated)

    exit_code, out, err = _run_cli_main(
        validate_ci_test_targets,
        monkeypatch,
        capsys,
        ["validate_ci_test_targets.py"],
    )
    assert exit_code == 1
    assert out == ""
    assert "ci_test_targets manifest validation failed:" in err
    assert duplicated_path in err


def test_main_pr_consistency_reports_expected_policy_failures(
    monkeypatch,
    capsys,
) -> None:
    """The main-PR consistency CLI should report the expected failure bundle."""
    _patch_main_pr_changed_files(
        monkeypatch,
        [
            ".github/workflows/ci.yml",
            "src/session_io.py",
        ],
    )
    exit_code, out, err = _run_cli_main(
        check_main_pr_consistency,
        monkeypatch,
        capsys,
        ["check_main_pr_consistency.py", "origin/main...HEAD"],
    )
    assert exit_code == 1
    assert out == ""
    assert "main-pr-consistency check failed:" in err
    assert (
        "Workflow or package CI entrypoints changed without any docs update"
        in err
    )
    assert (
        "Contract-sensitive code changed without updating docs/contracts.md."
        in err
    )
    assert "Backend contract changed without a matching test update" in err
    assert "Backend contract changed without a matching docs update" in err
    assert "changed files:" in err
    assert "src/session_io.py" in err


def test_main_pr_consistency_reports_usage_error_without_diff_range(
    monkeypatch,
    capsys,
) -> None:
    """The main-PR consistency CLI should reject missing diff ranges."""
    exit_code, out, err = _run_cli_main(
        check_main_pr_consistency,
        monkeypatch,
        capsys,
        ["check_main_pr_consistency.py"],
    )
    assert exit_code == 2
    assert out == ""
    assert "usage: check_main_pr_consistency.py <diff-range>" in err


def test_main_pr_consistency_reports_changed_files_subprocess_failure(
    monkeypatch,
    capsys,
) -> None:
    """Subprocess failures should still surface out of the consistency CLI."""
    monkeypatch.setattr(
        check_main_pr_consistency,
        "_changed_files",
        lambda diff_range: (_ for _ in ()).throw(
            subprocess.CalledProcessError(
                1,
                ["git", "diff", "--name-only", diff_range],
            )
        ),
    )

    with pytest.raises(subprocess.CalledProcessError):
        _run_cli_main(
            check_main_pr_consistency,
            monkeypatch,
            capsys,
            ["check_main_pr_consistency.py", "origin/main...HEAD"],
        )


def test_main_pr_consistency_passes_with_matching_tests_and_docs(
    monkeypatch,
    capsys,
) -> None:
    """Matching tests and docs should let the consistency CLI pass."""
    _patch_main_pr_changed_files(
        monkeypatch,
        [
            "frontend/src/hooks/usePlaybackSource.tsx",
            "frontend/src/hooks/usePlaybackSource.test.tsx",
            "docs/contracts.md",
        ],
    )
    exit_code, out, err = _run_cli_main(
        check_main_pr_consistency,
        monkeypatch,
        capsys,
        ["check_main_pr_consistency.py", "origin/main...HEAD"],
    )
    assert exit_code == 0
    assert err == ""
    assert out.strip() == "main-pr-consistency check passed"


def test_main_pr_consistency_reports_session_store_policy_failures(
    monkeypatch,
    capsys,
) -> None:
    """Session-store seam changes should require nearby tests and owning docs."""
    _patch_main_pr_changed_files(
        monkeypatch,
        [
            "src/session_store_runtime.py",
        ],
    )
    exit_code, out, err = _run_cli_main(
        check_main_pr_consistency,
        monkeypatch,
        capsys,
        ["check_main_pr_consistency.py", "origin/main...HEAD"],
    )

    assert exit_code == 1
    assert out == ""
    assert "Backend contract changed without a matching test update" in err
    assert "tests/test_session_store_runtime.py" in err
    assert "Backend contract changed without a matching docs update" in err
    assert "docs/session-persistence-audit.md" in err


def test_main_pr_consistency_passes_for_session_store_change_with_matching_tests_and_docs(
    monkeypatch,
    capsys,
) -> None:
    """Session-store seam changes should pass when paired ownership moves together."""
    _patch_main_pr_changed_files(
        monkeypatch,
        [
            "src/session_store_runtime.py",
            "tests/test_session_store_runtime.py",
            "docs/contracts.md",
            "docs/session-persistence-audit.md",
        ],
    )
    exit_code, out, err = _run_cli_main(
        check_main_pr_consistency,
        monkeypatch,
        capsys,
        ["check_main_pr_consistency.py", "origin/main...HEAD"],
    )

    assert exit_code == 0
    assert err == ""
    assert out.strip() == "main-pr-consistency check passed"


def test_split_suite_registration_prefers_explicit_changed_files_over_diff_range(
    monkeypatch,
    capsys,
) -> None:
    """Explicit changed-file arguments should win over diff-range discovery."""
    _patch_split_suite_args(
        monkeypatch,
        diff_range="origin/main...HEAD",
        changed_files=[REGISTERED_SHARED_MANIFEST_SPLIT_SUITE],
    )
    monkeypatch.setattr(
        check_split_suite_registration,
        "_added_or_renamed_files",
        lambda diff_range: (_ for _ in ()).throw(
            AssertionError(
                "_added_or_renamed_files should not run when --changed-file is present"
            )
        ),
    )

    exit_code, out, err = _run_cli_main(
        check_split_suite_registration,
        monkeypatch,
        capsys,
        ["check_split_suite_registration.py"],
    )
    assert exit_code == 0
    assert err == ""
    assert "split-suite registration check passed" in out
    assert "guarded files=1" in out


def test_split_suite_registration_collects_added_and_renamed_destinations(
    monkeypatch,
) -> None:
    """Rename destinations need the same registration review as added files."""
    monkeypatch.setattr(
        check_split_suite_registration.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            stdout=(
                "A\ttests/test_detector_lab_runner_new.py\n"
                "R100\ttests/test_detector_lab_runner.py\t"
                "tests/test_detector_lab_runner_moved.py\n"
            )
        ),
    )

    assert check_split_suite_registration._added_or_renamed_files(
        "origin/main...HEAD"
    ) == (
        "tests/test_detector_lab_runner_new.py",
        "tests/test_detector_lab_runner_moved.py",
    )


def test_split_suite_registration_main_reports_missing_cli_inputs(
    monkeypatch,
    capsys,
) -> None:
    """The split-suite CLI should reject empty invocation inputs."""
    _patch_split_suite_args(monkeypatch, diff_range=None, changed_files=[])

    exit_code, out, err = _run_cli_main(
        check_split_suite_registration,
        monkeypatch,
        capsys,
        ["check_split_suite_registration.py"],
    )
    assert exit_code == 1
    assert out == ""
    assert "Provide either <diff-range> or at least one --changed-file value." in err


def test_split_suite_registration_main_reports_subprocess_failures(
    monkeypatch,
    capsys,
) -> None:
    """The split-suite CLI should print subprocess failures clearly."""
    _patch_split_suite_args(
        monkeypatch,
        diff_range="origin/main...HEAD",
        changed_files=[],
    )
    monkeypatch.setattr(
        check_split_suite_registration,
        "_added_or_renamed_files",
        lambda diff_range: (_ for _ in ()).throw(
            subprocess.CalledProcessError(
                1,
                ["git", "diff"],
                stderr="synthetic git failure",
            )
        ),
    )

    exit_code, out, err = _run_cli_main(
        check_split_suite_registration,
        monkeypatch,
        capsys,
        ["check_split_suite_registration.py"],
    )
    assert exit_code == 1
    assert out == ""
    assert "Command '['git', 'diff']' returned non-zero exit status 1." in err


def test_split_suite_registration_main_reports_manifest_failures(
    monkeypatch,
    capsys,
) -> None:
    """The split-suite CLI should print manifest failures clearly."""
    _patch_split_suite_args(
        monkeypatch,
        diff_range=None,
        changed_files=[REGISTERED_SHARED_MANIFEST_SPLIT_SUITE],
    )
    monkeypatch.setattr(
        check_split_suite_registration,
        "collect_registration_statuses",
        lambda changed_files: (_ for _ in ()).throw(
            ci_target_manifest.ManifestError("synthetic manifest failure")
        ),
    )

    exit_code, out, err = _run_cli_main(
        check_split_suite_registration,
        monkeypatch,
        capsys,
        ["check_split_suite_registration.py"],
    )
    assert exit_code == 1
    assert out == ""
    assert "synthetic manifest failure" in err


def test_ci_maintainer_guide_keeps_workflow_contract_regression_note() -> None:
    """The maintainer guide should keep the focused workflow regression note honest."""
    _assert_contains_all(
        _ci_maintainer_guide_text(),
        CI_MAINTAINER_GUIDE_REGRESSION_TOKENS,
    )


def test_split_suite_registration_accepts_registered_guarded_shared_manifest_file() -> None:
    """Shared-manifest guarded files should still pass the registration guard."""
    _assert_registration_passes(
        REGISTERED_SHARED_MANIFEST_SPLIT_SUITE,
        accepted_surfaces=SHARED_OR_POLICY_SURFACES,
    )
    status = _registration_status_for(REGISTERED_SHARED_MANIFEST_SPLIT_SUITE)

    assert status.is_registered("shared_manifest") is True
    assert status.is_registered("policy_owned") is True


def test_split_suite_registration_reports_missing_manifest_and_policy_registration() -> None:
    """A new guarded file should fail when no accepted owner seam registers it."""
    status = _registration_status_for(UNREGISTERED_GUARDED_SPLIT_SUITE)

    assert status.relative_path == UNREGISTERED_GUARDED_SPLIT_SUITE
    assert status.ok is False
    assert status.accepted_surfaces() == SHARED_OR_POLICY_SURFACES
    assert status.registered_surfaces == frozenset()

    failure = _registration_failure_for(UNREGISTERED_GUARDED_SPLIT_SUITE)
    assert UNREGISTERED_GUARDED_SPLIT_SUITE in failure
    assert "missing accepted registration" in failure
    assert "shared_manifest=False" in failure
    assert "policy_owned=False" in failure


def test_split_suite_registration_accepts_local_only_policy_guarded_file() -> None:
    """Local-only Electron files should pass through the local-only policy seam."""
    _assert_registration_passes(
        REGISTERED_LOCAL_ONLY_SPLIT_SUITE,
        accepted_surfaces=LOCAL_ONLY_POLICY_SURFACES,
    )
    status = _registration_status_for(REGISTERED_LOCAL_ONLY_SPLIT_SUITE)

    assert status.is_registered("local_only_policy") is True


def test_split_suite_registration_accepts_focused_detector_recipe_file() -> None:
    """Reviewed detector splits should stay registered through a focused recipe."""
    _assert_registration_passes(
        REGISTERED_FOCUSED_DETECTOR_SPLIT_SUITE,
        accepted_surfaces=FOCUSED_DETECTOR_RECIPE_SURFACES,
    )
    status = _registration_status_for(REGISTERED_FOCUSED_DETECTOR_SPLIT_SUITE)

    assert status.is_registered("focused_detector_recipe") is True


def test_split_suite_registration_rejects_unregistered_focused_detector_split() -> None:
    """A new focused detector owner must not be omitted from every recipe."""
    status = _registration_status_for(UNREGISTERED_FOCUSED_DETECTOR_SPLIT_SUITE)

    assert status.ok is False
    assert status.accepted_surfaces() == FOCUSED_DETECTOR_RECIPE_SURFACES
    assert status.registered_surfaces == frozenset()

    failure = _registration_failure_for(UNREGISTERED_FOCUSED_DETECTOR_SPLIT_SUITE)
    assert "focused_detector_recipe=False" in failure


def test_split_suite_registration_uses_any_accepted_surface_not_all() -> None:
    """One accepted surface is enough; the guard does not require every surface."""
    status = _registration_status_for(REGISTERED_SHARED_MANIFEST_SPLIT_SUITE)

    assert status.accepted_surface_status() == {
        "shared_manifest": True,
        "policy_owned": True,
    }
    assert status.ok is True


def test_split_suite_registration_ignores_non_guarded_new_files() -> None:
    """Unguarded files should stay outside the registration guard entirely."""
    statuses = _registration_statuses_for((NON_GUARDED_NEW_TEST_FILE,))

    assert statuses == ()
    assert (
        check_split_suite_registration.registration_failures(
            (NON_GUARDED_NEW_TEST_FILE,)
        )
        == []
    )


def test_split_suite_registration_reports_only_unregistered_guarded_files_in_mixed_batch() -> None:
    """Mixed changed-file batches should fail only for guarded unregistered files."""
    changed_files = (
        REGISTERED_SHARED_MANIFEST_SPLIT_SUITE,
        UNREGISTERED_GUARDED_SPLIT_SUITE,
        NON_GUARDED_NEW_TEST_FILE,
    )

    statuses = _registration_statuses_for(changed_files)
    failures = check_split_suite_registration.registration_failures(changed_files)

    assert tuple(status.relative_path for status in statuses) == (
        REGISTERED_SHARED_MANIFEST_SPLIT_SUITE,
        UNREGISTERED_GUARDED_SPLIT_SUITE,
    )
    assert len(failures) == 1
    assert UNREGISTERED_GUARDED_SPLIT_SUITE in failures[0]
    assert REGISTERED_SHARED_MANIFEST_SPLIT_SUITE not in failures[0]


def test_split_suite_registration_matches_current_guarded_patterns() -> None:
    """The current guarded backend/frontend patterns should still match real files."""
    changed_files = (
        "tests/test_stream_loader_contracts.py",
        "frontend/src/hooks/useMonitoringSessionState.test.tsx",
        REGISTERED_FOCUSED_DETECTOR_SPLIT_SUITE,
        NON_GUARDED_NEW_TEST_FILE,
    )

    statuses = _registration_statuses_for(changed_files)

    assert tuple(status.relative_path for status in statuses) == (
        "tests/test_stream_loader_contracts.py",
        "frontend/src/hooks/useMonitoringSessionState.test.tsx",
        REGISTERED_FOCUSED_DETECTOR_SPLIT_SUITE,
    )


def test_split_suite_registration_stays_aligned_with_current_owner_seams() -> None:
    """Representative guarded files should stay aligned with the live owner seams."""
    statuses = _registration_statuses_for(GUARDED_OWNER_SEAM_EXEMPLARS)

    assert (
        tuple(status.relative_path for status in statuses)
        == GUARDED_OWNER_SEAM_EXEMPLARS
    )
    assert [status.ok for status in statuses] == [True, True, True, True, True]
    assert statuses[0].accepted_surfaces() == SHARED_OR_POLICY_SURFACES
    assert statuses[1].accepted_surfaces() == SHARED_OR_POLICY_SURFACES
    assert statuses[2].accepted_surfaces() == SHARED_OR_POLICY_SURFACES
    assert statuses[3].accepted_surfaces() == LOCAL_ONLY_POLICY_SURFACES
    assert statuses[4].accepted_surfaces() == FOCUSED_DETECTOR_RECIPE_SURFACES
    assert check_split_suite_registration.registration_failures(
        GUARDED_OWNER_SEAM_EXEMPLARS
    ) == []


def _alignment_contract(
    *,
    protected_groups: tuple[str, ...] = PROTECTED_ALIGNMENT_GROUPS,
    doc_requirements: tuple[Any, ...] = (),
) -> Any:
    """Build one narrow alignment contract for drift-focused tests."""
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
    """Matching workflow, policy, and docs alignment should pass."""
    contract = _alignment_contract()
    _patch_drift_inputs(monkeypatch, contract)
    _patch_clean_doc_alignment(monkeypatch)

    exit_code, out, err = _run_cli_main(
        check_ci_target_drift,
        monkeypatch,
        capsys,
        ["check_ci_target_drift.py"],
    )
    assert exit_code == 0
    assert err == ""
    assert out.strip() == "ci target drift check passed"


def test_ci_target_drift_check_reports_workflow_alignment_mismatch(
    monkeypatch,
    capsys,
) -> None:
    """Workflow-group drift should be reported by the drift checker."""
    contract = _alignment_contract()
    workflow_groups = {"backend_contract", "frontend_contract"}

    _patch_drift_inputs(
        monkeypatch,
        contract,
        workflow_groups=workflow_groups,
        policy_groups=workflow_groups,
    )
    _patch_clean_doc_alignment(monkeypatch)

    exit_code, out, err = _run_cli_main(
        check_ci_target_drift,
        monkeypatch,
        capsys,
        ["check_ci_target_drift.py"],
    )
    assert exit_code == 1
    assert out == ""
    assert "Main workflow contract-lane usage drifted" in err


def test_ci_target_drift_check_reports_policy_alignment_mismatch(
    monkeypatch,
    capsys,
) -> None:
    """Policy-group drift should be reported by the drift checker."""
    contract = _alignment_contract()
    policy_groups = {"backend_contract", "mcp_fastapi_parity"}

    _patch_drift_inputs(
        monkeypatch,
        contract,
        policy_groups=policy_groups,
    )
    _patch_clean_doc_alignment(monkeypatch)

    exit_code, out, err = _run_cli_main(
        check_ci_target_drift,
        monkeypatch,
        capsys,
        ["check_ci_target_drift.py"],
    )
    assert exit_code == 1
    assert out == ""
    assert "Consistency-script manifest-group usage drifted" in err


def test_ci_target_drift_check_reports_doc_alignment_mismatch(
    monkeypatch,
    capsys,
) -> None:
    """Missing required docs tokens should be reported by the drift checker."""
    contract = _alignment_contract(
        doc_requirements=(
            ci_target_manifest.DocAlignmentRequirement(
                path=ci_target_manifest.REPO_ROOT / "docs" / "README.md",
                required_tokens=("missing-ci-ownership-token",),
            ),
        ),
    )
    _patch_drift_inputs(monkeypatch, contract)

    exit_code, out, err = _run_cli_main(
        check_ci_target_drift,
        monkeypatch,
        capsys,
        ["check_ci_target_drift.py"],
    )
    assert exit_code == 1
    assert out == ""
    assert "missing manifest ownership references" in err
