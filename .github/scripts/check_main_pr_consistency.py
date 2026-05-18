#!/usr/bin/env python3
"""Run the narrower manifest-aware main-PR policy checks.

This script is the protected-PR policy layer that sits beside, not above, the
shared CI manifest:
- `.github/ci_test_targets.json` owns shared target groups
- this script owns narrower gate activation rules, docs expectations, and
  policy-only test expectations

Where practical, gates reuse manifest-backed groups from the active workflow.
That keeps CI execution and CI policy aligned without promoting every narrower
policy expectation into the shared manifest.

Current frontend split:
- shared `frontend_contract` ownership for bridge, transport, and `uiErrors`
  contract suites
- policy-only ownership for narrower hook-level monitoring/playback tests
- local-only ownership for Electron trust/playback expectations

For the short maintainer-facing summary of how this policy fits into CI
ownership, see `docs/ci-maintainer-guide.md`.
"""

from __future__ import annotations

from dataclasses import dataclass
from fnmatch import fnmatch
import subprocess
import sys

from ci_target_manifest import REPO_ROOT, manifest_group_targets

DOC_PATHS = (
    "README.md",
    "frontend/README.md",
    "docs/",
)

# These top-level path sets are policy triggers, not shared CI target inventory.
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

BACKEND_POLICY_GROUPS = (
    "backend_contract",
    "mcp_fastapi_parity",
)

FRONTEND_BRIDGE_POLICY_GROUPS = ("frontend_contract",)

# These tuples are intentionally policy-only. They stay outside the manifest
# because they are special-case expectations that are narrower than the shared
# CI ownership groups.
BACKEND_POLICY_ONLY_TESTS = (
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
)

FRONTEND_BRIDGE_POLICY_ONLY_TESTS = (
    "frontend/src/hooks/useMonitoringSession.lifecycle.test.tsx",
    "frontend/src/hooks/useMonitoringSession.apiStream.test.tsx",
    "frontend/src/hooks/usePlaybackSource.test.tsx",
)

FRONTEND_BRIDGE_CHANGED_PATHS = (
    "frontend/src/bridge/**",
    "frontend/src/types.ts",
    "frontend/src/hooks/useMonitoringSession*.tsx",
    "frontend/src/hooks/usePlaybackSource*.tsx",
    "frontend/src/uiErrors.ts",
)

ELECTRON_TRUST_PLAYBACK_POLICY_ONLY_TESTS = (
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

ELECTRON_TRUST_PLAYBACK_CHANGED_PATHS = (
    "frontend/electron/playbackSourcePolicy.mjs",
    "frontend/electron/localMediaRequestPolicy.mjs",
    "frontend/electron/bridgeResponses.mjs",
    "frontend/electron/fastApiFallback.mjs",
    "frontend/electron/fastApiRuntimePolicy.mjs",
    "frontend/electron/fastApiClient.mjs",
    "frontend/electron/fastApiProcessManager.mjs",
    "frontend/electron/fastApiStartupOrchestrator.mjs",
    "frontend/electron/localMediaResponses.mjs",
)


@dataclass(frozen=True)
class ContractGate:
    """Policy gate for one contract-sensitive CI seam.

    Manifest-backed groups cover the shared stable CI language. Policy-only
    tests remain for expectations that are intentionally narrower than the
    manifest. A gate may also stay fully local when the repo does not yet
    expose a matching shared manifest-backed CI group.

    Read each gate as:
    - label
    - changed paths
    - manifest groups
    - policy-only tests
    - docs expectations
    """

    label: str
    changed_paths: tuple[str, ...]
    manifest_groups: tuple[str, ...] = ()
    policy_only_tests: tuple[str, ...] = ()
    docs_expectations: tuple[str, ...] = ()

    def uses_manifest_groups(self) -> bool:
        """Return whether this gate reuses shared manifest-backed target groups."""
        return bool(self.manifest_groups)

    def expected_tests(self) -> tuple[str, ...]:
        """Return the full test expectations for this gate.

        Shared manifest-backed groups provide the broad CI-owned coverage for
        the gate. Smaller policy-only tuples keep the expectations that should
        stay narrower than the shared manifest groups for now.
        """
        return _manifest_group_test_paths(self.manifest_groups) + self.policy_only_tests

    def matches_changed_files(self, changed_files: list[str]) -> bool:
        """Return whether any changed file activates this gate."""
        return _matches_glob_any(changed_files, self.changed_paths)


def _ordered_unique_values(values: tuple[str, ...]) -> tuple[str, ...]:
    """Return one stable tuple without duplicate values, preserving order."""
    ordered_unique_values: list[str] = []
    seen_values: set[str] = set()

    for value in values:
        if value in seen_values:
            continue
        seen_values.add(value)
        ordered_unique_values.append(value)

    return tuple(ordered_unique_values)


def _manifest_group_test_paths(group_names: tuple[str, ...]) -> tuple[str, ...]:
    """Return the shared manifest-backed test paths for one group tuple.

    This keeps manifest-group flattening in one place for both per-gate
    expectations and policy-wide manifest-backed test ownership.
    """
    return tuple(
        test_path
        for group_name in group_names
        for test_path in manifest_group_targets(group_name)
    )


CONTRACT_GATES = (
    ContractGate(
        label="backend contract",
        changed_paths=(
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
        # This gate reads the same shared backend and parity suites that the
        # protected CI workflow already uses.
        manifest_groups=BACKEND_POLICY_GROUPS,
        # These remain policy-only because the gate expects narrower coverage
        # than the broader manifest-backed CI lane.
        policy_only_tests=BACKEND_POLICY_ONLY_TESTS,
        docs_expectations=("docs/contracts.md", "docs/session-model.md"),
    ),
    ContractGate(
        label="frontend bridge contract",
        changed_paths=FRONTEND_BRIDGE_CHANGED_PATHS,
        # This gate reads the same shared frontend contract group that the
        # protected CI workflow already uses.
        manifest_groups=FRONTEND_BRIDGE_POLICY_GROUPS,
        # These stay policy-only because they assert hook-level
        # monitoring/playback behavior after bridge normalization rather than
        # the stable shared bridge/transport/ui-errors contract lane itself.
        policy_only_tests=FRONTEND_BRIDGE_POLICY_ONLY_TESTS,
        docs_expectations=("docs/contracts.md",),
    ),
    ContractGate(
        label="electron trust/playback contract",
        changed_paths=ELECTRON_TRUST_PLAYBACK_CHANGED_PATHS,
        # This gate still owns its full policy-only test list because it is not
        # yet represented by a shared manifest-backed CI target group.
        policy_only_tests=ELECTRON_TRUST_PLAYBACK_POLICY_ONLY_TESTS,
        docs_expectations=("docs/contracts.md", "docs/architecture.md"),
    ),
)


def policy_only_test_paths() -> tuple[str, ...]:
    """Return every gate-local policy-only test path across all contract gates."""
    return _ordered_unique_values(
        tuple(
            relative_path
            for gate in CONTRACT_GATES
            for relative_path in gate.policy_only_tests
        )
    )


def local_only_policy_test_paths() -> tuple[str, ...]:
    """Return only the policy-only test paths from gates with no manifest groups."""
    return _ordered_unique_values(
        tuple(
            relative_path
            for gate in CONTRACT_GATES
            if not gate.uses_manifest_groups()
            for relative_path in gate.policy_only_tests
        )
    )


def manifest_policy_groups() -> tuple[str, ...]:
    """Return the deduplicated manifest groups consumed by policy gates.

    This is the explicit policy-owner seam for CI drift checks. Shared
    workflow/policy alignment should read from this helper instead of
    reverse-engineering `ContractGate(...)` internals.
    """
    return _ordered_unique_values(
        tuple(group_name for gate in CONTRACT_GATES for group_name in gate.manifest_groups)
    )


def manifest_policy_test_paths() -> tuple[str, ...]:
    """Return the shared manifest-backed test paths reused by policy gates."""
    return _manifest_group_test_paths(manifest_policy_groups())


def policy_owned_test_paths() -> tuple[str, ...]:
    """Return the full test surface owned by the main-PR policy layer.

    This combines shared manifest-backed tests reused by policy gates with the
    narrower policy-only expectations that stay local to this script.
    """
    return manifest_policy_test_paths() + policy_only_test_paths()


def _changed_files(diff_range: str) -> list[str]:
    """Return repo-relative changed files for one PR-style diff range."""
    result = subprocess.run(
        ["git", "diff", "--name-only", diff_range],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def _matches_any(path: str, prefixes: tuple[str, ...]) -> bool:
    """Return whether one changed path matches any exact or prefix trigger."""
    return any(path == prefix or path.startswith(prefix) for prefix in prefixes)


def _matches_glob_any(paths: list[str], patterns: tuple[str, ...]) -> bool:
    """Return whether any changed path matches any gate glob/pattern."""
    return any(any(fnmatch(path, pattern) for pattern in patterns) for path in paths)


def main() -> int:
    """Run the manifest-backed main PR consistency policy check.

    The policy layer stays intentionally narrower than the shared CI manifest:
    it enforces docs expectations, special-case policy-only tests, and the
    current gate activation rules for `main` pull requests. The shared target
    groups themselves remain owned by `.github/ci_test_targets.json`.

    For the frontend boundary, this means the shared workflow lane stays
    focused on `frontend_contract`, while hook-level monitoring/playback
    expectations continue to live here as policy-only checks.
    """
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
        if not gate.matches_changed_files(changed):
            continue

        gate_tests = gate.expected_tests()

        if not _matches_glob_any(changed, gate_tests):
            failures.append(
                f"{gate.label.capitalize()} changed without a matching test update "
                f"(expected one of: {', '.join(gate_tests)})."
            )

        if not _matches_glob_any(changed, gate.docs_expectations):
            failures.append(
                f"{gate.label.capitalize()} changed without a matching docs update "
                f"(expected one of: {', '.join(gate.docs_expectations)})."
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
