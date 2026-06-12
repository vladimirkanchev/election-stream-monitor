# Testing And Validation

This document summarizes how the repo is currently validated and where deeper
confidence still needs to be built.

Use it for verification commands and validation scope.
Do not use it as a detailed architecture or contract doc.

Keep two confidence lanes separate when reading this document:

- production runtime confidence
  - supported backend/frontend behavior
  - built-in detectors, built-in alert rules, session/runtime flows
- detector-lab experiment confidence
  - detector comparison work
  - practical lab-only alert policies
  - motion-blur exploration and scoring experiments

Passing detector-lab validation improves confidence in experiment work, but it
does not by itself promote that logic into the supported production runtime.

For detector and alert work specifically, keep this mental split:

- production confidence asks:
  - do built-in detectors still emit the right facts?
  - do production rules still enter, suppress, recover, and emit correctly?
- detector-lab confidence asks:
  - do experiment metrics and practical policies still behave as expected on
    the checked-in fixture slices?

For a shorter CI ownership handoff, use
[ci-maintainer-guide.md](./ci-maintainer-guide.md).

## Routine Validation

For everyday detector/rule work, the most useful focused checks are usually:

- production detector and rule slices
- detector-lab practical/experiment slices when the change is experimental

Current focused ownership map:

- `tests/test_detectors.py`
  - production detector rows, media-tool fallback behavior, and metric contracts
- `tests/test_alert_rules.py`
  - shared rule metadata, failure wrapping, and row annotation behavior
- `tests/test_alert_rules_black.py`
  - `video_metrics` black-screen entry, recovery, and source/session isolation
- `tests/test_alert_rules_blur.py`
  - `video_blur` warm-up, motion guards, recovery, and source/session isolation
- `tests/test_detector_lab.py`
  - detector-lab runner wiring, experiment families, practical alert policies,
    and export shaping
- `tests/test_detector_lab_real_media.py`
  - slower real-media confidence lane for detector-lab motion/flow behavior

Use two explicit backend modes when validating this branch:

- everyday synthetic checks
  - force `ESM_ALERT_STORE_BACKEND=file`
  - leave `POSTGRES_ALERT_STORE_REAL_SMOKE` unset or `0`
- live Postgres confidence
  - set `ESM_ALERT_STORE_BACKEND=postgres`
  - set `POSTGRES_ALERT_STORE_REAL_SMOKE=1`
  - provide `ESM_POSTGRES_ALERT_DATABASE_URL`

The fast PR/branch CI workflow now pins the synthetic path to the file-backed
alert backend. The weekly workflow owns the real Postgres confidence jobs and
overrides that default in its dedicated live-DB lanes.

For detector-lab specifically:

- focused detector-lab tests and fixture runs validate experimental comparison
  logic
- they are valuable for promotion candidates
- they should not be read on their own as proof that an experimental detector
  or alert lane is runtime-ready

Useful focused examples:

```bash
cd /home/vlad/Projects/election-stream-monitor && \
PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \
.venv/bin/pytest -p no:cacheprovider \
tests/test_detectors.py \
tests/test_processor.py \
tests/test_alert_rules.py \
tests/test_alert_rules_black.py \
tests/test_alert_rules_blur.py -q
```

```bash
cd /home/vlad/Projects/election-stream-monitor && \
PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \
.venv/bin/pytest -p no:cacheprovider \
tests/test_detector_lab.py -q -k 'practical or build_experiment_window_facts or prefers_motion_blur_classification or blend or optical_flow or motion_coherent_variant or compression_robust or structure_relief'
```

If you want the standardized local harness entrypoint instead of copying the
commands directly, use the matching `justfile` recipes:

- harness design note:
  - focused lanes are the source of truth
  - broader lanes such as `just test-fast` and `just ci-local` compose them
    so local validation stays aligned with the project seams
- `just env-check`
  - lightweight local tool and version sanity check
  - confirms `python3`, `node`, `ffmpeg`, and `just`
- `just test-detectors`
  - focused production detector contract and metric lane
- `just test-processor`
  - focused production processor and orchestration lane
- `just test-alert-rules`
  - focused production alert-rule policy lane
- `just test-hls`
  - focused HLS / `api_stream` loader, reconnect, and limits lane
  - narrower than the broader weekly `api_stream` deep-validation suites
- `just test-frontend`
  - focused frontend runtime and bridge checkpoint lane
  - useful for renderer, bridge, and Electron-facing UI changes
- `just docs-check`
  - docs/workflow consistency and CI-target ownership lane
  - validates the current manifest-backed CI and maintainer-doc alignment
- `just branch-cleanup`
  - non-destructive branch hygiene lane
  - shows branch name, status, upstream divergence, and changed-file summaries
- `just test-fast`
  - composed fast production runtime lane:
    `test-detectors`, `test-processor`, `test-alert-rules`, and
    `test-frontend`
  - intentionally smaller than the full fast synthetic backend CI lane
- `just test-detector-lab`
  - fast detector-lab synthetic and runner/export confidence lane
- `just test-real-media`
  - slower detector-lab real-media confidence lane backed by checked-in
    fixtures
- `just lint`
  - backend Ruff plus frontend ESLint
- `just typecheck`
  - backend mypy, backend pyright, and frontend TypeScript typecheck
- `just ci-local`
  - best local "ready to push?" lane
  - mirrors the current fast branch-feedback CI shape more closely:
    `backend-tests` fast synthetic lane, `frontend-checkpoint`, backend Ruff,
    backend mypy, backend pyright, frontend ESLint, and frontend typecheck
  - intentionally does not replace weekly slow lanes or PR-only consistency
    guards

## CI Shape

The current GitHub Actions workflow uses three practical layers:

- `changes`
  - path filter job that classifies backend, frontend, docs, workflow, and contract-sensitive edits
- `frontend-checkpoint`
  - quick Electron/bridge/session-flow regression signal
- `backend-tests`
  - packaging/import smoke check after editable install
  - compile smoke check for the compact session-alert report module and CLI
  - backend tests
- `backend-ruff`
  - primary Python lint check with Ruff
- `frontend-typecheck`
  - frontend TypeScript typecheck
- `frontend-lint`
  - advisory frontend ESLint signal on `src` TypeScript files
- `feature-gate`
  - summary job for the fast backend/frontend checks on pull requests
  - useful as a single CI signal, even though feature branches are no longer
    protected merge targets
- `contract-checks`
  - boundary-focused backend and frontend contract checks for PRs
- `backend-typecheck`
  - targeted type defense for the contract-sensitive Python boundary modules
- `backend-pyright`
  - advisory VSCode-aligned type signal for the same Python boundary modules
- `test-and-build`
  - full frontend tests
  - frontend build
- `main` pull-request guards
  - a small integration smoke test
  - a lightweight docs/contract consistency check
  - contract-sensitive changes must move with nearby tests and owning docs
- `docs-consistency`
  - path-aware docs and workflow consistency checks for non-`main` pull requests
- `weekly-validation`
  - scheduled slow e2e media tests
  - detector-lab real-media confidence checks
  - lifecycle-focused backend test coverage
  - deeper `api_stream` validation
  - Bandit security audit
  - `pip-audit` Python dependency scan
  - `npm audit` frontend dependency scan
  - dependency consistency check
  - packaging smoke check

Failure-only artifacts are now uploaded for the heaviest backend PR lane, the
weekly lifecycle lane, the slow e2e lane, and the weekly `api_stream`
deep-validation lane, starting with plain test logs.
The weekly lifecycle lane also uploads the persisted session files that most
often explain runner state, cancel behavior, and terminal outcomes.

This keeps ordinary branch feedback reasonably fast while giving `main` a
stricter merge barrier.

Feature branches now rely on CI feedback rather than required branch
protection. The protected workflow still runs on pull requests and now also
runs on feature-branch pushes so branch work gets feedback before a PR exists.
`main` stays out of the push trigger to avoid duplicate status contexts, and
stale PR runs are canceled automatically with GitHub Actions concurrency.

The workflow is now path-aware:

- backend-heavy work runs only when backend or contract files change
- frontend-heavy work runs only when frontend or contract files change
- docs/workflow consistency checks run on docs-oriented pull requests
- PRs into `main` still receive the full validation set
- contract-boundary edits on `main` PRs are expected to come with matching
  tests and the owning docs update

Current `changes` filter contract:

- `backend`
  - broad backend trigger
  - paths: `src/**`, `tests/**`
  - main direct gates: `backend-tests`, `backend-ruff`, `backend-typecheck`, `backend-pyright`
  - also feeds: `frontend-checkpoint`, `contract-checks`, `test-and-build`
- `frontend`
  - broad frontend trigger
  - paths: `frontend/**` except `frontend/README.md`
  - main direct gates: `frontend-checkpoint`, `frontend-typecheck`, `frontend-lint`
  - also feeds: `contract-checks`, `test-and-build`
- `docs`
  - docs-oriented consistency trigger
  - paths: `docs/**`, `README.md`, `frontend/README.md`
  - direct gate: `docs-consistency` on non-`main` pull requests
- `workflow`
  - CI/support-tooling trigger
  - paths: `.github/workflows/**`, `.github/scripts/**`, `frontend/package.json`, `pyproject.toml`
  - direct gate: `docs-consistency` on non-`main` pull requests
- `contract`
  - narrower contract-sensitive trigger
  - paths: selected backend boundary files, current session/stream contract owners, `frontend/src/bridge/**`, contract-sensitive monitoring hooks, `frontend/src/types.ts`, and `frontend/src/uiErrors.ts`
  - main direct gates: `frontend-checkpoint`, `backend-tests`, `backend-ruff`, `frontend-typecheck`, `frontend-lint`, `backend-typecheck`, `backend-pyright`, `docs-consistency`
  - also feeds: `contract-checks`, `test-and-build`

Filter intent:

- broad convenience scopes: `backend`, `frontend`
- narrower high-signal scopes: `contract`, `workflow`
- docs-oriented policy scope: `docs`

`backend` and `frontend` stay intentionally coarse. `contract` is the curated
cross-boundary signal and should be read more precisely.

Current contract-filter refinement result:

- added: `src/stream_loader.py`, `src/stream_loader_http_hls.py`,
  `src/session_runner.py`, `src/session_runner_progress.py`,
  `src/session_service.py`,
  `frontend/src/hooks/useMonitoringSession*.tsx`,
  `frontend/src/hooks/usePlaybackSource*.tsx`,
  `frontend/src/uiErrors.ts`
- intentionally left out: docs-only ownership such as `docs/contracts.md`,
  weekly-only owners, and electron trust/playback files that still belong to
  a local-only policy gate

Current broad-filter review result:

- `backend` stays broad as `src/**` plus `tests/**`
  - reason: narrowing it now would add more under-trigger risk than real CI savings
- `frontend` stays broad for real frontend work, but now excludes the docs-only
  handoff file `frontend/README.md`
  - reason: that file already belongs to the `docs` trigger
- no broader exclusions were applied yet for tracked frontend source, Electron,
  package, or config files
  - reason: those files still have meaningful impact on current frontend lanes

Downstream trigger model in `ci.yml` now matches that intent:

- backend-heavy jobs (`backend-tests`, `backend-ruff`, `backend-typecheck`,
  `backend-pyright`)
  - wake on `backend` or `contract`, plus protected `main` PR fallback
- frontend-heavy jobs (`frontend-typecheck`, `frontend-lint`)
  - wake on `frontend` or `contract`, plus protected `main` PR fallback
- `frontend-checkpoint`
  - wakes on `frontend`, `backend`, or `contract`, plus protected `main` PR fallback
- PR-only boundary lanes (`contract-checks`, `test-and-build`)
  - can be reached from broad `backend` / `frontend` scopes or the narrower `contract` scope
- `docs-consistency`
  - stays the non-`main` PR lane for `docs`, `workflow`, and narrower `contract` alignment work

`main` pull requests still run the protected lanes even when these branch-level
filters would otherwise skip them.

The CI hardening owner is `.github/ci_test_targets.json`. For the short owner
surface map, use [ci-maintainer-guide.md](./ci-maintainer-guide.md).

Key Python-side consumers:

- `.github/scripts/ci_target_manifest.py`
  - shared manifest access seam for target groups, lane ownership, path
    inventory, and the protected alignment model
- `.github/scripts/read_ci_test_targets.py`
  - resolves one stable target group for workflow shell steps
- `.github/scripts/validate_ci_test_targets.py`
  - checks manifest shape, approved scope, target hygiene, and lane ownership
- `.github/scripts/check_ci_test_paths_exist.py`
  - checks that CI-owned test paths still exist, including the inline smoke
    exception and the policy-owned paths from
    `.github/scripts/check_main_pr_consistency.py`
- `.github/scripts/check_ci_target_drift.py`
  - checks that manifest, workflows, `.github/scripts/check_main_pr_consistency.py`,
    and CI-facing docs still agree on the protected contract lane
- `tests/test_ci_test_target_scripts.py`
  - focused coverage for the shared path inventory, lane-helper seam, current
    drift outcomes, and split-suite registration outcomes
  - includes split-suite checks for:
    accepted-surface semantics, guarded-pattern matching, mixed changed-file
    batches, and representative owner-seam alignment
  - also covers the high-signal `changes` filter assumptions that now protect
    the refined contract trigger and the docs-only `frontend/README.md`
    exclusion

Those checks are complementary:

- `validate_ci_test_targets.py` catches bad manifest shape or scope
- `check_ci_test_paths_exist.py` catches missing CI-owned test files
- `check_ci_target_drift.py` catches workflow/policy/docs drift

The chosen manifest format is JSON. That keeps the source of truth easy to read
in Python tooling and straightforward to consume from workflow shell steps via
`python3`, without adding an extra YAML parser dependency.

Stable target groups:

- `backend_contract`
- `mcp_fastapi_parity`
- `frontend_contract`
- `weekly_slow_media`
- `weekly_api_stream_deep`
- `weekly_lifecycle`

Reader example:

```bash
python3 .github/scripts/read_ci_test_targets.py backend_contract --separator space
```

Workflow consumers:

- `test-and-build`
  - `contract_boundary` backend contract checks read `backend_contract` and
    `mcp_fastapi_parity`
  - `contract_boundary` frontend contract checks read `frontend_contract`
  - the job now validates the manifest boundary before resolving those groups
  - both shared contract checks resolve their targets through
    `read_ci_test_targets.py`
  - the frontend lane strips the leading `frontend/` prefix because Vitest runs
    from the `frontend/` working directory
- `weekly-validation`
  - `weekly_slow_real_media` slow media reads `weekly_slow_media`
  - `weekly_slow_real_media` deeper `api_stream` validation reads
    `weekly_api_stream_deep`
  - `weekly_slow_real_media` lifecycle validation reads `weekly_lifecycle`
  - each weekly heavy job now validates the manifest boundary before resolving
    its target group

This section is the primary CI lane-ownership reference for the repo. Keep the
full lane explanation here, and keep shorter CI mentions in `docs/README.md`
and `docs/contracts.md` role-specific.

Lane-ownership model:

- `fast_synthetic`
  - owner jobs:
    `backend-tests`
  - purpose:
    lightweight synthetic pytest coverage and fast PR/branch feedback such as
    `-m "not e2e and not slow"`
  - excludes:
    shared contract groups, real-media or `ffmpeg`-dependent suites, and
    weekly-only deep lifecycle or `api_stream` coverage
- `contract_boundary`
  - owner jobs:
    `test-and-build`, `integration-smoke`
  - purpose:
    manifest-backed shared backend/frontend contract checks in
    `test-and-build` plus the tiny inline `integration-smoke` exception
  - excludes:
    broad fast-lane backend selectors, weekly-only heavy suites, and lint /
    typecheck / security / packaging support jobs
- `weekly_slow_real_media`
  - owner jobs:
    `slow-e2e`, `api-stream-deep`, `lifecycle-deep`
  - purpose:
    `weekly_slow_media`, `weekly_api_stream_deep`, `weekly_lifecycle`, and the
    slower real-media / `ffmpeg` / deeper confidence-building suites
  - excludes:
    fast PR feedback lanes, protected contract-lane equality, and tiny local
    smoke paths

These category definitions live in `.github/ci_test_targets.json`, so the repo
has one official CI lane vocabulary. The manifest also assigns each shared
target group to one canonical lane category, and
`.github/scripts/ci_target_manifest.py` exposes that mapping to Python-side CI
helpers.

The executable seam is:

- `group_lane_categories` in `.github/ci_test_targets.json`
- `.github/scripts/ci_target_manifest.py`
  - `manifest_group_lane_category_name(...)`
  - `manifest_lane_groups(...)`
  - `lane_group_map()`

`validate_ci_test_targets.py` now also enforces that:

- `contract_boundary` owns only the protected shared PR contract groups
- `weekly_slow_real_media` owns only the weekly-only shared groups
- `fast_synthetic` owns no shared manifest groups at all

Adjacent CI jobs that are not lane owners:

- `frontend-checkpoint`
- `backend-ruff`
- `frontend-typecheck`
- `frontend-lint`
- `backend-typecheck`
- `backend-pyright`
- security and dependency audit jobs
- summary/coordination jobs such as `changes`, `feature-gate`, and
  `docs-consistency`

Selector ownership summary:

- shared contract and weekly-heavy suites are manifest-backed
- `test-and-build` is the reader-backed execution path for shared
  `contract_boundary` coverage
- `integration-smoke` stays inline because it is a tiny local smoke path
- `backend-tests` stays the `fast_synthetic` pytest marker lane

Current path-owning CI consumers for the existence self-check:

- workflow manifest groups
  - `backend_contract`
  - `mcp_fastapi_parity`
  - `frontend_contract`
  - `weekly_slow_media`
  - `weekly_api_stream_deep`
  - `weekly_lifecycle`
- workflow inline test paths
  - `tests/test_e2e_local_session.py`
- policy manifest groups
  - `backend_contract`
  - `mcp_fastapi_parity`
  - `frontend_contract`
- policy-only test paths
  - the narrower backend, frontend bridge, and electron trust/playback test
    tuples in `.github/scripts/check_main_pr_consistency.py`

That inventory is broader than the manifest alone because the one inline
smoke-path exception and the policy-only test paths can drift too.

Path-existence self-check boundary:

- included
  - manifest target entries
  - inline workflow test paths
  - policy-only test paths
- excluded
  - non-test source paths
  - docs expectations
  - glob-like selectors if they appear later

That boundary keeps the check precise. It is meant to catch stale
CI-owned test paths early, not to act as a general repo linter.

The validator already protects that scope contract, so the existence check runs
on a stable documented boundary instead of inventing its own rules.

Split-suite registration guard:

What counts as a guarded split suite:

- backend contract and session-service split suites
  - `tests/test_api_boundary_*.py`
  - `tests/test_api_alert_route_*.py`
  - `tests/test_api_session_alert*.py`
  - `tests/test_alert_query_service_*.py`
  - `tests/test_alert_timeline_service_*.py`
  - `tests/test_alert_incident_summary_service_*.py`
  - `tests/test_api_server_cli_*.py`
  - `tests/test_mcp_server_*.py`
  - `tests/test_session_service_*.py`
  - `tests/test_session_cli_*.py`
- `api_stream` and HTTP/HLS boundary split suites
  - `tests/test_stream_loader*.py`
  - `tests/test_session_runner_api_stream*.py`
- frontend bridge and hook contract split suites
  - `frontend/src/bridge/*.test.ts`
  - `frontend/src/hooks/useMonitoringSession*.test.tsx`
  - `frontend/src/hooks/usePlaybackSource*.test.tsx`
- local-only Electron policy suites
  - `frontend/electron/*.test.mjs`

This surface stays narrower than the whole repo so the guard can catch
high-signal split-suite ownership misses without policing every new test file.

What registration is required:

- update the manifest if the new file belongs to a shared CI target group
- update `check_main_pr_consistency.py` ownership if the new file belongs to
  the main-PR policy layer
- update docs only when the ownership meaning changes:
  - a new guarded area
  - a new shared ownership category
  - a policy-boundary change

This stays intentionally narrow. It does not require docs churn for every new
test file, and it does not treat unguarded test files as CI-registration
failures.

Where to update ownership when this guard fails:

- shared manifest ownership
  - update `.github/ci_test_targets.json`
  - use `.github/scripts/ci_target_manifest.py` as the read-side helper seam
- main-PR policy ownership
  - update `.github/scripts/check_main_pr_consistency.py`
- docs ownership
  - update this file only when ownership meaning changes
  - keep `docs/README.md` and `docs/contracts.md` as shorter handoff docs,
    not full duplicate owners

Chosen detection strategy for the live registration guard:

- inspect changed files in protected PR CI
- do not scan the full repo or try to infer historical split ownership

That keeps the guard cheaper, clearer, and more maintainable. It should
fail when a new guarded file is introduced without the required ownership
updates, not re-lint the whole repository on every run.

Split-suite registration command:

```bash
python3 .github/scripts/check_split_suite_registration.py <diff-range>
```

Current registration surfaces checked by that guard:

- `shared_manifest`
  - the new file is present in one shared manifest-backed target group
- `policy_owned`
  - the new file is present in the main-PR policy owner surface
- `local_only_policy`
  - the new file is present in the local-only policy owner surface

The current rule is still intentionally narrow:

- most guarded areas accept either `shared_manifest` or `policy_owned`
- the Electron local-only area requires `local_only_policy`
- docs changes are required only when:
  - the ownership model changes
  - a new guarded split-suite category appears
  - policy-boundary meaning changes
- ordinary split-file additions that stay within an existing guarded area and
  ownership model do not require docs churn on their own

Where to update ownership:

- shared manifest ownership
  - update `.github/ci_test_targets.json`
  - read-side helper seam: `.github/scripts/ci_target_manifest.py`
- main-PR policy ownership
  - update `.github/scripts/check_main_pr_consistency.py`
- docs ownership
  - update this file only when ownership meaning changes
  - keep `docs/README.md` and `docs/contracts.md` as shorter handoff docs

How the guard detects new files:

- inspect changed files in protected PR CI
- do not scan the full repo or infer historical ownership

That keeps the guard cheaper and clearer. It should fail when a new guarded
file is introduced without the required ownership updates, not re-lint the
whole repository on every run.

Command:

```bash
python3 .github/scripts/check_split_suite_registration.py <diff-range>
```

Owner seams used by the guard:

- `.github/scripts/ci_target_manifest.py`
  - `shared_manifest_test_paths()`
  - `matching_guarded_split_suite_areas(...)`
- `.github/scripts/check_main_pr_consistency.py`
  - `policy_owned_test_paths()`
  - `local_only_policy_test_paths()`

Protected PR lanes now run that guard after drift alignment and before broader
policy or contract work. The current protected order is:

1. manifest structure and scope
2. CI-owned test-path existence
3. workflow, policy, and docs drift alignment
4. split-suite registration for newly added guarded files
5. broader policy or shared contract execution

CI-owned test-path existence command:

```bash
python3 .github/scripts/check_ci_test_paths_exist.py
```

What this guard owns:

- missing-file validation for CI-owned test paths
- the inline workflow exception slice
- policy-only and local-only gate test expectations
- the manifest-to-policy ownership link for policy-only test paths

What it does not own:

- manifest structure and scope validation
  - that belongs to `validate_ci_test_targets.py`
- workflow/policy/docs alignment validation
  - that belongs to `check_ci_target_drift.py`
- general source-path or docs-path ownership checks
  - those stay outside this guard on purpose

That split keeps the new structural guard small, explicit, and hard to confuse
with the broader validator or drift check.

Current alignment contract enforced by `check_ci_target_drift.py`:

- workflow-to-manifest alignment
  - the shared reader-backed contract groups in `ci.yml` `test-and-build`
    must match the protected alignment group set:
    - `backend_contract`
    - `mcp_fastapi_parity`
    - `frontend_contract`
- policy-to-workflow alignment
  - manifest groups consumed by manifest-backed `ContractGate` entries in
    `check_main_pr_consistency.py` must match the shared reader-backed
    `test-and-build` contract groups in `ci.yml`
- docs-to-manifest alignment
  - `docs/testing-and-validation.md`, `docs/README.md`, and
    `docs/contracts.md` must keep the high-signal CI ownership references that
    match their role

The protected alignment contract now lives behind the shared Python seam in
`.github/scripts/ci_target_manifest.py`, so the drift checker consumes one
explicit model instead of carrying those expectations inline. Workflow-side
group extraction comes from that helper too, with multiline-shell normalization
and `python`/`python3` tolerance. On the policy side, the drift checker reads
manifest-group usage from the explicit `manifest_policy_groups()` helper in
`.github/scripts/check_main_pr_consistency.py`.

The docs-side check is intentionally narrow:

- `docs/testing-and-validation.md`
  - must keep the protected alignment groups and the key CI ownership helpers
- `docs/README.md`
  - must keep the top-level ownership handoff references
- `docs/contracts.md`
  - must keep the contract-relevant CI ownership references

It does not require every CI-facing doc to repeat every manifest group or
helper name. The goal is ownership clarity, not repetition.

What is intentionally outside that equality rule:

- weekly-only manifest groups
- the tiny inline `integration-smoke` path
- non-manifest workflow behavior

So the current alignment check is intentionally about the protected contract
lane, not the whole workflow universe.

Protected CI lane order:

1. `validate_ci_test_targets.py`
2. `check_ci_test_paths_exist.py`
3. `check_ci_target_drift.py`
4. broader workflow or policy checks

That keeps missing-path failures early, fast, and easier to read than later
policy or contract-lane failures.

This order applies to the protected PR lanes:

- `main-pr-consistency`
- `test-and-build`
- `docs-consistency`

The broader policy or contract work does not start until the manifest
boundary, CI-owned path inventory, and protected-lane alignment contract are
already healthy. Weekly heavy lanes still validate the manifest first, but
they do not run the protected-lane existence/drift sequence before their
slower suites.

Current focused test:

```bash
pytest -q tests/test_ci_test_target_scripts.py
```

That focused test also covers the workflow-reader extraction seam used by the
drift check, the explicit policy-group helper it consumes, the lane-helper
API, and the main drift outcomes it reports.

Ownership summary:

- the manifest owns the shared CI target groups
- `.github/scripts/check_main_pr_consistency.py` owns the narrower main-PR
  policy layer
- the policy layer keeps only:
  - gate activation rules
  - docs expectations
  - policy-only test expectations that are intentionally narrower than the
    shared CI groups

Policy consumer:

- backend contract gate reuses:
  - `backend_contract`
  - `mcp_fastapi_parity`
- frontend bridge gate reuses:
  - `frontend_contract`
- electron trust/playback stays local-only until the repo gives it a shared
  CI target group
- each policy gate now reads as:
  - label
  - changed paths
  - manifest groups
  - policy-only tests
  - docs expectations
- that keeps the script narrower than the workflow lanes it references, so it
  does not become a second target manifest

Current frontend contract targeting baseline:

- shared manifest group:
  - `frontend_contract`
  - current targets:
    - `frontend/src/bridge/contract.success.test.ts`
    - `frontend/src/bridge/contract.errors.test.ts`
    - `frontend/src/bridge/contract.session-snapshot.shape.test.ts`
    - `frontend/src/bridge/contract.session-snapshot.malformed.test.ts`
    - `frontend/src/bridge/contract.session-snapshot.collections.test.ts`
    - `frontend/src/bridge/transport.test.ts`
    - `frontend/src/uiErrors.test.ts`
- workflow consumer:
  - `test-and-build` runs the frontend `contract_boundary` lane with:
    `npm run test -- $(python3 ../.github/scripts/read_ci_test_targets.py frontend_contract --separator space --strip-prefix frontend/)`
  - the shared reader stays necessary because Vitest runs from the
    `frontend/` working directory while the manifest stores repo-root paths
- policy consumer:
  - the `frontend bridge contract` gate in
    `.github/scripts/check_main_pr_consistency.py` reuses
    `frontend_contract`
  - that gate is still intentionally narrower than the full workflow lane and
    now keeps only narrower frontend policy-only tests for:
    - `frontend/src/hooks/useMonitoringSession.lifecycle.test.tsx`
    - `frontend/src/hooks/useMonitoringSession.apiStream.test.tsx`
    - `frontend/src/hooks/usePlaybackSource.test.tsx`
- current focused regression coverage:
  - `tests/test_ci_test_target_scripts.py` now locks in:
    - the exact `frontend_contract` manifest targets
    - the remaining hook-only policy slice
    - the live workflow reader command

Final frontend ownership model:

- shared manifest lane:
  - `frontend_contract`
  - owns the stable bridge, transport, and `uiErrors` contract suites
- policy-only frontend lane:
  - `frontend/src/hooks/useMonitoringSession.lifecycle.test.tsx`
  - `frontend/src/hooks/useMonitoringSession.apiStream.test.tsx`
  - `frontend/src/hooks/usePlaybackSource.test.tsx`
- local-only frontend-adjacent lane:
  - Electron trust/playback expectations

Why the hook suites stay policy-only:

- they sit downstream of the shared bridge contract rather than defining it
- they assert hook-level polling, reconnect, terminal-state, and playback
  behavior after bridge normalization
- they are closer to operator-facing lifecycle and playback semantics than to
  the narrower shared bridge/transport payload contract
- moving them into `frontend_contract` now would broaden the shared workflow
  lane more than it would reduce real duplication

That keeps the shared manifest lane focused and leaves the narrower hook and
Electron expectations outside that workflow-owned contract surface.

The slower confidence-building checks run weekly instead of on every PR, so
the repo gets a broader safety net without turning normal branch work into a
long queue.

### Backend

The Python suite covers:

- detector and alert-rule behavior
- session runner lifecycle
- session persistence and snapshot assembly
- `api_stream` validation and loading
- loader contract helpers and deterministic seam behavior
- HLS/provider edge cases and soak-oriented scenarios

Detector and alert coverage is now split so the ownership is easier to scan:

- `tests/test_detectors.py`
  - typed detector rows, media-tool degradation, and blur/black metric contracts
- `tests/test_alert_rules.py`
  - metadata, failure wrapping, malformed payload tolerance, and detector isolation
- `tests/test_alert_rules_black.py`
  - `video_metrics` black-screen rule state transitions
- `tests/test_alert_rules_blur.py`
  - `video_blur` rolling/recovery rule state transitions
- `tests/test_detector_lab.py`
  - detector-lab runner, export shaping, experiment families, practical alert
    policies, and optical-flow / motion-coherence seams

Current blur-validation expectation:

- calibrate `video_blur` first against clean baseline clips from the media
  family you actually care about
- use the checked-in blur fixtures to prove positive detection
- use real-source clean baseline clips to prove the detector does not over-alert
  on naturally soft but acceptable broadcast footage
- include startup-heavy clips when validating blur behavior, because first-frame
  false positives are now handled in the blur rule through a minimum-sample
  warm-up gate
- include motion-heavy clean clips as a separate blur baseline, because the
  blur rule now uses detector-side motion summaries to suppress moving-camera
  softness before it becomes an alert
- keep black-screen fixtures in the validation set, because the blur detector
  now explicitly drops effectively black frames and that separation should stay
  intact
- keep malformed media in a separate resilience lane; the default
  `detector_lab --fixture-set test_video_files` batch intentionally stays on
  valid detector-quality MP4 fixtures so blur and black-score calibration
  output remains easy to read

Common local command:

```bash
. .venv/bin/activate
pip install -e .[test]
pytest -q -m "not e2e and not slow"
```

This default backend command keeps the normal local fast lane focused on unit,
service, and boundary coverage. Use the dedicated e2e commands below when you
want the snapshot-contract smoke check or the slower real-media matrix.

Focused detector-lab validation:

```bash
PYTHONPATH=src:. python3 -m detector_lab.cli \
  --fixture-set test_video_files \
  --output detector_lab/output/test_video_files_eval.csv
```

This writes the compact production-fixture detector export:

- one merged row per analyzed second/window
- one `row_index` column for quick scanning
- one combined view of the current `video_blur` and `video_metrics` outputs

Focused repo-local skill validation:

```bash
.venv/bin/pytest -q tests/test_repo_skills.py
```

This skill-focused test slice is intentionally no-key and deterministic.
It currently covers:

- the current repo-local skill inventory, frontmatter, and section structure
- readable section ordering
- explicit hand-off boundaries between the skills
- ambiguous-prompt coverage for nearby skills that could overlap
- explicit handoff checks where one skill should defer to another
- merged-skill regression markers for the newer multi-mode skills
- branch/PR/readiness guidance around drift, commit shape, cleanup safety, and merge readiness
- alert-backend parity guidance around file-backed versus PostgreSQL-backed store behavior and shared alert-read consistency
- CI failure classification and smallest-lane reproduction coverage
- detector/rule review guidance around runtime coupling, boundary drift, and missing focused tests
- concise summary guidance for PR notes, behavior-impact framing, and next-action clarity
- dependency-change review guidance for `pyproject.toml` and `uv.lock` drift decisions
- docs drift guidance that points back to the owning README or maintainer doc,
  and also covers module/class/function docstring drift explicitly
- fixture and environment safety guidance around local-only assets, sockets, and tool assumptions
- frontend/bridge review guidance around renderer ownership, preload normalization, polling, playback, and UI-runtime seams
- manual smoke-plan guidance for Electron, FastAPI, playback, alerts, and other operator-visible checks before merge
- security-surface review guidance around FastAPI, MCP, local sharing, and trust-boundary clarity
- task-planning guidance around repo-stage-aware ratings and phased next steps
- test-strategy guidance that now covers all three current modes:
  - missing coverage and lane placement
  - redundancy and environment-coupled confidence
  - smallest honest local validation lane selection
- golden scenario coverage for current repo use cases
- snapshot-style expected outputs for selected fixed prompts
- lightweight regression coverage for real repo incidents

Focused alert-query, seam, incident, and MCP validation:

```bash
.venv/bin/pytest -q tests/test_api_auth.py tests/test_api_rate_limit.py tests/test_api_boundary_settings_env.py tests/test_api_boundary_settings_validation.py tests/test_api_boundary_error_contracts.py tests/test_api_server_cli_runtime.py tests/test_api_server_cli_routes.py tests/test_api_server_cli_output.py tests/test_api_alert_route_auth_policy.py tests/test_api_alert_route_rate_limit_policy.py tests/test_api_alert_route_contracts.py tests/test_alert_query_service_read.py tests/test_alert_query_service_filter.py tests/test_alert_query_service_summary.py tests/test_alert_timeline_service_grouping.py tests/test_alert_timeline_service_filters.py tests/test_alert_incident_summary_service_contracts.py tests/test_alert_incident_summary_service_filters.py tests/test_session_alert_store.py tests/test_session_alert_store_runtime.py tests/test_session_alert_store_runtime_config.py tests/test_session_alert_store_parity.py tests/test_session_alert_store_postgres.py tests/test_session_alert_store_postgres_config.py tests/test_session_io.py tests/test_session_runner_execution_local.py tests/test_api_session_alerts.py tests/test_api_session_alert_incidents.py tests/test_mcp_server_contracts.py tests/test_mcp_server_alerts_behavior.py tests/test_mcp_server_alerts_errors.py tests/test_mcp_fastapi_boundary_split.py tests/test_mcp_fastapi_parity_behavior.py tests/test_mcp_fastapi_parity_edges.py tests/test_mcp_server_incidents_behavior.py tests/test_mcp_server_incidents_errors.py
```

This slice covers the shared read-only alert query service, the FastAPI alerts
boundary, and the MCP adapter over the same service seam. If you change only
one of those layers, this is still the best quick confidence check because it
proves the ownership split still lines up.

The normal local pass stays synthetic by default. The live PostgreSQL alert
smokes are opt-in and currently need:

- `POSTGRES_ALERT_STORE_REAL_SMOKE=1`
- `ESM_POSTGRES_ALERT_DATABASE_URL=postgresql://...`
- usually `ESM_ALERT_STORE_BACKEND=postgres` when the test exercises the
  runtime-selected backend path rather than the store in isolation

Use the live smokes when you need confidence in the real database path:

- connection/bootstrap behavior
- real SQL insert/read behavior
- snapshot/API/CLI behavior over the active Postgres backend

For this branch, the smallest useful live checks are:

- store-level smoke:
  - `tests/test_session_alert_store_postgres.py::test_real_postgres_alert_store_smoke_round_trip`
- representative public-surface smoke:
  - `tests/test_api_session_alert_incidents.py::test_live_runtime_postgres_grouped_routes_follow_actual_startup_path`

Use the synthetic suites for normal branch work. They are cheaper, faster, and
already cover most seam, parity, and boundary behavior.

For local live-Postgres validation, start PostgreSQL outside the Python
scripts. The scripts assume the database is already running and reachable.

Local options:

- local PostgreSQL service
  - start the service with your normal OS tooling
  - make sure a test database such as `election_stream_monitor` exists
- local Docker container
  - start a disposable container and map `5432:5432`

Example Docker startup:

```bash
docker run --name esm-postgres-test \
  -e POSTGRES_PASSWORD=postgres \
  -e POSTGRES_DB=election_stream_monitor \
  -p 5432:5432 \
  -d postgres:16
```

Example local env for the live checks:

```bash
export ESM_POSTGRES_ALERT_DATABASE_URL='postgresql://postgres:postgres@localhost:5432/election_stream_monitor'
export ESM_ALERT_STORE_BACKEND=postgres
export POSTGRES_ALERT_STORE_REAL_SMOKE=1
```

Quick connection sanity check before the longer bundles:

```bash
.venv/bin/python -c "import psycopg; psycopg.connect('postgresql://postgres:postgres@localhost:5432/election_stream_monitor').close(); print('ok')"
```

For weekly/manual rollout confidence, the live Postgres path is split into two
focused bundles:

- backend confidence
  - store bootstrap and real append/read round-trips
  - timestamp/order drift-sensitive checks
  - raw/grouped FastAPI route checks
  - grouped MCP agreement over the active backend
- runtime/operator-flow confidence
  - runner-written alerts through the live Postgres backend
  - session snapshot reads over the active backend
  - CLI `read-session` behavior over the active backend

Use either bundle directly:

```bash
ESM_POSTGRES_ALERT_DATABASE_URL='postgresql://...' \
python3 scripts/postgres_alert_weekly_backend_confidence.py
```

```bash
ESM_POSTGRES_ALERT_DATABASE_URL='postgresql://...' \
python3 scripts/postgres_alert_weekly_runtime_operator_confidence.py
```

Or run both with the umbrella helper:

```bash
ESM_POSTGRES_ALERT_DATABASE_URL='postgresql://...' \
python3 scripts/postgres_alert_weekly_confidence.py
```

The umbrella helper runs both bundles in order.

Use the backend bundle when:

- you want stronger real-DB confidence in storage and grouped query behavior
- you are comparing seeded alert behavior across the main public readers

Use the runtime/operator-flow bundle when:

- you want confidence in runner-written alerts under real Postgres mode
- you want to sanity-check snapshot and CLI behavior before a rollout or demo

For a quick human-readable view of one persisted session during a manual check,
use:

```bash
python3 scripts/session_alert_demo_report.py --session-id <session-id>
```

Use `--format json` when you want the same compact alert report shape in a
machine-friendly form.

Use the umbrella helper when:

- you want one repeatable weekly confidence pass
- you are preparing a rollout or demo with `ESM_ALERT_STORE_BACKEND=postgres`
- you want extra real-DB confidence before changing backend defaults later

The scheduled `weekly-validation` workflow also runs the backend and
runtime/operator bundles automatically with a disposable `postgres:16` service
container. CI does not rely on a shared external database for those weekly
checks.

Do not treat it as a normal branch-push requirement. The synthetic seam,
parity, and boundary suites remain the primary everyday validation path.

The fast backend CI lane intentionally stays synthetic and contract-focused.
The real-media `ffmpeg`/`ffprobe` fixture coverage lives in the slower weekly
e2e validation path rather than in the normal branch-push backend test job.
The same weekly validation workflow also owns the heavier confidence-building
checks for:

- real-media detector integration
- deeper `api_stream` validation
- lifecycle-focused backend regression slices
- security audits
- dependency consistency audits

It exercises the current alerts-router protection contract end to end:

- `local` mode defaults keep auth and rate limiting off
- `share` mode defaults turn auth and rate limiting on
- share mode can auto-generate one startup API key when none is configured
- protected scope
- structured `401` and `429` responses
- local in-memory/per-process limiter behavior
- coarse `Retry-After` behavior on `429`

Treat that as strong confidence for the current local/demo readiness level,
not as proof of a distributed shared-store deployment model.

The current functionality under that slice is:

- FastAPI API-key authentication seam for the alerts router
- FastAPI in-memory principal-aware rate-limiting seam for the alerts router
- raw session alert list queries
- raw numeric alert summaries
- grouped incident timelines
- grouped incident summaries
- stdio MCP launch wiring over the same shared service seam

Current alert persistence contract to preserve:

- seam owner:
  - `src/session_alert_store.py`
    - defines the narrow storage contract for append/read raw alert rows only
    - owns the runtime-selected default alert store and still defaults to the
      file-backed alert backend in this branch phase
    - filtering, summaries, and grouped incidents stay outside the store seam
  - `src/session_alert_store_runtime_config.py`
    - owns explicit `file` versus `postgres` backend selection for that default
      store through `ESM_ALERT_STORE_BACKEND`
  - `src/session_alert_store_postgres.py`
    - owns the PostgreSQL alert table, preserved read order, the small
      connection/bootstrap path, and the concrete second store implementation
  - `src/session_alert_store_postgres_config.py`
    - owns the narrow env/config parsing for the PostgreSQL bootstrap path
  - `src/session_alerts.py` and `src/session_alert_incidents.py`
    - public read-model entrypoints accept the store seam explicitly while still
      defaulting to the runtime-selected store implementation
- write entrypoint:
  - `src/session_io.py`
    - `append_alert(...)` remains the compatibility write entrypoint and now
      delegates to the default alert store implementation
    - session snapshots keep metadata, progress, and results file-backed, but
      now read their `alerts` field through that same runtime-selected seam
- read entrypoints:
  - `src/session_alerts.py`
    - raw persisted alert reads, filtering, and numeric summaries
  - `src/session_alert_incidents.py`
    - grouped timeline and incident-summary reads built on the raw alert layer
  - `src/session_alert_adapter.py`
    - shared FastAPI/MCP adapter seam for filter forwarding and domain-error mapping
- preserved semantics:
  - persisted alert row shape stays the validated `AlertEvent` payload written by
    `append_alert(...)`
  - missing `session.json` remains an unknown-session failure
  - missing the file-backed `alerts.jsonl` log on a known session remains a
    stable empty alert history
  - malformed or unreadable alert-log rows remain ignorable without failing the whole read
  - filter, raw-summary, grouped-timeline, and grouped-summary meanings stay unchanged
- current tests that prove this contract:
  - `tests/test_session_alert_store.py`
  - `tests/test_session_alert_store_runtime.py`
  - `tests/test_session_alert_store_runtime_config.py`
  - `tests/test_session_alert_store_parity.py`
  - `tests/test_session_alert_store_postgres.py`
  - `tests/test_session_alert_store_postgres_config.py`
  - `tests/test_session_io.py`
  - `tests/test_alert_query_service_read.py`
  - `tests/test_alert_query_service_filter.py`
  - `tests/test_alert_query_service_summary.py`
  - `tests/test_alert_timeline_service_grouping.py`
  - `tests/test_alert_timeline_service_filters.py`
  - `tests/test_alert_incident_summary_service_contracts.py`
  - `tests/test_alert_incident_summary_service_filters.py`
  - `tests/test_session_alert_adapter.py`
  - `tests/test_api_session_alerts.py`
  - `tests/test_api_session_alert_incidents.py`

The current test split is:

- `tests/session_alert_test_support.py`
  - shared session/alert setup helpers for this slice, including runtime
    Postgres smoke helpers and the shared
    `install_runtime_postgres_bootstrap_failure(...)` helper for deterministic
    boundary-failure tests
- `tests/test_session_alert_store.py`
  - file-backed alert-store contract coverage for raw reads, malformed-row
    tolerance, missing-session failures, repeated-read stability,
    append-order behavior, append/read round-trips, and parity with the raw
    and grouped alert read models
- `tests/test_session_alert_store_runtime.py`
  - runtime default-backend selection plus caller-stability coverage for the
    raw alert reader and compatibility write seam
  - also covers cache recovery after failed Postgres bootstrap plus explicit
    backend switching with cache clears
- `tests/test_session_alert_store_runtime_config.py`
  - explicit runtime backend-mode config coverage for `file` versus `postgres`
- `tests/test_session_alert_store_parity.py`
  - shared file-store versus PostgreSQL-store parity for raw reads,
    filtered raw reads, known-empty and unknown-session behavior, filtered
    summaries, grouped timelines, grouped summaries, grouped filtered reads,
    grouped time-bounded reads, and the file-only malformed-row subset path
- `tests/test_session_alert_store_postgres.py`
  - PostgreSQL alert-store contract coverage for schema/bootstrap plus the
    concrete second backend's read/write drift-sensitive behavior
- `tests/test_session_alert_store_postgres_config.py`
  - narrow Postgres env/config loading, cache behavior, and URL validation
    coverage
- `tests/test_session_io.py`
  - compatibility write-entry coverage showing `append_alert(...)` delegates to
    the default alert-store seam without widening into broader session
    persistence changes
  - also covers write-to-read seam integration plus the hybrid snapshot path
    where metadata/progress/results remain file-backed and alerts follow the
    active backend
- `tests/api_alert_test_support.py`
  - shared FastAPI alert-route payload builders plus boundary setup helpers for
  auth, limiter, and simple successful route responses
- `tests/mcp_alert_test_support.py`
  - shared in-memory MCP session helpers for the alert-tool tests
- `tests/alert_query_service_test_support.py`
  - tiny shared setup helpers for the split raw alert query service suites
- `tests/alert_incident_service_test_support.py`
  - tiny shared typed-access and empty-result helpers for the split grouped
    incident timeline and summary suites
- `tests/test_alert_query_service_read.py`
  - service-level persisted alert-log read semantics, corrupt/unreadable input
    tolerance, and missing/orphaned session handling
- `tests/test_alert_query_service_filter.py`
  - raw filtered alert semantics, including invalid time-filter validation,
    inclusive/open-ended time-range behavior, persisted ordering, unknown-filter
    empty results, and filtered-entrypoint missing-session failures
- `tests/test_alert_query_service_summary.py`
  - numeric raw alert summary semantics, summary-specific validation, empty
    summary behavior, and summary-entrypoint missing-session failures
- `tests/test_api_auth.py`
  - auth-boundary unit coverage for enabled/disabled auth, missing keys,
    invalid keys, blank headers, and unsupported modes
- `tests/test_api_rate_limit.py`
  - limiter unit coverage for fixed-window counting, principal separation,
    window reset, and IP-strategy subject building
- `tests/test_api_boundary_settings_env.py`
  - env parsing, run-mode defaults, and share-mode API-key generation coverage
- `tests/test_api_boundary_settings_validation.py`
  - direct validator coverage plus FastAPI startup validation integration
- `tests/test_api_boundary_error_contracts.py`
  - non-429 FastAPI boundary error-header regression coverage
- `tests/test_api_server_cli_runtime.py`
  - explicit `local`/`share` CLI runtime preparation, overrides, generated-key
    flow, fail-fast behavior, and CLI-only boundary posture decisions before
    any HTTP request exists
- `tests/test_api_server_cli_routes.py`
  - real alerts-router behavior under CLI-prepared `local` and `share` mode,
    including open local access, `401`, `429`, and proof that CLI-prepared
    share mode does not widen protection to public routes
  - also locks down that `/openapi.json` and `/detectors` remain outside the
    current alerts-router auth boundary
  - keeps generated-key and manual-key access aligned across more than one
    protected alerts route shape
- `tests/test_api_server_cli_output.py`
  - startup summary output, generated-key guidance, manual-key non-leakage,
    and operator-facing `share` versus `local` startup distinction
  - also covers custom host/port reflection for both manual `share` and `local`
    startup paths
- `tests/test_api_alert_route_auth_policy.py`
  - shared FastAPI alerts-router authentication policy, stable `401`
    behavior, cross-route invalid/missing-key consistency, and proof that the
    alerts-router auth boundary does not become app-wide policy
- `tests/test_api_alert_route_rate_limit_policy.py`
  - shared FastAPI alerts-router limiter behavior, logging, budget-sharing
    policy, stable `429` plus `Retry-After`, and proof that unrelated public
    routes stay usable after protected route throttling
- `tests/test_api_alert_route_contracts.py`
  - shared FastAPI alerts-router `429` response shaping and OpenAPI contract coverage
- `tests/test_alert_timeline_service_grouping.py`
  - service-level grouped timeline semantics for merge and non-merge rules,
    chronological ordering, deterministic same-timestamp tie-breaking, stable
    grouped `source_names`, transitive adjacent grouping, malformed-row
    degradation, and a light scaling guard
- `tests/test_alert_timeline_service_filters.py`
  - service-level grouped timeline filter reuse before grouping, invalid and
    inverted time-filter validation, missing-session failures, unknown-filter
    empty results, inclusive/open-ended time bounds, and time-filter handling
    for rows with unusable timestamps
- `tests/test_alert_incident_summary_service_contracts.py`
  - service-level grouped incident summary counts, categories, narrative
    shaping, deterministic tie-breaking, malformed-row degradation, and
    raw-versus-grouped count separation when some rows cannot form incidents
- `tests/test_alert_incident_summary_service_filters.py`
  - service-level grouped incident summary filter reuse, filtered-empty
    summaries, invalid and inverted time-filter validation, missing-session
    failures, and unknown-filter empty grouped summaries
- `tests/test_api_session_alerts.py`
  - FastAPI adapter behavior for raw alert list and summary routes
  - includes stable empty-result envelopes, filter-forwarding coverage, real
    file-backed seam reads, raw FastAPI/MCP optional-window-field parity, and
    shared runtime Postgres bootstrap-failure envelope coverage
- `tests/test_api_session_alert_incidents.py`
  - FastAPI adapter behavior for timeline and grouped incident summary routes
  - includes stable empty-result envelopes, grouped filter-forwarding
    coverage, real file-backed seam reads, grouped malformed-row boundary
    parity, and grouped runtime Postgres bootstrap-failure envelope coverage
- `tests/test_mcp_server_contracts.py`
  - structural MCP registration and launch-wiring coverage, including stable
    tool names/count, read-only server instructions, schema basics, and stdio
    launch wiring
- `tests/mcp_server_alerts_test_support.py`
  - tiny shared setup and result helpers for the split raw MCP behavior/error suites
  - intentionally limited to filesystem seams plus success/error assertion helpers
- `tests/test_mcp_server_alerts_behavior.py`
  - MCP raw alert-query and raw-summary behavior through the real in-memory
    MCP session
  - includes real file-backed seam reads
  - includes known-session empty payloads, filtered raw MCP list/summary alignment,
    and raw unknown-filter empty payloads
  - keeps usable payload behavior separate from MCP-facing error translation
- `tests/test_mcp_server_alerts_errors.py`
  - raw MCP tool-level error mapping
  - includes missing-session failures, invalid time-range failures, and combined
    raw invalid-timestamp parity
  - keeps raw MCP list/summary error translation parity explicit
- `tests/mcp_fastapi_parity_test_support.py`
  - tiny shared setup, fetch, and meaning-level assertion helpers for the split
    FastAPI/MCP parity suites
  - intentionally limited to protected FastAPI route setup, parity fixture
    setup, and cross-surface meaning plumbing
- `tests/test_mcp_fastapi_boundary_split.py`
  - explicit FastAPI-versus-stdio MCP trust-boundary and cross-surface smoke coverage
  - keeps the raw MCP boundary checks grouped together and the grouped MCP
    boundary checks grouped together so the trust rule is easier to review
  - includes the regression that FastAPI `share` CLI runtime preparation must
    not pull stdio MCP raw or grouped tools into the HTTP auth/rate-limit boundary
  - also keeps raw MCP list/summary tools grouped together under direct FastAPI
    auth/rate-limit boundary checks
  - and keeps grouped MCP tools usable even when both `share` prep and direct
    FastAPI protections are applied before the MCP read
- `tests/test_mcp_fastapi_parity_behavior.py`
  - FastAPI/MCP meaning parity for normal shared-fixture reads
  - includes unfiltered and filtered raw/grouped reads, known empty sessions,
    unknown-filter no-match reads, and one shared time-bounded slice
  - keeps ordinary parity scenarios separate from validation and ordering edges
- `tests/test_mcp_fastapi_parity_edges.py`
  - FastAPI/MCP meaning parity for validation and ordering edges
  - includes invalid time-filter validation, inverted ranges, inclusive and
    open-ended time bounds, and same-timestamp grouped ordering
  - keeps the higher-risk boundary and ordering seams separate from ordinary
    parity behavior
- `tests/mcp_server_incidents_test_support.py`
  - tiny shared setup and result helpers for the split grouped MCP behavior/error suites
  - intentionally limited to grouped-session setup plus success/error assertion helpers
- `tests/test_mcp_server_incidents_behavior.py`
  - MCP grouped timeline and incident-summary behavior
  - includes known-session empty grouped payloads, filtered grouped MCP
    alignment, unknown-filter empty grouped payloads, and real file-backed
    seam reads
  - keeps grouped payload behavior separate from grouped MCP error translation
- `tests/test_session_runner_execution_local.py`
  - finite-slice execution coverage for alert persistence through the shared
    seam, including boundary visibility, append-order preservation, and
    cancel-before-next-slice behavior
- `tests/test_mcp_server_incidents_errors.py`
  - grouped MCP tool-level error mapping
  - includes missing-session failures plus grouped invalid time-range and
    invalid timestamp-format parity
  - keeps grouped timeline/summary error translation parity explicit

Keep new tests near those ownership boundaries instead of adding a larger
catch-all alert-query suite.

The split is deliberate:

- service files prove the durable file-backed semantics once
- auth unit files prove API-key validation and auth-mode behavior before the
  HTTP adapter layer is involved
- rate-limit unit files prove fixed-window counting semantics before the HTTP
  adapter layer is involved
- `tests/api_alert_test_support.py` keeps the route-policy files small by
  owning the repeated alert-route setup seams rather than leaving each policy
  file to build its own tiny test framework
- the alerts-router HTTP protection composition lives in
  `src/api/alert_route_policy.py`, so route tests patch the boundary seam there
  rather than duplicating auth/rate-limit behavior inside route functions
- route-policy files prove router-scoped auth and limiter behavior once across
  the protected alerts surface, but are now split so authentication policy,
  limiter policy, and client-visible response contracts each have one obvious home
- route-policy files also lock down the current limiter identity rule:
  principal-by-default, optional IP strategy, and local fallback when auth is
  disabled
- FastAPI files prove HTTP parameter binding and error mapping
- MCP files prove tool registration, launch wiring, and behavior through the
  real in-memory MCP transport seam
- the FastAPI-versus-MCP boundary-split file keeps the current local-trust
  stdio story explicit without cluttering the raw MCP tool behavior files
- the raw and grouped MCP behavior files now also lock the no-data and
  filtered-data tool payloads to the same shared service contracts used by
  FastAPI

When you add new coverage for this slice, prefer extending the narrow owning
file over creating another mixed alert-and-incident test module.

Focused MCP launch wiring:

```bash
.venv/bin/esm-mcp
```

Raw-checkout equivalent:

```bash
PYTHONPATH=src .venv/bin/python -m esm_mcp
```

Both start the current MCP server over `stdio`, which is the intended local
client transport for the current project stage.
The installed `esm-mcp` entrypoint is available after refreshing the editable
environment (for example with `uv sync` or a fresh editable install). Use the
module form when you want a raw-checkout path that does not depend on the
console script already existing in `.venv/bin/`.

The current backend packaging split is:

- `pip install -e .`
  - runtime dependencies only
- `pip install -e .[test]`
  - runtime plus backend test tooling
- `pip install -e .[dev]`
  - runtime plus test, Ruff lint, and type-check tooling

Current backend import/run expectations:

- `npm run dev`
  - canonical desktop runtime path
- `pip install -e .` or `pip install -e .[test]`
  - editable-install path for backend runtime and test work
- `PYTHONPATH=src`
  - raw-checkout backend import/debug path when you are not relying on an
    editable install
- `uvicorn api.app:app --app-dir src --reload`
  - backend-only HTTP startup path for the current flat `src/` layout

Packaging sanity check:

```bash
python3 -m venv /tmp/esm-packaging-check
/tmp/esm-packaging-check/bin/python -m pip install --upgrade pip
/tmp/esm-packaging-check/bin/python -m pip install --no-deps --no-build-isolation -e .
```

Runtime import smoke check:

```bash
. .venv/bin/activate
pip install -e .[test]
python -c "import api.app, api.routers.sessions, session_service, session_cli"
```

Raw-checkout import/debug check:

```bash
PYTHONPATH=src .venv/bin/python -c "import api.app, api.routers.sessions, session_service, session_cli"
```

The first check confirms that editable installs still build cleanly with the
current package metadata. The second confirms that the backend import surface
still works in a runtime-capable environment after packaging changes. The
third is useful when you want to confirm raw-checkout backend imports still
work with the current `src/` layout.

If you are validating the MCP slice specifically, include the new shared
service and MCP adapter in the import smoke check:

```bash
PYTHONPATH=src .venv/bin/python -c "import api.app, session_alerts, session_alert_incidents, esm_mcp.server"
```

For a slightly stronger launch-path smoke check, verify the installed console
entrypoint resolves:

```bash
.venv/bin/python -c "import esm_mcp.server; print(callable(esm_mcp.server.main))"
```

Dedicated backend typecheck:

```bash
uv sync --extra typecheck
MYPYPATH=src mypy --explicit-package-bases src/alert_rules.py src/api/app.py src/api/routers/alerts.py src/api/routers/detectors.py src/api/routers/health.py src/api/routers/playback.py src/api/routers/sessions.py src/api/schemas.py src/api_auth.py src/api_boundary_config.py src/api_rate_limit.py src/api_server_cli.py src/esm_mcp/alert_tools.py src/esm_mcp/server.py src/session_alert_adapter.py src/session_alert_incidents.py src/session_alerts.py src/session_alert_store.py src/session_alert_store_runtime_config.py src/session_alert_store_postgres.py src/session_alert_store_postgres_config.py src/session_io.py src/session_models.py src/session_runner.py src/session_service.py src/stream_loader_contracts.py
```

Use `uv sync --extra typecheck` to make sure the local typecheck env has the
required checker deps.
Use `MYPYPATH=src` so mypy resolves the flat `src/` modules as source files
rather than treating them like installed third-party packages.
Use this after changing the Python contracts that sit closest to the frontend
bridge, session lifecycle, or alert-rule boundary.

Focused alert-query typecheck slice:

```bash
.venv/bin/mypy src/session_alert_store.py src/session_alert_store_runtime_config.py src/session_alert_store_postgres.py src/session_alert_store_postgres_config.py src/session_alerts.py src/session_alert_incidents.py src/session_alert_adapter.py
```

Use this shorter command when you are only tightening the alert persistence
and alert-query slice or the shared adapter typing and want a faster local
signal than the larger curated backend list.

Primary backend lint check:

```bash
python -m pip install -e .[lint]
ruff check src scripts tests
```

Use this as the main Python lint gate now that Ruff is the standardized
linter. Keep Bandit separate for security-focused checks.

CI currently runs the Ruff job as a fast backend gate on backend or contract
changes, and on `main` pull requests.

Advisory backend pyright check:

```bash
python -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/pip install -e .[typecheck]
.venv/bin/pyright --project pyrightconfig.json src/alert_rules.py src/api/app.py src/api/routers/alerts.py src/api/routers/detectors.py src/api/routers/health.py src/api/routers/playback.py src/api/routers/sessions.py src/api/schemas.py src/api_auth.py src/api_boundary_config.py src/api_rate_limit.py src/api_server_cli.py src/esm_mcp/alert_tools.py src/esm_mcp/server.py src/session_alert_adapter.py src/session_alert_incidents.py src/session_alerts.py src/session_alert_store.py src/session_alert_store_runtime_config.py src/session_alert_store_postgres.py src/session_alert_store_postgres_config.py src/session_io.py src/session_models.py src/session_runner.py src/session_service.py src/stream_loader_contracts.py
```

Use this as a non-blocking editor-aligned signal if you want pyright feedback
without making it the required branch gate yet.

Focused alert-query pyright slice:

```bash
.venv/bin/pyright --project pyrightconfig.json src/session_alert_store.py src/session_alert_store_runtime_config.py src/session_alert_store_postgres.py src/session_alert_store_postgres_config.py src/session_alerts.py src/session_alert_incidents.py src/session_alert_adapter.py
```

Use this when the change stays inside the shared alert persistence and
alert-query slice and you want the narrowest pyright signal that still matches
the branch's current typing focus.

### Repo-Local Skill Tests

The repo-local Codex skills under `./.agents/skills/` are validated with a
small deterministic Python slice rather than live model calls.

Current test files:

- `tests/test_repo_skills.py`
  - structure, skill-boundary, scenario, and snapshot checks
- `tests/skill_test_support.py`
  - parsing and reusable test helpers
- `tests/fixtures/skill_output_snapshots/`
  - saved expected output templates for selected prompts

This keeps the skill layer cheap to validate and easy to evolve while the
project is still in a local-first pre-pilot stage.

### Frontend

The frontend suite covers:

- setup flow
- playback source routing
- session status UX
- playback error messaging
- bridge contract normalization

Frontend type safety is intentionally strict:

- `tsc -b --incremental false`
- `noUncheckedIndexedAccess`
- `exactOptionalPropertyTypes`
- `noPropertyAccessFromIndexSignature`
- `noImplicitReturns`
- `noFallthroughCasesInSwitch`

Common local command:

```bash
npm --prefix frontend run test
```

Advisory frontend lint check:

```bash
npm --prefix frontend run lint:frontend
```

Use this as a lightweight frontend quality signal. It is not yet part of the
required merge gate, but it is already wired into CI as a non-blocking job.

## FastAPI And Bridge Contract Checks

These tests are especially important for the current project stage because they
protect the boundary between backend contracts and frontend normalization.

Backend/API contract checks:

- `tests/test_api_boundary_validation.py`
  - FastAPI request validation
- `tests/test_api_boundary_playback.py`
  - playback-resolution behavior
- `tests/test_api_boundary_sessions_read.py`
  - session read-route behavior
  - runtime-selected alert-backend parity between the session snapshot route
    and the dedicated alert routes
- `tests/test_api_boundary_sessions_start.py`
  - session start-route behavior
- `tests/test_api_boundary_sessions_cancel.py`
  - session cancel-route behavior
- `tests/test_session_service_start.py`
  - shared start-session service behavior
- `tests/test_session_service_worker.py`
  - detached worker launch and log-handle behavior
- `tests/test_session_service_read_cancel.py`
  - shared read/cancel service behavior
- `tests/test_session_cli_tooling.py`
  - CLI adapter behavior over the shared session service
  - runtime-selected alert-backend behavior for `read-session`
- `tests/test_api_boundary_contracts.py`
  - structured API error payloads
  - populated session snapshot response shape
- `tests/test_stream_loader_contracts.py`
  - `api_stream` contract-builder consistency
  - loader seam helper invariants
  - replay/identity helper behavior
- `tests/test_stream_loader_http_hls_core_playlist.py`
  - ordinary playlist parsing, variant resolution, and segment-path resolution
- `tests/test_stream_loader_http_hls_core_progression.py`
  - live progression, moving-window, cancel, and idle-refresh behavior
- `tests/test_stream_loader_http_hls_core_provider.py`
  - malformed refresh recovery and provider/transport edge behavior
- `tests/test_stream_loader_http_hls_reconnect_recovery.py`
  - reconnect recovery, resumed progression, and temporary outage behavior
- `tests/test_stream_loader_http_hls_reconnect_state.py`
  - reconnect budgets, replay de-duplication state, and reconnect logging behavior
- `tests/test_stream_loader_http_hls_limits_runtime.py`
  - runtime and refresh-budget enforcement plus shutdown behavior
- `tests/test_stream_loader_http_hls_limits_cleanup.py`
  - temp-state, cleanup, and storage-budget guarantees
- `tests/test_stream_loader_http_hls_limits_restart.py`
  - soak, restart, and dedup-resume behavior
- `tests/test_stream_loader_http_hls_playlist.py`
  - direct playlist parsing helper coverage
- `tests/test_stream_loader_http_hls_fetch.py`
  - direct transport helper coverage
- `tests/test_stream_loader_http_hls_materialize.py`
  - direct temp-file materialization helper coverage
- `tests/test_stream_loader_http_hls_policy.py`
  - direct replay/window/policy helper coverage

Frontend contract checks:

- `frontend/src/bridge/contract.success.test.ts`
  - bridge success normalization
  - detector and playback-source normalization
- `frontend/src/bridge/contract.errors.test.ts`
  - typed bridge failures
  - transport-envelope error normalization
  - bridge error payload fallback and typed metadata preservation
- `frontend/src/bridge/contract.session-snapshot.shape.test.ts`
  - required session snapshot shape and lifecycle field preservation
- `frontend/src/bridge/contract.session-snapshot.malformed.test.ts`
  - fail-closed malformed nested payload handling
- `frontend/src/bridge/contract.session-snapshot.collections.test.ts`
  - partially corrupt alert/result collection compatibility
- `frontend/src/bridge/transport.test.ts`
  - transport selection and demo fallback behavior
- `frontend/src/components/SessionStatusPanel.test.tsx`
  - operator-facing lifecycle, reconnect, and playback-diagnostic wording
- `frontend/src/presenters/alertFeed.test.ts`
  - playback-aware alert feed reveal timing and timestamp labels
- `frontend/src/uiErrors.test.ts`
  - operator-facing error wording
  - `api_stream` status/error interpretation
- `frontend/src/hooks/useMonitoringSession.lifecycle.test.tsx`
  - hook behavior for local lifecycle polling, cancel-state transitions, and typed failures
- `frontend/src/hooks/useMonitoringSession.apiStream.test.tsx`
  - hook behavior for `api_stream` reconnect, recovery, and terminal polling semantics
- `frontend/src/hooks/usePlaybackSource.test.tsx`
  - hook behavior on top of normalized playback-source resolution
- `frontend/electron/fastApiFallback.test.mjs`
  - FastAPI readiness cache and fallback policy
  - no-fallback behavior for structured API business errors
- `frontend/electron/fastApiRuntimePolicy.test.mjs`
  - startup timeout and clear unavailable-runtime behavior
  - no-operation execution after startup failure
- `frontend/electron/fastApiProcessManager.test.mjs`
  - FastAPI process ownership
  - single-start behavior and process-state reset
- `frontend/electron/bridgeResponses.test.mjs`
  - Electron bridge success/error envelope mapping
  - structured bridge payload expectations for lifecycle operations
- `frontend/electron/bridgeHandlerRegistry.test.mjs`
  - current IPC channel map and shared runtime-policy wrapping
- `frontend/electron/fastApiClient.test.mjs`
  - FastAPI JSON request/response shaping
- `frontend/electron/fastApiStartupOrchestrator.test.mjs`
  - startup composition across process management, readiness checks, and policy
- `frontend/electron/playbackSourcePolicy.test.mjs`
  - renderer-safe playback URL adaptation
- `frontend/electron/localMediaResponses.test.mjs`
  - concrete `local-media://` file/range response helpers
- `frontend/electron/localMediaRequestPolicy.test.mjs`
  - `local-media://` request classification and routing policy
- `frontend/electron/hlsProxy.test.mjs`
  - remote HLS manifest rewriting and opaque proxy-token behavior

Use these focused checks when changing:

- shared session start/read/cancel mechanics
- detached worker launch, `worker.log` capture, or parent/worker observability
- FastAPI request/response schemas
- session snapshot fields
- bridge error payloads
- frontend normalization logic
- frontend transport selection and demo fallback behavior
- bridge helper ownership or validator-sharing inside the normalized contract layer
- Electron transport fallback or bridge-envelope behavior
- Electron startup orchestration, readiness policy, or process ownership
- Electron bridge-handler registration or playback URL adaptation
- `local-media://` protocol routing/response behavior
- `api_stream` contract builders or loader helper semantics
- concrete HTTP/HLS reconnect, cleanup, or limit behavior
- the new direct HLS helper modules or their helper-level invariants

Focused HLS helper command:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/pytest -p no:cacheprovider \
  tests/test_stream_loader_http_hls_playlist.py \
  tests/test_stream_loader_http_hls_fetch.py \
  tests/test_stream_loader_http_hls_materialize.py \
  tests/test_stream_loader_http_hls_policy.py -q
```

Useful focused commands:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/pytest -p no:cacheprovider \
  tests/test_session_service_start.py \
  tests/test_session_service_worker.py \
  tests/test_session_service_read_cancel.py \
  tests/test_api_boundary_sessions_read.py \
  tests/test_api_boundary_sessions_start.py \
  tests/test_api_boundary_sessions_cancel.py \
  tests/test_session_cli_tooling.py -q
```

Use that command first for worker-observability changes. It covers:

- shared worker-launch behavior in `session_service.py`
- the current API rule that diagnostics stay backend-owned
- CLI-side worker failure logging behavior

### Legacy Seam Replacement

For the demoted legacy `src/main.py` seam, the intended replacement is focused
pytest coverage rather than a new manual tooling script. The main local
confidence replacements are:

- `tests/test_processor_routing.py`
- `tests/test_processor_failures.py`
- `tests/test_processor_context_alerts.py`
- `tests/test_session_runner_local.py`
- `tests/test_e2e_local_session.py`

```bash
PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/pytest -p no:cacheprovider tests/test_api_boundary_*.py -q
```

```bash
cd frontend
npm run test -- src/bridge/contract.success.test.ts src/bridge/contract.errors.test.ts src/bridge/contract.session-snapshot.shape.test.ts src/bridge/contract.session-snapshot.malformed.test.ts src/bridge/contract.session-snapshot.collections.test.ts src/uiErrors.test.ts
```

```bash
cd frontend
npm run test:electron-bridge
```

Frontend migration checkpoint:

```bash
cd frontend
npm run test:frontend-checkpoint
```

Dedicated frontend typecheck:

```bash
cd frontend
npm run typecheck
```

Cancel migration checkpoint:

```bash
cd frontend
npm run test:cancel-migration
```

Startup/runtime checkpoint:

```bash
cd frontend
npm run test:startup-runtime
```

Startup milestone checkpoint:

```bash
cd frontend
npm run test:startup-milestone
```

Use this checkpoint after a meaningful FastAPI startup/readiness change when
you want both the focused Electron runtime tests and the broader frontend
session-flow checks in one run.

If a change touches FastAPI startup/readiness behavior, run Electron-layer
startup tests first before expanding into broader app-level checks.

For narrower diagnosis:

```bash
cd frontend
npm run test:electron-bridge
npm run test:session-flow
```

For faster local feedback loops, use the narrower frontend aliases:

```bash
cd frontend
npm run test:app-runtime
```

Runs the heavier App integration checks for start/cancel/polling behavior
without paying for the full frontend suite.

```bash
cd frontend
npm run test:ui-fast
```

Runs the cheap bridge/view-model/presenter/source-model slices that are useful
when iterating on contracts or UI state logic without touching the App shell.

## Lifecycle Slice Validation

After each lifecycle-hardening slice, run:

```bash
cd frontend
npm run test:startup-milestone
```

Use the full frontend suite at larger boundaries, such as before grouping
commits or after a broader lifecycle/race hardening pass:

```bash
cd frontend
npm run test
```

If one side of the contract changes, do not rely on only backend tests or only
frontend tests. Run at least one focused backend contract check and one focused
frontend normalization check together.

For a branch that is about to merge into `main`, also run a small composed
smoke check:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/pytest -p no:cacheprovider tests/test_e2e_local_session.py -q
```

For the backend E2E suites, the current split is:

- `tests/test_e2e_local_session.py`
  - small snapshot-contract smoke check
- `tests/test_e2e_local_session_real_media.py`
  - curated real-media local-session coverage
- `tests/test_e2e_session_ground_truth_api_stream.py`
  - synthetic `api_stream` ground-truth contract cases
- `tests/test_e2e_session_ground_truth_local.py`
  - slower real-media ground-truth matrix

Use markers to keep local feedback tight:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/pytest -p no:cacheprovider -m "e2e and not slow" tests/test_e2e_*.py -q
```

That command keeps:

- the small local-session smoke test
- the synthetic `api_stream` ground-truth cases

and skips the heavier real-media suites until you actually need them.

Run the fuller real-media E2E pass when changing detector behavior, windowing,
or persisted snapshot expectations for checked-in media fixtures:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/pytest -p no:cacheprovider -m "e2e and slow" tests/test_e2e_*.py -q
```

Note:

- some Electron/HLS tests bind loopback listeners on `127.0.0.1`
- those cases may fail inside stricter sandboxes even when the code is healthy
- if that happens, rerun the same targeted suite in a normal local shell

Recommended backend order for session-runner work:

1. `tests/test_session_runner_lifecycle.py`
2. `tests/test_session_runner_execution_local.py`
3. `tests/test_session_runner_execution_api_stream.py`
4. `tests/test_session_runner_terminal.py`
5. `tests/test_session_runner_local.py`
6. `tests/test_session_runner_api_stream_progress.py`
7. `tests/test_session_runner_api_stream_http_hls_lifecycle.py` in a normal local shell when loopback sockets are available
8. `tests/test_session_runner_api_stream_http_hls_failures.py` in a normal local shell when loopback sockets are available

## Lifecycle Coverage Audit

Current lifecycle coverage is already spread across the main layers:

- backend tests
  - `tests/test_session_runner_lifecycle.py`
    - pending-session setup
    - pending-to-running transition semantics
    - smallest helper-level seam for session setup and status transitions
  - `tests/test_session_runner_execution_local.py`
    - extracted local execution-loop helper behavior
    - analyzer-bundle invocation and local event-persistence seams
  - `tests/test_session_runner_execution_api_stream.py`
    - extracted live `api_stream` execution-loop helper behavior
    - api-stream cleanup accounting and live helper wiring seams
    - analyzer-bundle invocation and event-persistence seams
    - first stop when a refactor changes slice-processing flow
  - `tests/test_session_runner_terminal.py`
    - terminal outcome persistence
    - validation-failure persistence
    - api-stream cleanup accounting and terminal log-field shaping
    - first stop when a refactor changes status mapping, cleanup, or terminal logs
  - `tests/test_session_runner_local.py`
    - start-to-completed flow
    - mid-run cancel leading to `cancelled`
    - runtime failure persistence
    - validation failure persistence
    - stable black-box local lifecycle coverage
    - local discovery and slice-expansion behavior now owned by
      `session_runner_discovery`
  - `tests/test_session_runner_api_stream_progress.py`
    - seam-loader `api_stream` progress-shaping, repeated temporary failure
      tolerance, alert re-entry, and multi-detector live coherence
  - `tests/test_session_runner_api_stream_http_hls_lifecycle.py`
    - real HTTP/HLS-backed `api_stream` transport and lifecycle integration
    - keep this as the signoff suite when a change touches successful real HTTP/HLS progression
  - `tests/test_session_runner_api_stream_http_hls_failures.py`
    - real HTTP/HLS-backed failure persistence, partial-progress, and budget exhaustion coverage
  - `tests/test_session_io.py`
    - invalid terminal transitions
    - completed-progress consistency checks
- FastAPI boundary tests
  - `tests/test_api_boundary_validation.py`
    - request validation failures
  - `tests/test_api_boundary_sessions_read.py`
    - missing-session reads
    - populated session snapshot passthrough behavior
  - `tests/test_api_boundary_sessions_start.py`
    - start success and shared error mapping
  - `tests/test_api_boundary_sessions_cancel.py`
    - cancel success, missing-session cancel failure, and current terminal cancel behavior
  - `tests/test_api_boundary_contracts.py`
    - structured error envelopes
    - malformed nested payload fail-closed behavior
- Electron bridge/runtime tests
  - `frontend/electron/bridgeResponses.test.mjs`
    - start/cancel success mapping
    - structured start/cancel failure mapping
    - generic unavailable-runtime failure mapping
  - `frontend/electron/fastApiRuntimePolicy.test.mjs`
    - startup readiness success
    - startup timeout and clear unavailable failure
  - `frontend/electron/fastApiFallback.test.mjs`
    - legacy fallback/helper seam coverage for start/read/cancel edge cases
- frontend app/session-flow tests
  - `frontend/src/App.startSession.test.tsx`
    - start failures
    - malformed start payloads
    - initial-read failure after start
    - successful `api_stream` start flow
  - `frontend/src/App.cancelSession.test.tsx`
    - normal cancel flow
    - typed cancel failures
    - malformed cancel payloads
    - missing-session cancel failure
    - `cancelSession -> null` success
  - `frontend/src/App.pollingStatus.local.test.tsx`
    - running-to-completed polling flow
  - `frontend/src/App.pollingStatus.apiStream.test.tsx`
    - polling failure with recovery
    - running-to-failed terminal transitions
    - `api_stream` status/detail messaging

Current high-value gaps:

- no explicit backend truth-table style test for repeated cancel requests
- no explicit backend/API test for canceling an already terminal session as a final intended rule
- no focused Electron test for read-session missing-session bridge mapping
- no frontend app-flow coverage for cancel-after-completion

## Current Branch Validation Baseline

This branch currently has a green full-suite validation baseline:

- backend: `350 passed, 3 skipped`
- frontend/Electron: `24 files passed, 203 tests passed`

That is strong coverage for the current late-prototype / MVP stage.
The remaining gaps are mostly security-policy activation and deeper Electron
main-process composition checks, not broad missing functional coverage.
  - stale poll result arriving after cancel request
  - repeated end/cancel requests from the UI

Use this audit before adding more lifecycle tests so new coverage fills a real
gap instead of duplicating an existing layer.

### Runtime Doc Alignment

When the desktop runtime model changes, keep these docs aligned:

- `docs/fastapi-boundary.md`
- `docs/architecture-decision-fastapi.md`
- `docs/architecture.md`
- `README.md`
- `frontend/README.md`

These docs should describe the same normal runtime path:

- Electron owns local FastAPI startup/readiness
- FastAPI is the normal desktop runtime backend
- Python CLI commands remain available for tooling/debugging only

### Build Validation

Common local build command:

```bash
npm run build
```

## Opt-In Manual Validation

Public-stream validation is intentionally split from routine tests because
provider behavior is unstable and can make CI noisy.

Use:

- [api-stream-local-validation.md](./api-stream-local-validation.md)
- `tests/test_api_stream_real_smoke.py`

That split keeps normal regression tests reproducible while still leaving a
path for real-stream confidence checks.

## Current Validation Limits

- not all public providers allow automated fetches
- some providers require Cloudflare/browser behavior and will fail even with a
  local proxy
- long-run operational confidence is improving but not finished
- broader multi-user or service-mode validation still belongs to the next stage

## What CI Should Cover

The current GitHub Actions workflow is intentionally lightweight:

- backend runtime install plus `test` extra for pytest jobs
- frontend install
- frontend test run
- frontend build

That is enough to catch common regressions without pretending CI replaces
manual real-stream validation.
