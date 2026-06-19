# CI Maintainer Guide

Use this as the short operational map for CI ownership changes.

Use it when you need the shortest safe path for:

- changing CI-owned test target groups
- checking which lane should own a suite
- splitting tests in a guarded CI area
- understanding what `main-pr-consistency` is protecting

For the full CI behavior and validation model, use
[testing-and-validation.md](./testing-and-validation.md).

## Gate Entrypoints

Use this as the smallest top-down map before tracing individual job
dependencies.

- workflow triggers
  - `push` runs on all branches except `main`
  - `pull_request` runs for pull requests
- aggregate gates
  - `feature-gate`
  - `main-gate`
- `main` PR-only jobs
  - `main-pr-consistency`
  - `integration-smoke`
  - `main-gate`

## Intended Required-Check Contract

Use this as the branch decision artifact for `main` protection.

- required external status for `main` protection:
  - `CI / main-gate`
- internal required chain behind it:
  - `feature-gate`
  - `main-pr-consistency`
  - `integration-smoke`
  - `contract-checks`
  - `test-and-build`
- advisory-only today:
  - `frontend-lint`
  - `backend-pyright`
- not currently protected by `main-gate`:
  - `pr-template-completeness`

## Required Check Graph For `main` PRs

For GitHub branch protection, require the stable top-level status:

- `CI / main-gate`

The internal required graph for pull requests targeting `main` is:

| Job | Runs on every `main` PR | Directly required by `main-gate` | What it validates |
| --- | --- | --- | --- |
| `main-gate` | yes | n/a | final aggregate protected status for `main`; fails unless each required upstream job finishes as `success` |
| `feature-gate` | yes | yes | aggregate fast required checks: `frontend-checkpoint`, `backend-tests`, `frontend-typecheck`, `backend-typecheck`, `backend-ruff` |
| `main-pr-consistency` | yes | yes | protected-PR manifest structure, CI-owned path existence, workflow/policy drift, split-suite registration, and narrower `main` PR policy |
| `integration-smoke` | yes | yes | small backend integration smoke through `tests/test_e2e_local_session.py` |
| `contract-checks` | yes | yes | PR-only protected boundary lane that currently enforces frontend lint in the contract-sensitive PR path |
| `test-and-build` | yes | yes | manifest/path/drift checks, shared backend/frontend `contract_boundary` suites, full frontend tests, and frontend build |

This keeps the GitHub settings layer simple while preserving the internal
meaning of that one protected status.

## Frontend Validation Split For `main` PRs

Use this as the concise lane contract for frontend confidence:

- `frontend-checkpoint`
  - fast early-feedback lane for ordinary feature work
  - intentionally smaller and cheaper than the protected `main` PR lane
- `test-and-build`
  - protected shared lane behind `CI / main-gate`
  - still needs: `changes`, `frontend-checkpoint`, `backend-tests`,
    `frontend-typecheck`
  - keeps the cheaper policy and boundary checks first, then runs the full
    frontend test suite and frontend production build

Current `test-and-build` order:

1. manifest/path/drift guards
2. backend `contract_boundary` suites
3. frontend `contract_boundary` suites
4. full frontend `npm run test`
5. frontend `npm run build`

Trigger model for the heavier frontend work:

- ordinary PRs run it when `frontend`, `backend`, or `contract` paths changed
- pull requests targeting `main` force it on through `github.base_ref ==
  'main'`

Protection rule:

- `main-gate` must continue to require `test-and-build`
- full frontend validation belongs inside `test-and-build`, not in a separate
  `frontend-full` top-level job
- GitHub branch protection should keep requiring `CI / main-gate`, not a
  growing list of leaf frontend statuses

Expected tradeoff:

- slower protected `main` PR validation is intentional
- earlier feature-branch feedback should still come from
  `frontend-checkpoint`
- if this lane becomes too slow later, optimize the internal test/build shape
  first instead of removing protected frontend coverage from `main`

## Remaining Gaps After The Audit

Do not expand this list during the audit pass. Keep only the real remaining
follow-up items.

- decide whether `pr-template-completeness` should join the protected
  `main-gate` aggregate
- verify GitHub branch protection requires `CI / main-gate`
- verify GitHub is not still requiring older leaf statuses instead of the
  aggregate protected status
- open one real PR against `main` and confirm the protected statuses appear
  exactly as documented

Current check classification:

- blocking by aggregate contract: `main-gate`, `feature-gate`,
  `main-pr-consistency`, `integration-smoke`, `contract-checks`,
  `test-and-build`
- indirect blockers through `feature-gate`: `frontend-checkpoint`,
  `backend-tests`, `frontend-typecheck`, `backend-typecheck`, `backend-ruff`
- advisory only: `frontend-lint`, `backend-pyright`
- informational but not protected: `changes`, `pr-template-completeness`,
  `docs-consistency`

Nuance: standalone `frontend-lint` is advisory, but frontend lint still
becomes blocking for `main` PRs through `contract-checks`.

## Skip And Forced-On Behavior For `main` PRs

This is the highest-signal protection audit in the workflow. Unexpected
`skipped` states are the easiest way for a branch to look protected while
actually missing validation. Keep step-level skipping separate from job-level
skipping.

| Job | Can it skip on ordinary PRs? | Forced on for `main` PRs? | If it skips, what happens? |
| --- | --- | --- | --- |
| `frontend-checkpoint`, `backend-tests`, `frontend-typecheck`, `backend-typecheck`, `backend-ruff` | work steps can skip on ordinary PRs when their path filters do not match; each job still succeeds through an explicit skip step | yes, through step-level `github.base_ref == 'main'` guards | `feature-gate` still sees `success`, not `skipped`, on ordinary PRs; on `main` PRs the real work is forced on |
| `contract-checks` | yes, at the job level; it runs only for PRs with `backend`, `frontend`, or `contract` changes | yes, through the job-level `github.base_ref == 'main'` clause | if it were `skipped` on a `main` PR, `main-gate` would fail because it requires `success`; current logic avoids that by forcing the job on for `main` |
| `test-and-build` | the job itself does not skip; some heavier install/test/build steps can skip on ordinary non-relevant PRs, while manifest/path/drift checks still run | yes, through step-level `github.base_ref == 'main'` guards on the heavier frontend/backend work | it does not disappear from the graph, so `main-gate` keeps a stable upstream status; on `main` PRs the protected test/build work is forced on regardless of path filter |
| `main-gate` | yes, at the job level; it exists only on PRs targeting `main` | yes, by definition | outside `main` PRs there is no protected aggregate status; on `main` PRs it fails unless every required upstream job finishes as `success` |

## Current Owner Surfaces

- canonical CI target manifest: `.github/ci_test_targets.json`
- shared Python read-side helper: `.github/scripts/ci_target_manifest.py`
- protected PR workflow: `.github/workflows/ci.yml`
- weekly heavy workflow: `.github/workflows/weekly-validation.yml`
- narrower protected-PR policy guard:
  `.github/scripts/check_main_pr_consistency.py`
- focused CI-helper regression coverage:
  `tests/test_ci_test_target_scripts.py`

The weekly workflow now also owns the live PostgreSQL alert-confidence bundles
through a disposable GitHub Actions `postgres:16` service container. It does
not depend on a shared external database secret for the normal weekly path.

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
