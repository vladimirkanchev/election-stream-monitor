# CI Maintainer Guide

Use this as the short operational map for CI ownership changes.

Use it when you need the shortest safe path for:

- changing CI-owned test target groups
- checking which lane should own a suite
- splitting tests in a guarded CI area
- understanding what `main-pr-consistency` is protecting

For the full CI behavior and validation model, use
[testing-and-validation.md](./testing-and-validation.md).

For AI-assisted tools, keep this split strict:

- use this guide for protection policy, dependency graphs, advisory versus
  required meaning, and skip/forced-on behavior
- use `testing-and-validation.md` for local commands, validation scope, and
  contributor run choices
- prefer linking across the two docs instead of copying the same CI rule twice

## Lane Terminology

Use these terms consistently when reading or changing CI:

- **required**: blocks a pull request to `main` through the protected
  `CI / main-gate` status, either directly or through its dependency graph
- **advisory**: runs in CI and reports useful failures, but cannot block merge
- **informational**: reports process, policy, or coordination status outside
  the protected merge contract
- **weekly**: deeper validation started by the scheduled weekly workflow or
  manual workflow dispatch; it is not an ordinary PR merge gate
- **local**: contributor-run validation such as `just test-fast` or
  `just ci-local`; it produces no GitHub required status

Running in CI does not by itself make a job required. Required status is
defined by the `main-gate` dependency contract and the matching GitHub branch
protection or ruleset.

## Lane Classification

Use this matrix as the authoritative high-level policy view. The sections
below explain the required dependency graph and activation details.

| Lane | Examples | Blocks `main` merge? | Activation |
| --- | --- | --- | --- |
| Required | `main-gate` and its protected dependency chain | yes | path-aware normally; protected work is forced on for `main` PRs |
| Advisory | standalone `frontend-lint`, `backend-pyright` | no | path-aware branch or PR runs |
| Informational | `changes`, `pr-template-completeness`, `docs-consistency` | no | workflow or policy conditions |
| Weekly | slow media, lifecycle, deep `api_stream`, audits, PostgreSQL confidence | no | Sunday 03:00 UTC or manual dispatch |
| Local | `just test-fast`, `just ci-local`, focused `just` recipes | no | contributor initiated |

Weekly failures fail the weekly workflow but do not block an ordinary PR
merge. Local lanes produce no GitHub status and do not reproduce the complete
protected workflow.

## Important Distinctions

Keep these five distinctions explicit when reviewing or editing CI:

- `CI / main-gate` is the external required status for `main` branch
  protection
- standalone `frontend-lint` and `backend-pyright` are advisory jobs, even
  though protected `main` PRs still enforce frontend lint through
  `contract-checks`
- informational jobs are not the same as advisory jobs; they report process or
  policy state outside the protected merge contract
- weekly checks fail the weekly workflow when they break, but they do not
  block an ordinary PR
- local commands approximate CI intent for contributors, but they do not
  replace protected checks, GitHub event handling, or branch-protection wiring

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

## Main Protection Contract

Use this as the shortest branch decision artifact for `main` protection.

- external required status:
  - `CI / main-gate`
- direct blockers behind `main-gate`:
  - `feature-gate`
  - `main-pr-consistency`
  - `integration-smoke`
  - `contract-checks`
  - `test-and-build`
- indirect blockers through `feature-gate`:
  - `frontend-checkpoint`
  - `backend-tests`
  - `frontend-typecheck`
  - `backend-typecheck`
  - `backend-ruff`
- advisory only:
  - standalone `frontend-lint`; protected `main` PRs still enforce frontend
    lint through `contract-checks`
  - `backend-pyright`; `backend-typecheck` remains the protected primary
    Python type gate
- informational, not protected:
  - `pr-template-completeness`
  - `docs-consistency`
  - `changes`

## Required Check Graph For `main` PRs

For GitHub branch protection, require the stable top-level status:

- `CI / main-gate`

The internal required graph for pull requests targeting `main` is:

| Job | Runs on every `main` PR | Directly required by `main-gate` | What it validates |
| --- | --- | --- | --- |
| `main-gate` | yes | n/a | final aggregate protected status for `main`; fails unless each required upstream job finishes as `success` |
| `feature-gate` | yes | yes | aggregate fast required checks: `frontend-checkpoint`, `backend-tests`, `frontend-typecheck`, `backend-typecheck`, `backend-ruff` |
| `main-pr-consistency` | yes | yes | protected-PR manifest structure, CI-owned path existence, fixture/environment policy assumptions, workflow/policy drift, split-suite registration, and narrower `main` PR policy |
| `integration-smoke` | yes | yes | small backend integration smoke through `tests/test_e2e_local_session.py` |
| `contract-checks` | yes | yes | PR-only protected boundary lane that currently enforces frontend lint in the contract-sensitive PR path |
| `test-and-build` | yes | yes | manifest/path/drift checks, shared backend/frontend `contract_boundary` suites, full frontend tests, and frontend build |

This keeps the GitHub settings layer simple while preserving the internal
meaning of that one protected status.

## Coverage Map

Use this table before changing `main-gate` dependencies or promoting advisory
checks.

| Target validation | Current workflow path | Protected now? | Notes |
| --- | --- | --- | --- |
| backend fast tests and packaging smoke | `main-gate -> feature-gate -> backend-tests` | yes | includes editable-install packaging check, import smoke, compile smoke, and fast backend tests |
| Ruff | `main-gate -> feature-gate -> backend-ruff` | yes | already part of the aggregate fast protected backend lane |
| backend mypy | `main-gate -> feature-gate -> backend-typecheck` | yes | current primary Python type gate |
| frontend typecheck | `main-gate -> feature-gate -> frontend-typecheck` | yes | already protected through the fast aggregate gate |
| full frontend tests and build | `main-gate -> test-and-build` | yes | protected shared lane now carries the full frontend suite and production build |
| contract checks | `main-gate -> contract-checks` | yes | protected PR boundary lane |
| integration smoke | `main-gate -> integration-smoke` | yes | protected `main` PR smoke path |
| CI consistency checks | `main-gate -> main-pr-consistency`; `docs-consistency` stays non-`main` | yes | `main-pr-consistency` is the protected `main` policy owner; `docs-consistency` remains the non-`main` early-feedback lane |
| PR-template completeness | standalone `pr-template-completeness` job | no | intentionally informational process policy, not part of `main-gate` |
| standalone frontend lint | standalone `frontend-lint` stays advisory; protected `main` PRs still block on frontend lint through `contract-checks` | yes, through `contract-checks` | no separate top-level protected frontend-lint status is currently intended |

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

## Frontend Lint Policy

Keep the current lint shape unless you intentionally want a separate required
status:

- standalone `frontend-lint` remains advisory
- protected `main` PRs still block on frontend lint through `contract-checks`
- do not add `frontend-lint` separately into `feature-gate` or `main-gate`
  unless you want an additional top-level blocking policy surface

## PR Template Policy

Keep `pr-template-completeness` informational for now:

- it is process policy, not product-correctness validation
- it should not block `main` merges unless the repo intentionally wants that
  extra friction
- missing validation/docs text should still be fixed in review, but the
  protected merge contract remains centered on runtime, test, type, lint, and
  CI-consistency checks

## Python Type Policy

Keep one protected Python type gate:

- `backend-typecheck` is the protected backend Python type gate
- `backend-typecheck` currently runs `mypy` and remains the primary merge
  blocker for backend typing
- `backend-pyright` stays advisory for extra signal and editor alignment
- do not add `backend-pyright` into `feature-gate` or `main-gate` unless the
  repo intentionally wants two blocking Python type tools

## GitHub Settings Follow-up

The workflow contract is now explicit in-repo. GitHub branch protection still
has to require the right external status:

- require `CI / main-gate`
- avoid requiring older leaf statuses instead of the aggregate protected
  status
- confirm one real PR against `main` shows the protected statuses exactly as
  documented

Nuance: standalone `frontend-lint` is advisory, but protected `main` PRs still
block on frontend lint through `contract-checks`.

## Skip And Forced-On Behavior For `main` PRs

This is the highest-signal protection audit in the workflow. Unexpected
`skipped` states are the easiest way for a branch to look protected while
actually missing validation. Keep step-level skipping separate from job-level
skipping. The protected forced-on audit for this contract covers:

- `backend-tests`
- `backend-ruff`
- `backend-typecheck`
- `frontend-typecheck`
- `contract-checks`
- `test-and-build`
- `main-pr-consistency`

`pr-template-completeness` is intentionally outside this audit because it is
informational rather than protected by `main-gate`.

| Job | Can it skip on ordinary PRs? | Forced on for `main` PRs? | If it skips, what happens? |
| --- | --- | --- | --- |
| `frontend-checkpoint`, `backend-tests`, `frontend-typecheck`, `backend-typecheck`, `backend-ruff` | work steps can skip on ordinary PRs when their path filters do not match; each job still succeeds through an explicit skip step | yes, through step-level `github.base_ref == 'main'` guards | `feature-gate` still sees `success`, not `skipped`, on ordinary PRs; on `main` PRs the real work is forced on |
| `contract-checks` | yes, at the job level; it runs only for PRs with `backend`, `frontend`, or `contract` changes | yes, through the job-level `github.base_ref == 'main'` clause | if it were `skipped` on a `main` PR, `main-gate` would fail because it requires `success`; current logic avoids that by forcing the job on for `main` |
| `test-and-build` | the job itself does not skip; some heavier install/test/build steps can skip on ordinary non-relevant PRs, while manifest/path/drift checks still run | yes, through step-level `github.base_ref == 'main'` guards on the heavier frontend/backend work | it does not disappear from the graph, so `main-gate` keeps a stable upstream status; on `main` PRs the protected test/build work is forced on regardless of path filter |
| `main-pr-consistency` | no, for `main` PRs; it is a dedicated protected `main` PR policy lane rather than a path-filtered branch lane | yes, by construction; the job exists only for pull requests targeting `main` | it cannot silently path-skip protected `main` consistency work; if it is absent, `main-gate` cannot pass for a `main` PR |
| `main-gate` | yes, at the job level; it exists only on PRs targeting `main` | yes, by definition | outside `main` PRs there is no protected aggregate status; on `main` PRs it fails unless every required upstream job finishes as `success` |

## Current Owner Surfaces

- canonical CI target manifest: `.github/ci_test_targets.json`
- shared Python read-side helper: `.github/scripts/ci_target_manifest.py`
- protected PR workflow: `.github/workflows/ci.yml`
- weekly heavy workflow: `.github/workflows/weekly-validation.yml`
- narrow workflow reader: `.github/scripts/ci_workflow.py`
- protected workflow-contract validator:
  `.github/scripts/ci_workflow_contract.py`
- narrower protected-PR policy guard:
  `.github/scripts/check_main_pr_consistency.py`
- focused workflow-regression tests:
  - `tests/test_ci_workflow.py`
    - owns the protected `ci.yml` contract through one narrow workflow reader
  - `tests/test_ci_test_target_scripts.py`
    - owns manifest/helper/ownership drift checks around that workflow

Task-4 workflow regression coverage intentionally stays narrow. The protected
invariants under test are:

- exact `main-gate` direct dependencies
- protected frontend `npm run test` and `npm run build` ownership in
  `test-and-build`
- forced-on behavior for protected `main` PR jobs and work steps
- advisory-job classification for standalone `frontend-lint` and
  `backend-pyright`

The weekly workflow now also owns the live PostgreSQL alert-confidence bundles
through a disposable GitHub Actions `postgres:16` service container. It does
not depend on a shared external database secret for the normal weekly path.

Focused local validation for this task-4 surface:

- `python3 .github/scripts/validate_ci_test_targets.py`
- `python3 .github/scripts/check_ci_test_paths_exist.py`
- `python3 .github/scripts/check_ci_target_drift.py`
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/pytest -q tests/test_ci_workflow.py tests/test_ci_test_target_scripts.py`

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
policy layer, and the `main-pr-consistency` job is the protected `main`
owner for CI/docs/workflow consistency checks.

It guards:

- workflow/package entrypoint changes moving with docs updates
- contract-sensitive code moving with `docs/contracts.md`
- contract gates moving with nearby tests
- contract gates moving with the owning docs
- fixture and environment policy assumptions in the protected `main` path

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
