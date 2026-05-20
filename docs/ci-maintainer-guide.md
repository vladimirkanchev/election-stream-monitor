# CI Maintainer Guide

Use this as the short operational map for CI ownership changes.

Use it when you need the shortest safe path for:

- changing CI-owned test target groups
- checking which lane should own a suite
- splitting tests in a guarded CI area
- understanding what `main-pr-consistency` is protecting

For the full CI behavior and validation model, use
[testing-and-validation.md](./testing-and-validation.md).

## Current Owner Surfaces

- canonical CI target manifest: `.github/ci_test_targets.json`
- shared Python read-side helper: `.github/scripts/ci_target_manifest.py`
- protected PR workflow: `.github/workflows/ci.yml`
- weekly heavy workflow: `.github/workflows/weekly-validation.yml`
- narrower protected-PR policy guard:
  `.github/scripts/check_main_pr_consistency.py`
- focused CI-helper regression coverage:
  `tests/test_ci_test_target_scripts.py`

The weekly workflow now also owns the opt-in live PostgreSQL alert-confidence
bundles when `ESM_POSTGRES_ALERT_DATABASE_URL` is configured in the repo
secrets.

## Canonical CI Target Manifests

The canonical CI target manifest lives in:

- `.github/ci_test_targets.json`

Use it as the source of truth for:

- shared target groups such as `backend_contract`, `mcp_fastapi_parity`,
  `frontend_contract`, and the weekly groups
- lane ownership metadata
- CI-owned path-existence inventory
- guarded split-suite registration metadata

Read it from Python through:

- `.github/scripts/ci_target_manifest.py`

Use it from workflow shell steps through:

- `.github/scripts/read_ci_test_targets.py`

## Lane Ownership

Current lane split:

- `fast_synthetic`
  - owner job:
    `backend-tests`
- `contract_boundary`
  - owner jobs:
    `test-and-build`, `integration-smoke`
- `weekly_slow_real_media`
  - owner jobs:
    `slow-e2e`, `api-stream-deep`, `lifecycle-deep`

Support jobs such as lint, typecheck, docs-consistency, security audit, and
packaging smoke are not lane owners.

## When Splitting Tests

When a new split suite is added in a guarded CI area, update the owner surface
that actually owns it:

- shared manifest ownership:
  - update `.github/ci_test_targets.json`
- narrower protected-PR policy ownership:
  - update `.github/scripts/check_main_pr_consistency.py`
- docs:
  - update docs only when the ownership model changes, a new guarded category
    appears, or policy-boundary meaning changes

Then verify the change with:

- `python3 .github/scripts/validate_ci_test_targets.py`
- `python3 .github/scripts/check_ci_test_paths_exist.py`
- `python3 .github/scripts/check_ci_target_drift.py`
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/pytest -q tests/test_ci_test_target_scripts.py`

## What `main-pr-consistency` Guards

`.github/scripts/check_main_pr_consistency.py` is the narrower protected-PR
policy layer.

It guards:

- workflow/package entrypoint changes moving with docs updates
- contract-sensitive code moving with `docs/contracts.md`
- contract gates moving with nearby tests
- contract gates moving with the owning docs

It reuses shared manifest groups where the repo already has stable CI target
ownership, and keeps narrower policy-only expectations for cases that should
not be promoted into shared manifest groups yet.

## What This Doc Is Not

This is not the full CI narrative.

For:

- workflow trigger details
- lane definitions
- path-filter behavior
- split-suite registration rules
- exact validation commands

go to [testing-and-validation.md](./testing-and-validation.md).
