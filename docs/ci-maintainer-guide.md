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
  `main-gate` status, either directly or through its dependency graph
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

## Detector Validation CI Baseline

This table is the CI ownership snapshot for detector-validation lanes. It is
intentionally narrower than the detailed test and fixture inventory in
[detector-validation-ownership.md](./detector-validation-ownership.md): use
this table when changing a recipe, workflow target, marker, or failure
artifact.

The focused rows below are snapshots, not performance gates. Most local
measurements were captured on 2026-07-31; the `fast_synthetic` row was
refreshed on 2026-08-01. The weekly row uses the checked-in snapshot recorded
in the ownership guide because it is scheduled/manual depth.

| Lane | Targets | Marker / expected skips | Current evidence | CI owner and failure evidence |
| --- | --- | --- | --- | --- |
| `just test-detectors` | `tests/test_detectors.py` | Unmarked; no expected skips. | 31 passed in 0.22s. | Local focused lane; also selected by `fast_synthetic`. |
| `just test-alert-rules` | `tests/test_alert_rules.py`, `test_alert_rules_black.py`, `test_alert_rules_blur.py` | Unmarked; no expected skips. | 47 passed in 0.22s. | Local focused lane; also selected by `fast_synthetic`. |
| `just test-processor` | `tests/test_processor_routing.py`, `test_processor_context_alerts.py`, `test_processor_failures.py` | Unmarked; no expected skips. | 19 passed in 0.57s. | Local focused lane; also selected by `fast_synthetic`. |
| `just test-detector-lab` | The four synthetic detector-lab owners: runner, metrics, practical blur, practical motion. | Unmarked; no expected skips. | 81 passed in 0.76s. | Local focused lane; also selected by `fast_synthetic`. |
| `just test-real-media` | `tests/test_detectors_integration.py`, `tests/test_detector_lab_real_media.py` | `slow`; no expected skips when checked-in fixtures and decoder tools are available. | 10 passed in 42.26s. | Local focused lane; both suites are included in `weekly_slow_media`. |
| `fast_synthetic` | Broad `pytest -m "not e2e and not slow"` selector. | Excludes slow and E2E tests rather than skipping them; no detector-specific skip allowance. | 1,938 selected from 2,052 collected: 1,790 passed, 148 skipped, and 114 deselected in 8.89s. | Path-aware branch feedback and required `backend-tests` coverage on `main` PRs; failure-only `backend-tests.log`. |
| `weekly_slow_media` | Checked-in session/media truth plus `test_detectors_integration.py` and `test_detector_lab_real_media.py`. | `slow`; optional representative assets are not targets. The recorded checked-in snapshot has zero skips. | 35 passed in 81.93s in the recorded weekly-equivalent snapshot. | Scheduled/manual weekly depth; non-decoding fixture/tool preflight, failure-only log, detector-lab CSV, and bounded ground-truth diagnostics. |

Do not create a detector-only required workflow from this table. Routine CI
already exercises the fast synthetic detector surfaces, while the manifest
keeps decoded media and session truth together in one deliberately deeper
weekly lane.

### Weekly Media Failure Artifacts

`slow-e2e` first performs a non-decoding check of required checked-in media
and FFmpeg/FFprobe. On failure, it uploads only the sanitized, bounded evidence
below for seven days. Optional representative assets, source videos, session
directories, credentials, raw pytest output, and successful-run artifacts remain
outside this bundle.

| Artifact | Contents and boundary | Limit / use |
| --- | --- | --- |
| `weekly-media-preflight.log` | Checked-in fixture and tool readiness; no decoder run. | Separates checkout or tool failures from detector regressions. |
| `weekly-media-results.json` | Outcome counts, total duration, reviewed tool versions, up to 10 slowest normalized tests, safe skip categories, and up to 24 normalized failed test IDs. | At most 64 KiB; excludes parameter values, traceback, captured output, paths, URLs, environment values, and exception text. |
| `detector-lab-real-media/*.failure.json` | Fixture ID, requested and actual detector-row counts, versions, and allowlisted public rows. | At most 24 rows and 64 KiB per failed execution or assertion. |
| `detector-lab-real-media/*.csv` | Allowlisted per-window detector fields only. | At most 12 files, 512 KiB each, and 4 MiB total; excludes paths, source metadata, alert text, and unknown columns. |
| `ground-truth-failures/*.json` | Reviewed case context plus expected/actual counts and allowlisted alert/result fields. | At most 24 projected alerts, 24 results, and 64 KiB per case. |

Raw pytest and JUnit output remain in the job log or as an internal
result-index input; neither is uploaded. Fixture IDs must be catalog-relative names or reviewed case IDs.
All detector fields are allowlisted; configuration, headers, API keys,
database URLs, raw driver errors, source URLs, local paths, and full snapshots
are excluded. Other weekly jobs retain their separately owned failure evidence.

The weekly log prints this sanitized index after test execution. Treat its
duration, slowest-test list, and skip categories as informational baselines:
they reveal drift but never fail a run because hosted-runner timing varies.

For ordinary branch pushes and non-`main` pull requests, detector source,
detector-lab source, tests (including checked-in fixture metadata), `justfile`,
and `.github/ci_test_targets.json` all match the backend filter. The last two
also match the workflow filter so CI policy checks run when lane selection
changes. Protected `main` PRs still force the required backend work on.

### Focused Detector Registration

The baseline table above names the canonical focused and weekly targets.
`justfile` owns the local recipes, while the manifest owns the shared weekly
target. Added files and Git-detected rename destinations that split those
reviewed detector owners must appear in `test-detectors`, `test-detector-lab`,
or `test-real-media`; protected PR CI verifies this through the
`focused_detector_recipe` registration surface.

`tests/test_ci_workflow.py` protects this admission policy, routine exclusion
of slow and external confidence, weekly target membership, and the bounded
failure-artifact contract. Keep assertions behavioral: they should survive
workflow formatting changes while rejecting a lost target or widened artifact
bundle.

Representative-media calibration, runtime E2E, soak, and unrelated detector
tests remain outside this narrow guard. Do not add local focused recipes to the
manifest only to satisfy registration; move a test only when its validation
owner actually changes.

## Important Distinctions

Keep these five distinctions explicit when reviewing or editing CI:

- `main-gate` is the external required status for `main` branch
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

- workflow entrypoints
  - `CI`
    - runs on `pull_request`
    - owns the protected `main-gate` status
  - `Branch CI`
    - runs on `push` for all branches except `main`
    - owns ordinary fast branch feedback so push runs do not emit competing
      `main-gate` contexts
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
  - `main-gate`
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

- `main-gate`

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

Why the workflow split exists:

- `CI` is PR-only so the required `main-gate` context is emitted by one
  workflow only
- `Branch CI` keeps ordinary branch push feedback without producing a second
  workflow/check context that can confuse merge readiness on the same commit

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
  - protected shared lane behind `main-gate`
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
- GitHub branch protection should keep requiring `main-gate`, not a
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

## GitHub Settings Shape

The workflow contract is now explicit both in-repo and in GitHub settings. The
active repository ruleset targeting `main` owns the external protection layer:

- required external status: `main-gate`
- pull request required: yes
- required approvals: `0`
- stale approvals dismissed on push: no
- latest-push approval required: no
- branch deletion blocked: yes
- force pushes blocked: yes
- bypass actors: none

Keep GitHub protection centered on that ruleset:

- require `main-gate`, not older leaf statuses
- keep `main` under the repository ruleset instead of reintroducing overlapping
  classic branch protection
- confirm an occasional real PR against `main` still shows the protected
  statuses exactly as documented

Team-oriented review strictness can increase later, but it is a policy choice
rather than a code-correctness requirement:

- `dismiss_stale_reviews_on_push`
  - keep `false` for now to avoid extra friction while the repo is still
    mostly solo or small-team driven
- `require_last_push_approval`
  - keep `false` for now for the same reason
- `required_approving_review_count`
  - keep `0` for now because this repo currently treats `main-gate` as
    the primary merge barrier and does not need approval friction for a
    solo-maintained `main`
- revisit both settings if the repo moves to a larger team, stricter reviewer
  handoff, or enterprise-style merge control expectations

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

Workflow regression coverage intentionally stays narrow. The protected
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

Focused local validation for this workflow-contract surface:

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
- session-store persistence changes moving with focused store tests and
  session persistence docs
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
