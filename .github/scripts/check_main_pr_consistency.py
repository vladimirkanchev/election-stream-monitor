#!/usr/bin/env python3
"""Lightweight main-PR consistency checks for docs and workflow-sensitive changes."""

from __future__ import annotations

from fnmatch import fnmatch
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]

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

CONTRACT_GATES = (
    {
        "label": "backend contract",
        "paths": (
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
        "tests": (
            "tests/test_api_boundary_contracts.py",
            "tests/test_api_boundary_validation.py",
            "tests/test_api_boundary_sessions.py",
            "tests/test_session_service.py",
            "tests/test_session_cli_tooling.py",
            "tests/test_stream_loader_contracts.py",
            "tests/test_stream_loader_http_hls_policy.py",
            "tests/test_stream_loader_http_hls_playlist.py",
            "tests/test_stream_loader_http_hls_fetch.py",
            "tests/test_stream_loader_http_hls_materialize.py",
            "tests/test_stream_loader_http_hls_core_provider.py",
            "tests/test_stream_loader_http_hls_core_progression.py",
            "tests/test_stream_loader_http_hls_reconnect.py",
            "tests/test_stream_loader_http_hls_limits.py",
            "tests/test_session_runner_api_stream_completion.py",
            "tests/test_session_runner_api_stream_cancellation.py",
            "tests/test_session_runner_execution.py",
        ),
        "docs": ("docs/contracts.md", "docs/session-model.md"),
    },
    {
        "label": "frontend bridge contract",
        "paths": (
            "frontend/src/bridge/**",
            "frontend/src/types.ts",
            "frontend/src/hooks/useMonitoringSession*.tsx",
            "frontend/src/hooks/usePlaybackSource*.tsx",
            "frontend/src/uiErrors.ts",
        ),
        "tests": (
            "frontend/src/bridge/contract.success.test.ts",
            "frontend/src/bridge/contract.errors.test.ts",
            "frontend/src/bridge/contract.session-snapshot.test.ts",
            "frontend/src/bridge/transport.test.ts",
            "frontend/src/uiErrors.test.ts",
            "frontend/src/hooks/useMonitoringSession.lifecycle.test.tsx",
            "frontend/src/hooks/useMonitoringSession.apiStream.test.tsx",
            "frontend/src/hooks/usePlaybackSource.test.tsx",
        ),
        "docs": ("docs/contracts.md",),
    },
    {
        "label": "electron trust/playback contract",
        "paths": (
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
        "tests": (
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
        "docs": ("docs/contracts.md", "docs/architecture.md"),
    },
)


def _changed_files(diff_range: str) -> list[str]:
    result = subprocess.run(
        ["git", "diff", "--name-only", diff_range],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def _matches_any(path: str, prefixes: tuple[str, ...]) -> bool:
    return any(path == prefix or path.startswith(prefix) for prefix in prefixes)


def _matches_glob_any(paths: list[str], patterns: tuple[str, ...]) -> bool:
    return any(any(fnmatch(path, pattern) for pattern in patterns) for path in paths)


def main() -> int:
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
        if not _matches_glob_any(changed, gate["paths"]):
            continue

        if not _matches_glob_any(changed, gate["tests"]):
            failures.append(
                f"{gate['label'].capitalize()} changed without a matching test update "
                f"(expected one of: {', '.join(gate['tests'])})."
            )

        if not _matches_glob_any(changed, gate["docs"]):
            failures.append(
                f"{gate['label'].capitalize()} changed without a matching docs update "
                f"(expected one of: {', '.join(gate['docs'])})."
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
