# Testing And Validation

This document summarizes how the repo is currently validated and where deeper
confidence still needs to be built.

Use it for verification commands and validation scope.
Do not use it as a detailed architecture or contract doc.

For Python commands in this repo, prefer `./.venv/bin/python` or `just`
recipes rather than `python3` from `PATH`. The workspace does not force
virtualenv auto-activation.

For broader doc ownership rules, use [docs/README.md](./README.md#document-ownership).

For branch workflow around those checks, use:

- [branch-purpose-template.md](./branch-purpose-template.md)
- [`.github/pull_request_template.md`](../.github/pull_request_template.md)
- [merge-readiness-checklist.md](./merge-readiness-checklist.md)

Treat them as one flow:

- define branch purpose first
- keep PR scope and validation notes explicit while the branch is active
- use the readiness checklist at the end instead of turning it into a second
  planning doc

The branch template owns the lightweight execution pattern and the medium-task
checklist. Reuse that pattern in planning and review notes instead of copying
it into multiple workflow docs.

When the next question is "what is the smallest honest lane?" use the
`test-strategy-review` skill first. When a validation or workflow change also
touches API, CLI, persisted-data, or bridge contracts, move
`docs/contracts.md` with it instead of treating the update as local-only docs
polish.

Keep the test rule lightweight:

- first ask what existing focused test or `just docs-check` already proves the change
- if none, decide whether one nearby focused test is worth adding
- only then choose whether broader validation is needed

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
That guide owns the definitions of required, advisory, informational, weekly,
and local lanes used throughout this document.

For AI-assisted tools, use this doc as the execution owner:

- stay here when choosing local commands, validation depth, or what a local
  run can and cannot prove
- switch to `ci-maintainer-guide.md` for merge-blocking policy, `main-gate`
  dependencies, or skip/forced-on CI behavior
- prefer cross-links over repeating the same CI policy detail here

## Routine Validation

Choose the smallest honest lane first.

### Execution Guide

| Change shape | Start locally | CI follow-up | Local limit |
| --- | --- | --- | --- |
| One clear seam such as detectors, alert rules, HLS, or docs/workflow helpers | Matching focused lane such as `just test-detectors`, `just test-alert-rules`, `just test-hls`, or `just docs-check` | Path-aware branch lanes and the protected `main` chain when the change reaches those areas | Focused runs do not prove neighboring seams stayed intact |
| Multi-seam runtime work that crosses backend plus frontend/operator flow | `just test-fast` | Fast branch-feedback lanes such as `backend-tests`, `frontend-checkpoint`, and aggregate gates | Does not prove packaging smoke, full frontend production validation, or PR-only policy checks |
| Detached-worker runtime persistence work across FastAPI, `session_service`, and durable session snapshots | `just test-session-runtime` only when the branch really changes that seam | Weekly `lifecycle-deep` lane | Slower and more timing-sensitive than routine fast local loops; default helper stays file-backed while live PostgreSQL runtime smoke stays separate and opt-in |
| "Ready to push" confidence for ordinary day-to-day work | `just ci-local` | Required and advisory PR lanes | Still does not reproduce clean-runner setup, editable-install packaging checks, full frontend test/build, or GitHub event/branch-protection behavior |
| Real-media, long-running lifecycle, deep `api_stream`, security, dependency, or live PostgreSQL confidence | Weekly/manual-depth commands only when the change reaches that risk; use `just test-session-postgres-live` for explicit local PostgreSQL session smoke | `weekly-validation` for the weekly-owned lanes; the session PostgreSQL live helper itself stays local-only | Too slow and environment-sensitive for routine local or PR use |

Harness ownership for this workflow is intentionally split:

- `justfile`
  - daily local validation entrypoints
- `pre-commit`
  - cheap commit-time hygiene only
- optional `pre-push`
  - last cheap local push guard for `just test-fast` or `just docs-check`
- CI
  - branch feedback, protected `main` validation, and weekly deeper confidence

Recommended local command order for most day-to-day work:

- `just env-check`
  - use once after environment setup or toolchain changes
- focused lanes such as `just test-detectors`, `just test-alert-rules`, or
  `just test-hls`
  - use when the changed seam is already clear and you want the smallest honest lane
- `just test-fast`
  - best default fast production-runtime lane when you want one honest fast runtime pass
- `just test-session-runtime`
  - use only when the branch changes detached-worker startup, FastAPI/session-service agreement, durable session snapshot timing, or backend-selection runtime behavior
  - bundles `tests/test_session_service_worker.py`, `tests/test_session_cli_tooling.py`, `tests/test_api_boundary_sessions_runtime.py`, and `tests/test_session_store_runtime.py`
  - not a default edit-refresh loop; keep it for slower runtime-confidence passes
- `just test-session-postgres-live`
  - use only when the branch needs real PostgreSQL session confidence after the faster parity and file-backed runtime lanes already pass
  - runs the narrow live store smoke and the narrow live FastAPI-to-worker runtime smoke only
  - local-only helper; protected PR CI and `main-gate` do not depend on it
- `just fixture-check`
  - use when the change touches fixture paths, docs, shared metadata, or environment assumptions
- `just dependency-check`
  - use when `pyproject.toml` or `uv.lock` changed and you want a cheap drift check
- `just ci-contract-check`
  - use when changing `.github/workflows/ci.yml`, the workflow-contract
    helpers, or their focused regression tests
- `just ci-local`
  - use before push or PR when you want the closest fast local CI proxy

Use weekly or manual-depth validation only when the change materially reaches:

- real media or `ffmpeg` behavior
- deeper `api_stream` lifecycle and recovery semantics
- persisted session/lifecycle artifacts that only show up in longer runs
- detached-worker runtime confidence you want rechecked in CI without promoting it into the protected PR lane
- dependency or security audit work
- live PostgreSQL backend or operator-flow confidence

For the current session-store branch work, keep that deeper lane modest on
purpose:

- do not add a nightly-only validation lane yet
- do not add an OS or Python-version matrix just for this slice
- do not turn file-backed versus PostgreSQL-backed coverage into a broad PR
  matrix before the focused parity and runtime lanes stop being enough
- treat broader CI depth here as later expansion work, not as routine branch
  polish

Local validation is intentionally incomplete. It cannot prove:

- clean GitHub runner setup and dependency install behavior
- event-driven job activation, path-filter behavior, or branch-protection wiring
- protected `main` PR-only checks such as the full frontend test/build lane
- weekly/manual environment-sensitive checks against slower or external surfaces

For the shortest contributor-facing command summary, use
[../CONTRIBUTING.md](../CONTRIBUTING.md). This document keeps the fuller lane
ownership and CI context.

For cheap local guardrails before those lanes, install and run the repo's
[`pre-commit`](../.pre-commit-config.yaml) hooks. They intentionally stay
small:

- Ruff
- trailing whitespace / EOF fixes
- YAML / JSON / TOML validation
- fixture/environment policy guard

For dependency metadata specifically, use `just dependency-check` when
`pyproject.toml` or `uv.lock` moved. Keep the result simple:

- `uv.lock` moving by itself is treated as suspicious local drift
- paired dependency metadata changes pass, but still need an explanation in PR
  notes or commit text

If you want one last cheap local check before `git push`, install the optional
versioned hook in [git-hooks.md](./git-hooks.md). Keep it narrow on purpose:

- `just test-fast` for runtime/frontend/test/harness changes
- `just docs-check` for docs/workflow-only changes
- do not turn it into a push-time `ci-local` or full-suite gate

That hook is intentionally covered by one small routing test slice instead of
full end-to-end push automation.

Current focused ownership map:

- `src/detectors/`
  - canonical production detector package
- `src/detectors/registry.py`
  - explicit runtime detector registration and catalog metadata
- `tests/test_analyzer_registry.py`
  - explicit registry ownership, mode exposure, detector catalog metadata, and shim behavior
- `tests/test_api_boundary_contracts.py`
  - detector-catalog API contract and structured FastAPI failure envelopes
- `tests/test_detectors.py`
  - production detector rows, media-tool fallback behavior, metric contracts,
    and runtime-row compatibility
- `tests/test_processor.py`
  - production processor routing, detector orchestration, and persistence behavior
- `tests/test_alert_rules.py`
  - shared rule metadata, failure wrapping, and row annotation behavior
- `tests/test_alert_rules_black.py`
  - `video_metrics` black-screen entry, recovery, and source/session isolation
- `tests/test_alert_rules_blur.py`
  - `video_blur` warm-up, motion guards, recovery, and source/session isolation
- `tests/test_plugin_manifest_validation.py`
  - future-facing plugin manifest ownership and id-boundary rules
- `tests/test_session_cli_tooling.py`
  - session CLI adapter behavior, detector catalog CLI output, and read-session snapshot wiring
- `tests/test_session_store_contract.py`
  - durable session-store contract shape and excluded runtime concerns
- `tests/test_session_store_file.py`
  - file-backed session-store parity with `session_io`
- `tests/test_session_store_parity.py`
  - shared file-store versus PostgreSQL-store parity for missing-session
    empty-shape reads, metadata-only snapshots, latest-only `progress`,
    ordered `results`, `latest_result` derivation, and cancel-intent behavior
  - uses the shared in-memory PostgreSQL-like adapter double by default, so
    this lane stays fast and storage-neutral
- `tests/test_api_boundary_sessions_read.py`
  - HTTP-visible session snapshot regression coverage so outer keys,
  null-vs-empty behavior, ordered `results`, and derived `latest_result`
  stay stable while storage changes underneath
- `frontend/src/bridge/contract.session-snapshot.shape.test.ts`
  - bridge normalization coverage so ordered `results`, derived
  `latest_result`, and latest-only progress fields stay stable for desktop
  polling consumers
- `frontend/src/bridge/contract.session-snapshot.collections.test.ts`
  - malformed-row tolerance and proof that bridge reads `latest_result` from
  the final valid ordered result instead of trusting a stale top-level row
- these lanes prove snapshot parity across the current read path, but they do
  not by themselves prove that the full session-store backend evolution is complete
- `tests/test_session_store_runtime.py`
  - default store selection, fallback behavior, rollback-safe runtime config,
    and explicit proof that `postgres` is built only on deliberate opt-in
  - explicit proof that unsupported backend values stay on the file default,
    while missing URL, invalid URL shape, driver/bootstrap failure, and
    missing-schema behavior fail clearly only after explicit PostgreSQL selection
- `tests/test_session_store_postgres.py`
  - PostgreSQL session-store adapter behavior, bootstrap, driver failure
    shaping, and opt-in schema-isolation helpers for live smoke lanes
  - focused coverage:
    metadata/progress/results persistence, snapshot assembly, malformed-row
    tolerance, missing/invalid URL guards, missing-driver failure, no
    accidental auto-create in default lanes, unit-level idempotency, and one
    opt-in real PostgreSQL bootstrap smoke plus one opt-in adapter round-trip
    smoke
- `tests/test_session_runner_store_writes.py`
  - storage-neutral lifecycle/execution/terminal write behavior
- `tests/test_session_runner_progress.py`
  - latest-progress no-op write guard for timestamp-only refreshes
- `tests/test_export_detector_catalog.py`
  - exported detector-catalog JSON contract for frontend-facing tooling
- `tests/test_detector_lab.py`
  - detector-lab runner wiring, experiment families, practical alert policies,
    and export shaping
- `tests/test_detector_lab_real_media.py`
  - slower real-media confidence lane for detector-lab motion/flow behavior
  - weekly confidence here is intentionally behavior-based and artifact-backed;
    when fixture boundary timing shifts slightly across environments, prefer
    suppression/precedence assertions plus emitted CSV diagnostics over exact
    window-number calibration
- `tests/test_detector_lab_representative_media.py`
  - reviewed representative MP4 calibration lane for low-resolution and
    compression cases
  - keeps low-resolution review-only work split honestly:
    black-negative guards, score-shift calibration, and explicit metadata
    boundaries between promoted MP4 blur truth and review-only HLS black
    guards
  - keeps repeated-compression checks in calibration territory:
    black-negative guard, blur-score movement, repeated-burst profile
    consistency, metadata boundary guard, and lead-in versus compression-core
    separation
  - useful for detector tuning and false-positive control, not for exact
    production truth promotion

Use two explicit backend modes when validating this branch:

- everyday synthetic checks
  - force `ESM_ALERT_STORE_BACKEND=file`
  - leave `POSTGRES_ALERT_STORE_REAL_SMOKE` unset or `0`
- live Postgres confidence
  - set `ESM_ALERT_STORE_BACKEND=postgres`
  - provide `ESM_POSTGRES_ALERT_DATABASE_URL`
  - keep `ESM_POSTGRES_ALERT_AUTO_CREATE_TABLES` explicit when you want to
    make bootstrap intent obvious; the current alert path defaults it on
  - set `POSTGRES_ALERT_STORE_REAL_SMOKE=1`

The fast PR/branch CI workflow now pins the synthetic path to the file-backed
alert backend. The weekly workflow owns the real Postgres confidence jobs and
overrides that default in its dedicated live-DB lanes.

Apply the same rule to the in-progress PostgreSQL session-store branch work:

- treat the env shape as parallel where practical:
  - backend selector
  - PostgreSQL database URL
  - optional auto-create flag
  - real-smoke flag
- keep `POSTGRES_SESSION_STORE_REAL_SMOKE` unset or `0` in normal local and PR validation
- the live smoke stays disabled unless both `POSTGRES_SESSION_STORE_REAL_SMOKE=1` and `ESM_POSTGRES_SESSION_DATABASE_URL` are set
- use the session-store isolation helper only in opt-in live PostgreSQL smoke runs
- reset only the known session-store tables; do not point shared checks at a developer's long-lived database state
- if you just ran `just test-session-postgres-live`, clear the PostgreSQL
  session env before returning to the normal file-default lanes:

```bash
unset ESM_SESSION_STORE_BACKEND
unset ESM_POSTGRES_SESSION_DATABASE_URL
unset ESM_POSTGRES_SESSION_AUTO_CREATE_TABLES
unset POSTGRES_SESSION_STORE_REAL_SMOKE
```

The fast CI workflows now make that default explicit too:

- `.github/workflows/ci.yml`
  - `POSTGRES_SESSION_STORE_REAL_SMOKE=0`
- `.github/workflows/branch-ci.yml`
  - `POSTGRES_SESSION_STORE_REAL_SMOKE=0`

Use a manual or service-backed run only when you intentionally want live
PostgreSQL session-store confidence. The focused command is listed in the
session-store validation section below.

For the short fixture and environment ownership rules behind those lanes, use
[fixture-environment-policy.md](./fixture-environment-policy.md).

That policy keeps the fast shared lanes honest. In practice, the repo should reject:

- local-only media or research assets leaking into shared tests or docs
- default test lanes that quietly require optional tools, sockets, or host-specific behavior
- Python tests that hardcode the developer repo root instead of resolving paths dynamically
- shared fixture metadata that quietly points back at local-only assets without an explicit exception

Use `just fixture-check` when you want the lightweight guard directly. Treat
failures there as ownership or portability issues first, not as product
regressions.

Use [docs/merge-readiness-checklist.md](./merge-readiness-checklist.md) when
you want to turn those lane choices into a final branch-ready pass.

For detector-lab specifically:

- focused detector-lab tests and fixture runs validate experimental comparison
  logic
- they are valuable for promotion candidates
- they should not be read on their own as proof of supported runtime behavior

Use the lane split this way when a detector-lab idea may become supported
runtime behavior:

- `tests/test_detector_lab.py`
  - validates lab-only comparison behavior
- production detector, processor, and alert-rule lanes
  - validate supported runtime behavior:
    - `tests/test_detectors.py`
    - `tests/test_processor.py`
    - `tests/test_alert_rules.py`
    - `tests/test_alert_rules_black.py`
    - `tests/test_alert_rules_blur.py`

Promotion needs the production-facing lanes, not only the detector-lab lane.

For the representative-media detector-lab lane specifically, keep one extra
boundary in mind:

- repeated compression fixtures are currently review-only calibration samples
  - they may prove score shape, false-positive resistance, or burst consistency
  - they should not be promoted into exact alert truth until a reviewed runtime
    lane proves a stable subset worth promoting

For current session-store migration work, use these as the smallest useful
focused lanes before you reach for `just test-fast` or `just ci-local`:

Current CI coverage audit for this area:

- `backend-tests` already runs the normal non-`slow`, non-`e2e` Python tests,
  so the store contract, file-store, parity, runtime-selection, service, CLI,
  and PostgreSQL adapter unit coverage are already in the routine backend PR
  lane when backend or contract changes wake it.
- `test-and-build` owns the protected manifest-backed route/session-service
  contract checks for `main` PRs.
- `tests/test_api_boundary_sessions_runtime.py` is also listed in the weekly
  lifecycle manifest and included in the local `just test-session-runtime`
  helper bundle.
  It is marked `slow`, so routine backend PR tests do not collect it even
  though the helper also includes faster supporting worker, CLI, and
  runtime-selection tests.
  Use `just test-session-runtime` locally or weekly lifecycle when you want
  that deeper detached-worker confidence.
- live PostgreSQL session-store smoke remains opt-in and should not be added
  to routine PR CI without a separate CI-expansion decision.
  Keep it manual or weekly until the project intentionally accepts service
  startup cost, database bootstrap ownership, and the extra failure surface in
  ordinary branch feedback. Treat broader live-PostgreSQL automation as
  follow-up work after the focused parity and runtime lanes stop being enough.

Minimum required focused tests for this branch:

- always keep the store contract and parity lane:
  `just test-session-store`
- add detached-worker runtime integration only when the branch changes
  FastAPI start/read/cancel flow, worker startup timing, or parent/worker
  backend agreement:
  `tests/test_session_service_worker.py`,
  `tests/test_session_cli_tooling.py`,
  `tests/test_api_boundary_sessions_runtime.py`
- rely on the existing protected docs and contract checks when the work is
  docs-only or CI-contract-only; do not add a second session-store-specific CI
  lane just to restate that confidence

- start here for store parity and file-default behavior:

```bash
just test-session-store
```

  Use this first when the change is mainly about durable session semantics:

  - file-backed session storage is still the default
  - PostgreSQL session storage still turns on only after explicit backend
    selection plus valid PostgreSQL configuration
  - file and PostgreSQL-like store behavior still agree on the shared contract
  - this lane assumes the normal file-default runtime env; stale PostgreSQL
    runtime env from live smoke work can make unrelated parity or file-store
    tests fail by forcing runtime store resolution through PostgreSQL

  Lane meaning:

  - `just test-session-store`
    - store contract and backend parity
  - `just test-session-runtime`
    - detached-worker runtime confidence over FastAPI, `session_service`,
      CLI/runtime wiring, and backend-selection agreement
  - opt-in live PostgreSQL session-store smoke
    - real-database store smoke only
  - opt-in live PostgreSQL runtime smoke
    - real FastAPI-to-worker PostgreSQL runtime confidence

  Keep these as separate lanes. Do not treat them as one generic PostgreSQL
  validation bucket.

- use runtime integration only when the detached worker path or parent/worker
  backend agreement is part of the risk:

```bash
cd /home/vlad/Projects/election-stream-monitor && \
PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \
.venv/bin/pytest -p no:cacheprovider \
tests/test_session_service_worker.py \
tests/test_session_cli_tooling.py \
tests/test_api_boundary_sessions_runtime.py \
tests/test_session_store_runtime.py -q
```

  This slower lane is the right next step when you need to prove the
  runtime-selection contract across parent and worker paths:

  - file-backed session storage is still the default
  - PostgreSQL session storage still turns on only after explicit backend
    selection plus valid PostgreSQL configuration
  - the detached worker and parent process still agree on the selected backend
  - explicit bad PostgreSQL config fails clearly instead of silently falling
    back in the worker or local runner path
  - for the detailed rollback and failure-policy matrix, use
    `docs/session-persistence-audit.md` instead of repeating that policy here

- cancel behavior across store, service, and route seams:

```bash
cd /home/vlad/Projects/election-stream-monitor && \
PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \
.venv/bin/pytest -p no:cacheprovider \
tests/test_session_store_parity.py \
tests/test_session_service_read_cancel.py \
tests/test_api_boundary_sessions_cancel.py -q
```

- opt-in live PostgreSQL session-store smoke:
  - keep this out of normal local runs, protected PR CI, and `main-gate`
  - keep the helper local-only in this branch; weekly/manual depth can still
    call the same narrow smoke bundles without making them protected CI work
  - use the shared rollout vocabulary consistently here:
    file-backed default, PostgreSQL opt-in, explicit backend selection, and
    live smoke
  - it requires `ESM_SESSION_STORE_BACKEND=postgres`,
    `ESM_POSTGRES_SESSION_DATABASE_URL`,
    `ESM_POSTGRES_SESSION_AUTO_CREATE_TABLES=1`, and
    `POSTGRES_SESSION_STORE_REAL_SMOKE=1`
  - `ESM_POSTGRES_SESSION_AUTO_CREATE_TABLES=1` is explicit bootstrap opt-in
    for the known session-store tables, not default migration policy
  - keep the live contract small and deterministic:
    schema reset, metadata write/read, latest progress, ordered results,
    cancel intent, and stable snapshot shape
  - `just test-session-postgres-live` owns the shared live PostgreSQL env gate
    and runs the two narrow real-DB bundles in order:
    `tests/test_session_store_postgres.py -k real_postgres_session_store`
    then `tests/test_api_boundary_sessions_runtime.py -k live_postgres_runtime`
  - use the helper only after the cheaper parity and file-default runtime
    lanes already say the contract still holds
  - do not grow this lane into broader PostgreSQL rollout, backfill, or
    unrelated slow-runtime coverage
  - use `docs/session-persistence-audit.md` for readiness states,
    default-switch blockers, forward-only/backfill policy, and
    schema/bootstrap ownership instead of repeating that rollout story here

```bash
cd /home/vlad/Projects/election-stream-monitor && \
export ESM_SESSION_STORE_BACKEND=postgres && \
export ESM_POSTGRES_SESSION_DATABASE_URL='postgresql://postgres:postgres@localhost:5432/election_stream_monitor' && \
export ESM_POSTGRES_SESSION_AUTO_CREATE_TABLES=1 && \
export POSTGRES_SESSION_STORE_REAL_SMOKE=1 && \
.venv/bin/pytest -q tests/test_session_store_postgres.py -k real_postgres_session_store
```

Practical lane order for this area:

- use store parity first
- add detached-worker runtime integration only when that runtime path changed
- add live PostgreSQL smoke only when you need confidence in the real database
  path itself

The always-needed store parity lane, the detached-worker runtime lane, and the
opt-in live PostgreSQL session lane now have dedicated `just` wrappers. Keep
the remaining commands direct until the repo has a real reason to wrap them
too.

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
- `just fixture-check`
  - lightweight fixture/environment policy lane
  - catches local-only fixture leakage and obvious repo-root test assumptions
  - use it when a test or doc starts mentioning ignored fixture paths,
    optional-tool assumptions, or machine-specific paths
  - also runs in the non-`main` PR docs/workflow consistency lane
- `just dependency-check`
  - lightweight dependency metadata drift lane
  - flags the highest-suspicion case: `uv.lock` changing without
    `pyproject.toml`
  - keeps broader intent and explanation rules with the PR template and
    merge/readiness checklist
- `just ci-contract-check`
  - focused workflow-contract regression lane
  - runs `tests/test_ci_workflow.py` and
    `tests/test_ci_test_target_scripts.py`
  - best local check when editing `ci.yml`, workflow-helper scripts, or the
    protected/advisory lane contract
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
  - approximates the current fast branch-feedback CI shape:
    `backend-tests` fast synthetic lane, `frontend-checkpoint`, backend Ruff,
    backend mypy, backend pyright, frontend ESLint, and frontend typecheck
  - does not reproduce CI environment setup, the editable-install packaging
    check, full frontend test/build, PR-only policy guards, or weekly lanes

## CI Shape

Use [ci-maintainer-guide.md](./ci-maintainer-guide.md) for the authoritative
required/advisory/informational lane contract. This section stays focused on
what contributors should expect to run later in CI.

The current GitHub Actions workflow is easiest to read as five contributor
facing lanes:

- fast branch feedback
  - `Branch CI` on ordinary branch pushes
  - `frontend-checkpoint`, `backend-tests`, Ruff, frontend typecheck, and
    advisory Pyright/frontend lint
  - closest local proxy: `just ci-local`
- protected `main` PR validation
  - `CI` on pull requests, with `main-gate` plus its required dependency
    chain
  - includes contract checks, integration smoke, full frontend test, and
    frontend production build
  - use [ci-maintainer-guide.md](./ci-maintainer-guide.md) for the exact
    dependency graph and skip/forced-on policy
- informational policy checks
  - `changes`, `pr-template-completeness`, `docs-consistency`
  - useful review/process signal, but not merge blockers for `main`
- weekly deeper confidence
  - Sunday 03:00 UTC or manual dispatch
  - slow media, deeper lifecycle and `api_stream`, audits, packaging smoke,
    and live PostgreSQL confidence
- local-only validation
  - focused `just` recipes, `just test-fast`, `just docs-check`, and
    `just ci-local`
  - faster feedback, but still incomplete compared with protected and weekly
    CI lanes

Failure-only artifacts are now uploaded for the heaviest backend PR lane, the
weekly lifecycle lane, the slow e2e lane, and the weekly `api_stream`
deep-validation lane, starting with plain test logs.
The weekly lifecycle lane also uploads the persisted session files that most
often explain runner state, cancel behavior, and terminal outcomes.

This keeps ordinary branch feedback reasonably fast while giving `main` a
stricter merge barrier. For exact merge-blocking policy, advisory status, and
the protected dependency graph, switch to
[ci-maintainer-guide.md](./ci-maintainer-guide.md).

The split between `Branch CI` and `CI` is intentional:

- branch pushes still get fast feedback
- pull requests to `main` still get the protected gate
- only the PR workflow emits the required `main-gate` context, which
  avoids duplicate-status merge confusion on the same commit SHA

## Workflow Contract Checks

This adds one narrow regression layer around the protected `main` PR CI
contract. Read it as a maintainer safeguard, not as a second workflow
implementation.

For ownership and policy meaning, use
[ci-maintainer-guide.md](./ci-maintainer-guide.md). The local helper surface
is:

- `.github/scripts/ci_workflow.py`
- `.github/scripts/ci_workflow_contract.py`
- `tests/test_ci_workflow.py`
- `tests/test_ci_test_target_scripts.py`

Use this focused local command when changing the workflow-helper layer:

```bash
just ci-contract-check
```

Equivalent raw command:

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/pytest -q \
  tests/test_ci_workflow.py \
  tests/test_ci_test_target_scripts.py
```

The workflow is path-aware, but the contributor-facing consequence is the part
that matters here:

- ordinary PRs and pushes may skip irrelevant lanes
- pull requests targeting `main` still force on the protected work
- contract-sensitive changes should move with matching tests and the owning
  docs update

The CI helper surface uses one manifest-backed source of truth and focused
regression tests. The pieces are complementary:

- `validate_ci_test_targets.py`
  - catches bad manifest shape or scope
- `check_ci_test_paths_exist.py`
  - catches missing CI-owned test files
- `check_ci_target_drift.py`
  - catches workflow/policy/docs drift

Use [ci-maintainer-guide.md](./ci-maintainer-guide.md) for the exact trigger
graph, filter ownership, and protected-policy meaning.

The matching repo helpers are:

- `.github/ci_test_targets.json`
- `.github/scripts/read_ci_test_targets.py`
- `.github/scripts/check_ci_target_drift.py`
- `.github/scripts/check_main_pr_consistency.py`

This section documents validation scope and local reproduction commands. Keep
the CI policy and protection graph in `docs/ci-maintainer-guide.md`, and keep
shorter CI mentions in `docs/README.md` and `docs/contracts.md` role-specific.

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
  `contract_boundary` coverage and also runs the full frontend test and build
  pass for protected `main` PR confidence
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

Where to update ownership when this guard fails:

- shared manifest ownership
  - update `.github/ci_test_targets.json`
  - read-side helper seam: `.github/scripts/ci_target_manifest.py`
- main-PR policy ownership
  - update `.github/scripts/check_main_pr_consistency.py`
- docs ownership
  - update this file only when ownership meaning changes
  - keep `docs/README.md` and `docs/contracts.md` as shorter handoff docs

Chosen detection strategy:

- inspect changed files in protected PR CI
- do not scan the full repo or infer historical ownership

That keeps the guard cheaper and clearer. It should fail when a new guarded
file is introduced without the required ownership updates, not re-lint the
whole repository on every run.

Split-suite registration command:

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
3. `check_fixture_environment_policy.py`
4. `check_ci_target_drift.py`
5. broader workflow or policy checks

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
  - the `SessionStore` contract now lives under that same backend-contract policy,
    so persistence-contract changes should move with focused store tests and
    session persistence docs

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

- skill inventory, frontmatter, and section structure
- readable ordering plus explicit hand-off boundaries
- nearby-skill overlap and explicit deferral coverage
- merged-skill regression markers for the newer multi-mode skills
- representative repo scenarios plus fixed output-shape snapshots
- lightweight regressions for real repo incidents

Use [docs/README.md](./README.md#repo-local-codex-skills) for the skill routing
map. This document owns the test command and validation-lane meaning, not the
full question-to-skill catalog.

The lightweight workflow templates that pair with this skill slice are:

- [`.github/pull_request_template.md`](../.github/pull_request_template.md)
  - keeps purpose, scope, validation, fixture impact, and docs impact explicit
- [branch-purpose-template.md](./branch-purpose-template.md)
  - keeps branch purpose, scope, and split trigger explicit
- [merge-readiness-checklist.md](./merge-readiness-checklist.md)
  - keeps final validation, docs, fixture checks, cleanup, and merge safety in one pass

The fixture/environment policy guard also runs in the non-`main`
`docs-consistency` CI lane. That keeps ignored fixture paths and obvious
machine-specific test assumptions from drifting into shared review branches.

Focused alert-query, seam, incident, and MCP validation:

```bash
.venv/bin/pytest -q tests/test_api_auth.py tests/test_api_rate_limit.py tests/test_api_boundary_settings_env.py tests/test_api_boundary_settings_validation.py tests/test_api_boundary_error_contracts.py tests/test_api_server_cli_runtime.py tests/test_api_server_cli_routes.py tests/test_api_server_cli_output.py tests/test_api_alert_route_auth_policy.py tests/test_api_alert_route_rate_limit_policy.py tests/test_api_alert_route_contracts.py tests/test_alert_query_service_read.py tests/test_alert_query_service_filter.py tests/test_alert_query_service_summary.py tests/test_alert_timeline_service_grouping.py tests/test_alert_timeline_service_filters.py tests/test_alert_incident_summary_service_contracts.py tests/test_alert_incident_summary_service_filters.py tests/test_session_alert_store.py tests/test_session_alert_store_runtime.py tests/test_session_alert_store_runtime_config.py tests/test_session_alert_store_parity.py tests/test_session_alert_store_postgres.py tests/test_session_alert_store_postgres_config.py tests/test_session_io.py tests/test_session_runner_execution_local.py tests/test_api_session_alerts.py tests/test_api_session_alert_incidents.py tests/test_mcp_server_contracts.py tests/test_mcp_server_alerts_behavior.py tests/test_mcp_server_alerts_errors.py tests/test_mcp_fastapi_boundary_split.py tests/test_mcp_fastapi_parity_behavior.py tests/test_mcp_fastapi_parity_edges.py tests/test_mcp_server_incidents_behavior.py tests/test_mcp_server_incidents_errors.py
```

This slice covers the shared read-only alert query service, the FastAPI alerts
boundary, and the MCP adapter over the same service seam. If you change only
one of those layers, this is still the best quick confidence check because it
proves the ownership split still lines up.

The normal local pass stays synthetic by default. The opt-in live PostgreSQL
alert smoke lane requires all of these explicit settings:

- `ESM_ALERT_STORE_BACKEND=postgres`
- `POSTGRES_ALERT_STORE_REAL_SMOKE=1`
- `ESM_POSTGRES_ALERT_DATABASE_URL=postgresql://...`
- optional explicit `ESM_POSTGRES_ALERT_AUTO_CREATE_TABLES=1` when you want to
  make bootstrap intent obvious; the current alert path defaults it on

The store-level live smoke resets alert-store-owned schema, so its URL must
point to a disposable database. It skips when any required setting is absent.

Use the same shared rollout vocabulary here too:

- file-backed default
- PostgreSQL opt-in
- explicit backend selection
- live smoke

Use the same words, but not the same maturity claims:

- alert PostgreSQL is opt-in like session PostgreSQL
- alert validation should not inherit session forward-only, backfill, or
  default-switch wording unless the alert rollout explicitly reaches that stage

Alert lane meaning:

- focused synthetic alert slice
  - alert parity plus FastAPI/MCP/service boundary confidence without a live DB
- opt-in live PostgreSQL alert smoke
  - run after the synthetic parity slice when a reachable disposable PostgreSQL
    database is available
  - proves schema/bootstrap, append/read, ordering, filtering, and raw or
    grouped summary shapes through the alert-store read models
  - does not replace the broader runtime/operator or API/MCP bundles
- weekly/manual live PostgreSQL alert runtime/operator bundles
  - broader runtime/operator confidence for grouped routes, MCP, snapshot
    reads, and CLI behavior over the active backend

Keep alert parity, alert live smoke, and broader runtime/operator-flow
confidence as separate lanes rather than one large PostgreSQL bucket.

The focused synthetic slice already owns the explicit failure policy too:
runtime alert-store tests prove that unset or invalid PostgreSQL bootstrap
input stays harmless in file mode and fails clearly only after explicit
`ESM_ALERT_STORE_BACKEND=postgres` selection.

Use the live smokes when you need confidence in the real database path:

- connection/bootstrap behavior
- real SQL insert/read behavior
- snapshot/API/CLI behavior over the active PostgreSQL backend

For this branch, the smallest useful live checks are:

- store-level smoke after the synthetic slice:
  - `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/pytest -q tests/test_session_alert_store_postgres.py -k real_postgres_alert_store`
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
  - canonical runner-written alerts through the live PostgreSQL backend
  - standalone session snapshot reads over the active backend
  - CLI `read-session` behavior over the active backend

The backend bundle seeds alerts through the real store before exercising public
readers. The runtime/operator bundle owns the stronger write-to-read seam:
deterministic runner output is persisted through the selected PostgreSQL store,
then compared across the session snapshot and FastAPI readers.

Its canonical smoke proves only this compact operator contract:

- runtime selection resolves the PostgreSQL alert store
- the runner persists a small ordered alert sequence
- the session snapshot and raw alert route expose that same normalized sequence
- FastAPI raw alerts plus derived summary and timeline views remain coherent

Detached worker startup, real video processing, MCP, and CLI behavior remain
separate confidence seams so this smoke stays deterministic and fast.

Use either bundle directly:

```bash
ESM_POSTGRES_ALERT_DATABASE_URL='postgresql://...' \
.venv/bin/python scripts/postgres_alert_weekly_backend_confidence.py
```

```bash
ESM_POSTGRES_ALERT_DATABASE_URL='postgresql://...' \
.venv/bin/python scripts/postgres_alert_weekly_runtime_operator_confidence.py
```

Or run both with the umbrella helper:

```bash
ESM_POSTGRES_ALERT_DATABASE_URL='postgresql://...' \
.venv/bin/python scripts/postgres_alert_weekly_confidence.py
```

The umbrella helper runs both bundles in order.

Use the backend bundle when:

- you want stronger real-DB confidence in storage and grouped query behavior
- you are comparing seeded alert behavior across the main public readers

Use the runtime/operator-flow bundle when:

- you want confidence in runner-written alerts under real PostgreSQL mode
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

Those weekly PostgreSQL alert-confidence helpers run through the GitHub
runner's Python environment rather than a repo-local `.venv` path. Keep that
portability intact when editing the helper scripts or workflow steps.

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

- contract owner:
  - `src/session_alert_store.py`
    - defines the narrow storage contract for append/read raw alert rows only
    - owns the runtime-selected default alert store and still defaults to the
      file-backed alert backend in this branch phase
    - filtering, summaries, and grouped incidents stay outside the store contract
  - `src/session_alert_store_runtime_config.py`
    - owns explicit `file` versus `postgres` backend selection for that default
      store through `ESM_ALERT_STORE_BACKEND`
  - `src/session_alert_store_postgres.py`
    - owns the PostgreSQL alert table, preserved read order, the small
      connection/bootstrap path, and the concrete second store implementation
  - `src/session_alert_store_postgres_config.py`
    - owns the narrow env/config parsing for the PostgreSQL bootstrap path:
      `ESM_ALERT_STORE_BACKEND`,
      `ESM_POSTGRES_ALERT_DATABASE_URL`,
      `ESM_POSTGRES_ALERT_AUTO_CREATE_TABLES`, and
      `POSTGRES_ALERT_STORE_REAL_SMOKE`
  - `src/session_alerts.py` and `src/session_alert_incidents.py`
    - public read-model entrypoints accept the store contract explicitly while still
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
  - shared file-store versus PostgreSQL-store parity for append order,
    normalized raw read shape, session-scoped filtering, summaries, grouped
    timelines, grouped incident summaries, known-empty and unknown-session
    behavior, and the file-only malformed-row subset path
- `tests/test_session_alert_store_postgres.py`
  - PostgreSQL alert-store contract coverage for schema/bootstrap plus the
    concrete second backend's read/write drift-sensitive behavior
- `tests/test_session_alert_store_postgres_config.py`
  - narrow Postgres env/config loading, cache behavior, and URL validation
    coverage
- `tests/test_session_io.py`
  - compatibility write-entry coverage showing `append_alert(...)` delegates to
    the default alert-store contract without widening into broader session
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
The repo's `typecheck` dependency group installs `pyright[nodejs]`, so this
path does not rely on a separately installed system `node` binary.

Focused alert-query pyright slice:

```bash
.venv/bin/pyright --project pyrightconfig.json src/session_alert_store.py src/session_alert_store_runtime_config.py src/session_alert_store_postgres.py src/session_alert_store_postgres_config.py src/session_alerts.py src/session_alert_incidents.py src/session_alert_adapter.py
```

Use this when the change stays inside the shared alert persistence and
alert-query slice and you want the narrowest pyright signal that still matches
the branch's current typing focus.

### Repo-Local Skill Tests

The repo-local Codex skills under `./.agents/skills/` are validated with the
focused deterministic slice shown above, not with live model calls.

Harness ownership:

- `tests/test_repo_skills.py`
  - inventory, boundary, scenario, and snapshot assertions
- `tests/repo_skill_expectations.py`
  - inventory, routing, scenario, and snapshot expectation tables
- `tests/skill_test_support.py`
  - parsing and shared assertion helpers
- `tests/fixtures/skill_output_snapshots/`
  - stable example output shapes for selected prompts

This keeps the harness cheap to validate and honest about what it proves.

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
  - stable snapshot keys, null-vs-empty defaults, malformed-row tolerance,
    and alert/result consistency across the current storage split
  - runtime-selected alert-backend parity between the session snapshot route
    and the dedicated alert routes
- `tests/test_api_boundary_sessions_start.py`
  - session start-route behavior
- `tests/test_api_boundary_sessions_cancel.py`
  - session cancel-route status mapping
  - transient `cancelling` response before worker settlement
- `tests/test_api_boundary_sessions_runtime.py`
  - real FastAPI-to-detached-worker runtime integration over the public session
    routes
  - accepted pending metadata, honest early-read `session_not_found`
    tolerance, first readable snapshot, terminal persistence, and durable
    cancel settlement through the worker path
  - routine proof that the parent process and detached worker stay aligned on
    the default file-backed session-store runtime
  - owned by the slower local `just test-session-runtime` helper and the
    weekly `lifecycle-deep` CI lane, not the routine fast PR lanes
  - live PostgreSQL runtime coverage stays in the same file but runs only by
    direct opt-in command with explicit real-DB env plus
    `ESM_SESSION_STORE_BACKEND=postgres`
- `tests/test_session_service_start.py`
  - shared start-session service behavior
- `tests/test_session_service_worker.py`
  - detached worker launch and log-handle behavior
- `tests/test_session_service_read_cancel.py`
  - shared read/cancel service behavior
  - store-backed snapshot/result/progress passthrough
  - transient cancel summary before durable settlement
- `tests/test_session_store_contract.py`
  - backend-neutral session-store cancel contract
- `tests/test_session_store_file.py`
  - file-backed cancel marker compatibility behind `SessionStore`
- `tests/test_session_store_postgres.py`
  - PostgreSQL cancel current-state behavior
- `tests/test_session_store_parity.py`
  - file/PostgreSQL parity for cancel semantics and public snapshot stability
- `tests/test_session_cli_tooling.py`
  - CLI adapter behavior over the shared session service
  - detector-catalog CLI output parity with the canonical registry
  - runtime-selected alert-backend behavior for `read-session`
  - worker-path backend selection, cache refresh, and explicit postgres
    failure behavior for `run-session`
- `tests/test_api_boundary_contracts.py`
  - structured API error payloads
  - detector-catalog route parity with the canonical registry
  - shared route-envelope behavior that sits beside the dedicated session-read tests
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
  - required session snapshot shape, lifecycle field preservation, and tolerant progress timestamp handling
- `frontend/src/bridge/contract.session-snapshot.malformed.test.ts`
  - fail-closed malformed nested payload handling
- `frontend/src/bridge/contract.session-snapshot.collections.test.ts`
  - partially corrupt alert/result collection compatibility
  - `latest_result` recovery from the final valid ordered result row
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
  - hook behavior for local lifecycle polling, cancel-state transitions, typed failures, and store-backed progress updates
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
- worker/backend runtime selection or env inheritance
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

### Minimum Runtime Integration Contract

Keep the slower runtime integration lane deliberately small and end-to-end. It
should prove only that:

- FastAPI `start-session` returns accepted pending session metadata
- the detached worker later persists the first readable snapshot
- FastAPI `read-session` sees the stable snapshot contract rather than
  transport-local guesses
- FastAPI `cancel-session` reaches the worker through durable cancel intent
- terminal session state stays readable after worker settlement

Keep the suite behavioral and narrow:

- prove the parent-process API seam and detached-worker seam still meet
- keep routine runtime coverage file-backed
- treat PostgreSQL-like behavior as store-parity coverage
- keep any live PostgreSQL runtime confidence as a separate opt-in smoke lane
- keep that live runtime smoke narrow:
  accepted start, first persisted readable snapshot, durable cancel delivery,
  and post-settlement terminal readability
- require the same real DB env as the store smoke plus explicit
  `ESM_SESSION_STORE_BACKEND=postgres` so routine file-backed runs and normal
  PR CI cannot collect it accidentally
- keep the live runtime setup shared through
  `tests/api_boundary_sessions_runtime_test_support.py` so backend selection,
  schema reset, request access, and cleanup do not drift across tests
- use the slower detached-worker suite only in explicit lanes:
  local `just test-session-runtime` when that seam changes, and weekly
  `lifecycle-deep` for recurring CI confidence
- do not expand the suite into detector, alert-rule, or frontend UX coverage
- do not repeat store-parity or runner-internal assertions already covered by
  focused tests

Use this lane when you need proof that the real runtime chain still holds:

- FastAPI accepts the session start request
- `session_service.py` launches the detached worker with the active runtime
  backend selection
- the worker persists a readable snapshot that the parent process can later
  read through the public session routes
- durable cancel intent reaches that worker path and later settles to a stable
  terminal snapshot

Run the opt-in live PostgreSQL variant only when the branch changes the real
runtime path between FastAPI, the detached worker, and PostgreSQL-backed
session persistence.

- add explicit runtime backend selection:
  `ESM_SESSION_STORE_BACKEND=postgres`
- the exact runtime-smoke bundle for any helper in this branch is:
  `tests/test_api_boundary_sessions_runtime.py -k live_postgres_runtime`
- reuse the same live env gate and helper ownership already documented in the
  store-smoke section above
- if you want the direct command instead of the helper, export the same live
  store-smoke env first; this live variant stays intentionally separate from
  the default file-backed `just test-session-runtime` helper:

```bash
cd /home/vlad/Projects/election-stream-monitor && \
export ESM_SESSION_STORE_BACKEND=postgres && \
export ESM_POSTGRES_SESSION_DATABASE_URL='postgresql://postgres:postgres@localhost:5432/election_stream_monitor' && \
export ESM_POSTGRES_SESSION_AUTO_CREATE_TABLES=1 && \
export POSTGRES_SESSION_STORE_REAL_SMOKE=1 && \
.venv/bin/pytest -q tests/test_api_boundary_sessions_runtime.py -k live_postgres_runtime
```

- keep the live variant out of routine local loops and normal PR CI
- do not fold `tests/test_session_service_worker.py`,
  `tests/test_session_cli_tooling.py`, `tests/test_session_store_runtime.py`,
  parity tests, or broader slow/e2e selectors into this live helper bundle
- prefer `just test-session-runtime` for the default file-backed runtime lane
- use the live PostgreSQL runtime smoke only after parity and focused runtime
  checks already say the contract still holds
- use `docs/session-persistence-audit.md` for schema/bootstrap, readiness, and
  migration policy instead of copying that detail into validation notes

Do not use this lane as a substitute for the cheaper focused seams:

- use `tests/test_session_store_parity.py` for file versus PostgreSQL-like
  store contract parity
- use the split `tests/test_session_service_*.py` files for service-level
  start/read/cancel and worker-launch behavior
- use the split `tests/test_api_boundary_sessions_*.py` files for route
  payload shape, status mapping, and structured API error behavior

What the default file-backed runtime lane does not prove:

- real PostgreSQL runtime behavior; use the opt-in live variant for that
- detector correctness, alert-rule correctness, or frontend UX behavior
- every runner-internal state transition already covered by runner and store
  suites
- GitHub Actions trigger or protected-lane behavior

Use [`session-model.md`](./session-model.md) for the lifecycle meaning behind
early-read lag, cancel settlement, and durable terminal readability.

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
- `tests/test_e2e_local_session_representative_hls.py`
  - local-only representative HLS intent checks over focused subset playlists
  - includes broad low-res MP4/HLS parity without forcing exact blur counts,
    plus black-negative guards for clean, compression, and review-only low-res
    subsets
- `tests/test_e2e_local_session_representative_hls_ground_truth.py`
  - exact session truth for the few representative HLS subsets that proved stable enough
- `tests/test_e2e_api_stream_representative_hls.py`
  - the same reviewed representative HLS subsets served through the real `api_stream` seam
- `tests/test_e2e_local_session_representative_mp4_ground_truth.py`
  - exact truth for reviewed representative MP4 windows on the real `video_files` seam
- `tests/test_e2e_local_session_representative_mp4_soak.py`
  - capped representative `video_files` confidence in the ordinary slow lane
  - includes a long-window output-shape check plus focused positive and
    false-positive guards on reviewed subsets
  - full-file `pytest -m soak` confidence for selected longer MP4 fixtures
  - repeatability, interruption/recovery, and long-baseline false-positive
    posture stay under `pytest -m soak`, not ordinary PR validation
- `tests/test_e2e_session_ground_truth_api_stream.py`
  - synthetic `api_stream` ground-truth contract cases
- `tests/test_e2e_session_ground_truth_local.py`
  - slower real-media ground-truth matrix

The representative-media support and calibration layers stay separate on purpose:

- `tests/test_representative_hls_test_support.py`
  - representative catalog and helper ownership
  - fixture resolution, route-map shape, promoted-truth consistency, and
    confidence-lane metadata checks across `manifest.json`,
    `expected_results.json`, and `ground_truth.json`
  - guards that promoted exact-truth references still point at real reviewed
    ground-truth cases
- `tests/test_detector_lab_representative_media.py`
  - calibration-oriented score-shape checks for reviewed low-resolution and
    compression windows
  - useful for detector tuning, false-positive control, and promotion-boundary
    review, not exact production truth

Read the representative-media ladder this way:

- support and catalog guards
  - `tests/test_representative_hls_test_support.py`
- reviewed runtime intent
  - `tests/test_e2e_local_session_representative_hls.py`
  - this is where broad low-res MP4/HLS agreement belongs before exact truth
- exact reviewed-subset truth
  - `tests/test_e2e_local_session_representative_hls_ground_truth.py`
  - `tests/test_e2e_local_session_representative_mp4_ground_truth.py`
- transport-backed confidence
  - `tests/test_e2e_api_stream_representative_hls.py`
- calibration-only confidence
  - `tests/test_detector_lab_representative_media.py`
- capped MP4 confidence
  - the non-`soak` lanes inside `tests/test_e2e_local_session_representative_mp4_soak.py`
- full-file MP4 soak confidence
  - `tests/test_e2e_local_session_representative_mp4_soak.py`

Keep the exact representative lanes small. Promote only reviewed stable
subsets into exact truth. Leave borderline, threshold-sensitive, or mainly
diagnostic cases in intent or calibration lanes instead of forcing fake
precision.

For the current low-resolution branch fixtures specifically:

- use reviewed runtime-intent lanes to prove black-negative behavior and broad
  MP4/HLS agreement
- use detector-lab lanes to keep score-shift and false-positive behavior
  visible
- promote exact blur truth only after a reviewed subset proves stable enough

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
PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/pytest -p no:cacheprovider -m "e2e and slow and not soak" tests/test_e2e_*.py -q
```

Note:

- some Electron/HLS tests bind loopback listeners on `127.0.0.1`
- those cases may fail inside stricter sandboxes even when the code is healthy
- if that happens, rerun the same targeted suite in a normal local shell

For representative-media work specifically:

- start with the smallest honest lane
  - support/catalog checks for metadata or fixture-shape changes
  - intent checks for broader detector/runtime behavior
  - exact truth only when a reviewed subset is already proven stable
- use the capped representative MP4 lane when the branch reaches longer
  `video_files` execution but does not need full-file manual-depth coverage yet
  - this lane is the right home for capped output-shape checks and focused
    positive or false-positive guards on reviewed windows
- use the `api_stream` representative lane when the change reaches transport,
  loader, or temp-file lifecycle behavior
- keep the MP4 soak lane as weekly/manual-depth confidence unless the branch is
  explicitly about longer-run runtime behavior
- keep repeatability and interruption/recovery under that soak lane too; they
  should not ride along in ordinary PR validation
- use `pytest -m soak` for the full-file representative MP4 lane when you want
  scheduled/manual-depth confidence without pulling it into ordinary PR
  validation

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
    - detector-bundle invocation and local event-persistence seams
  - `tests/test_session_runner_execution_api_stream.py`
    - extracted live `api_stream` execution-loop helper behavior
    - api-stream cleanup accounting and live helper wiring seams
    - detector-bundle invocation and event-persistence seams
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
  - `tests/test_session_store_runtime.py`
    - current default store resolution
    - invalid-backend fallback to file mode
    - rollback-safe runtime selection behavior
    - explicit proof that PostgreSQL session storage is opt-in, not the default
  - `tests/test_session_runner_store_writes.py`
    - helper-level metadata/progress/result writes through the session-store contract
    - first stop when lifecycle/execution/terminal helpers drift back toward raw file ownership
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
    - stable snapshot shape, null-vs-empty behavior, and ordered `latest_result`
  - `tests/test_api_boundary_sessions_start.py`
    - start success and shared error mapping
  - `tests/test_api_boundary_sessions_cancel.py`
    - cancel success, missing-session cancel failure, terminal cancel rejection, and transient-to-terminal cancel flow
  - `tests/test_api_boundary_contracts.py`
    - structured error envelopes
    - detector-catalog and shared route-envelope behavior
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
- no focused Electron test for read-session missing-session bridge mapping
- no frontend app-flow coverage for cancel-after-completion

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

## What Local Validation Does Not Replace

Local commands are there to shorten feedback loops, not to replace the
protected and scheduled CI lanes. Use CI results for merge readiness, and use
weekly/manual validation when the change reaches slower or environment-shaped
surfaces that routine local runs cannot honestly prove.
