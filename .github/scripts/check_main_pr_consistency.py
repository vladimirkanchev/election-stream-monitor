#!/usr/bin/env python3
"""Lightweight main-PR consistency checks for docs and workflow-sensitive changes.

The contract gates now consume the same manifest-backed CI target groups used by
the active workflow jobs where that reuse is practical, which reduces one of
the main drift seams between CI execution and CI policy enforcement.
"""

from __future__ import annotations

from dataclasses import dataclass
from fnmatch import fnmatch
from functools import cache
import subprocess
import sys
from pathlib import Path

from ci_target_manifest import CiTargetManifest, REPO_ROOT

DOC_PATHS = (
    "README.md",
    "frontend/README.md",
    "docs/",
)

WORKFLOW_PATHS = (
    ".github/workflows/",
    "frontend/package.json",
)

CONTRACT_PATHS = (
    "src/source_validation.py",
    "src/session_io.py",
    "src/session_models.py",
    "src/alert_rules.py",
    "src/stream_loader_contracts.py",
    "src/api/routers/sessions.py",
    "src/api/schemas.py",
    "frontend/src/bridge/contract.ts",
    "frontend/src/bridge/contractErrors.ts",
    "frontend/src/bridge/contractDetectors.ts",
    "frontend/src/bridge/contractSessionSnapshot.ts",
    "docs/contracts.md",
)


@dataclass(frozen=True)
class ContractGate:
    """Policy gate for one contract-sensitive part of the repo.

    Manifest-backed groups cover the shared stable CI language. Local extras
    remain for expectations that are intentionally narrower than the manifest.
    """

    label: str
    paths: tuple[str, ...]
    docs: tuple[str, ...]
    tests: tuple[str, ...] = ()
    manifest_test_groups: tuple[str, ...] = ()
    extra_tests: tuple[str, ...] = ()


CONTRACT_GATES = (
    ContractGate(
        label="backend contract",
        paths=(
            "src/source_validation.py",
            "src/stream_loader.py",
            "src/stream_loader_contracts.py",
            "src/stream_loader_http_hls.py",
            "src/session_io.py",
            "src/session_models.py",
            "src/session_runner.py",
            "src/session_runner_progress.py",
            "src/session_service.py",
            "src/alert_rules.py",
            "src/api/schemas.py",
            "src/api/routers/sessions.py",
        ),
        manifest_test_groups=(
            "backend_contract",
            "mcp_fastapi_parity",
        ),
        extra_tests=(
            "tests/test_api_boundary_validation.py",
            "tests/test_mcp_server_alerts_behavior.py",
            "tests/test_mcp_server_alerts_errors.py",
            "tests/test_mcp_server_incidents_behavior.py",
            "tests/test_mcp_server_incidents_errors.py",
            "tests/test_stream_loader_contracts.py",
            "tests/test_stream_loader_http_hls_policy.py",
            "tests/test_stream_loader_http_hls_playlist.py",
            "tests/test_stream_loader_http_hls_fetch.py",
            "tests/test_stream_loader_http_hls_materialize.py",
            "tests/test_stream_loader_http_hls_core_provider.py",
            "tests/test_stream_loader_http_hls_core_progression.py",
            "tests/test_stream_loader_http_hls_reconnect_recovery.py",
            "tests/test_stream_loader_http_hls_reconnect_state.py",
            "tests/test_stream_loader_http_hls_limits_runtime.py",
            "tests/test_stream_loader_http_hls_limits_cleanup.py",
            "tests/test_stream_loader_http_hls_limits_restart.py",
            "tests/test_session_runner_api_stream_completion.py",
            "tests/test_session_runner_api_stream_cancellation.py",
            "tests/test_session_runner_execution_local.py",
            "tests/test_session_runner_execution_api_stream.py",
        ),
        docs=("docs/contracts.md", "docs/session-model.md"),
    ),
    ContractGate(
        label="frontend bridge contract",
        paths=(
            "frontend/src/bridge/**",
            "frontend/src/types.ts",
            "frontend/src/hooks/useMonitoringSession*.tsx",
            "frontend/src/hooks/usePlaybackSource*.tsx",
            "frontend/src/uiErrors.ts",
        ),
        manifest_test_groups=("frontend_contract",),
        extra_tests=(
            "frontend/src/bridge/contract.session-snapshot.test.ts",
            "frontend/src/hooks/useMonitoringSession.lifecycle.test.tsx",
            "frontend/src/hooks/useMonitoringSession.apiStream.test.tsx",
            "frontend/src/hooks/usePlaybackSource.test.tsx",
        ),
        docs=("docs/contracts.md",),
    ),
    ContractGate(
        label="electron trust/playback contract",
        paths=(
            "frontend/electron/playbackSourcePolicy.mjs",
            "frontend/electron/localMediaRequestPolicy.mjs",
            "frontend/electron/bridgeResponses.mjs",
            "frontend/electron/fastApiFallback.mjs",
            "frontend/electron/fastApiRuntimePolicy.mjs",
            "frontend/electron/fastApiClient.mjs",
            "frontend/electron/fastApiProcessManager.mjs",
            "frontend/electron/fastApiStartupOrchestrator.mjs",
            "frontend/electron/localMediaResponses.mjs",
        ),
        tests=(
            "frontend/electron/playbackSourcePolicy.test.mjs",
            "frontend/electron/localMediaRequestPolicy.test.mjs",
            "frontend/electron/bridgeResponses.test.mjs",
            "frontend/electron/fastApiFallback.test.mjs",
            "frontend/electron/fastApiRuntimePolicy.test.mjs",
            "frontend/electron/fastApiClient.test.mjs",
            "frontend/electron/fastApiProcessManager.test.mjs",
            "frontend/electron/fastApiStartupOrchestrator.test.mjs",
            "frontend/electron/localMediaResponses.test.mjs",
        ),
        docs=("docs/contracts.md", "docs/architecture.md"),
    ),
)


@cache
def _load_ci_target_manifest() -> CiTargetManifest:
    """Return the parsed CI target manifest used by workflow and policy checks.

    This keeps the main PR policy gate aligned with the same stable target
    groups the workflows already consume directly.
    """
    return CiTargetManifest.load()


def _manifest_group_targets(group_name: str) -> tuple[str, ...]:
    """Return one stable manifest-backed CI target group."""
    return _load_ci_target_manifest().group_targets(group_name)


def _gate_tests(gate: ContractGate) -> tuple[str, ...]:
    """Return the combined manifest-backed and gate-local test expectations.

    Manifest-backed groups cover the shared stable CI language. Gate-local
    extras remain for expectations that are not yet owned by a canonical
    manifest group.
    """
    manifest_tests = tuple(
        test_path
        for group_name in gate.manifest_test_groups
        for test_path in _manifest_group_targets(group_name)
    )
    return manifest_tests + gate.extra_tests + gate.tests


def _changed_files(diff_range: str) -> list[str]:
    """Return repo-relative files changed in the provided git diff range."""
    result = subprocess.run(
        ["git", "diff", "--name-only", diff_range],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def _matches_any(path: str, prefixes: tuple[str, ...]) -> bool:
    """Return whether a changed path matches one exact or prefix-based trigger."""
    return any(path == prefix or path.startswith(prefix) for prefix in prefixes)


def _matches_glob_any(paths: list[str], patterns: tuple[str, ...]) -> bool:
    """Return whether any changed path matches any glob-like gate pattern."""
    return any(any(fnmatch(path, pattern) for pattern in patterns) for path in paths)


def main() -> int:
    """Run the manifest-backed main PR consistency policy check."""
    if len(sys.argv) != 2:
        print("usage: check_main_pr_consistency.py <diff-range>", file=sys.stderr)
        return 2

    changed = _changed_files(sys.argv[1])
    changed_set = set(changed)

    docs_changed = any(_matches_any(path, DOC_PATHS) for path in changed)
    workflow_sensitive = any(_matches_any(path, WORKFLOW_PATHS) for path in changed)
    contract_sensitive = any(path in CONTRACT_PATHS for path in changed_set)

    failures: list[str] = []

    if workflow_sensitive and not docs_changed:
        failures.append(
            "Workflow or package CI entrypoints changed without any docs update "
            "(expected one of README.md, frontend/README.md, or docs/*)."
        )

    if contract_sensitive and "docs/contracts.md" not in changed_set:
        failures.append(
            "Contract-sensitive code changed without updating docs/contracts.md."
        )

    for gate in CONTRACT_GATES:
        if not _matches_glob_any(changed, gate.paths):
            continue

        gate_tests = _gate_tests(gate)

        if not _matches_glob_any(changed, gate_tests):
            failures.append(
                f"{gate.label.capitalize()} changed without a matching test update "
                f"(expected one of: {', '.join(gate_tests)})."
            )

        if not _matches_glob_any(changed, gate.docs):
            failures.append(
                f"{gate.label.capitalize()} changed without a matching docs update "
                f"(expected one of: {', '.join(gate.docs)})."
            )

    if failures:
        print("main-pr-consistency check failed:", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        print("changed files:", file=sys.stderr)
        for path in changed:
            print(f"  {path}", file=sys.stderr)
        return 1

    print("main-pr-consistency check passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
