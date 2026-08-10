# Manual Prompt Evaluation

Use this compact set to review skill routing after material changes to active
skill descriptions, boundaries, or consolidation. Run one case in a fresh
conversation with repository context available. Paste only the **User prompt**;
do not reveal the expected route or evaluation criteria before the response.

Record the run date, repository commit, visible model label, selected primary
skill, result (`pass`, `partial`, or `fail`), and one concise reason outside
this file. Do not commit full model outputs or use this set in CI.

## Plan Detector Work

- Case ID: `plan-detector-work`
- User prompt: "Before I start tuning detector thresholds, should I first finish static-analysis cleanup, improve detector confidence tests, or prepare the project for cloud deployment? Rank the next two branches for the local-first pilot and explain the trade-offs."
- Expected primary skill: `task-planning-evaluation`
- Acceptable secondary handoff: `test-strategy-review` after the priority decision if validation design needs detail.
- Required response properties: rates or clearly compares priority; considers the pilot stage; recommends a bounded next branch rather than a broad roadmap.
- Avoid: proposing a PR shape, designing every detector test, or treating cloud deployment as the immediate default.

## Triage Backend CI

- Case ID: `triage-backend-ci`
- User prompt: "The backend type-check job failed in GitHub Actions after my change. The output says a source module cannot resolve an imported package. Identify the likely failure class and give me the smallest local command to reproduce before suggesting a fix."
- Expected primary skill: `ci-failure-triage`
- Acceptable secondary handoff: `dependency-change-review` only if the reproduction shows dependency metadata drift.
- Required response properties: identifies the CI owner and likely class; gives a focused local reproduction; distinguishes an environment or dependency problem from a code-type error.
- Avoid: changing unrelated CI lanes, assuming a root cause without the focused reproduction, or starting a broad incident investigation.

## Review Detector Boundary

- Case ID: `review-detector-boundary`
- User prompt: "I want to lower the practical blur threshold because one reviewed clip is not alerting. Review whether this belongs in detector facts, alert rules, or the processor, and name the smallest honest tests before I edit the threshold."
- Expected primary skill: `detector-rule-review`
- Acceptable secondary handoff: `test-strategy-review` for a detailed validation-lane decision; `real-media-validation-review` when decoded-media evidence becomes central.
- Required response properties: separates detector facts from alert decisions and orchestration; preserves explicit mode support; recommends focused tests without duplicating cross-layer coverage.
- Avoid: moving alert-state behavior into detector tests or treating one clip as sufficient calibration evidence.

## Review Persistence Parity

- Case ID: `review-persistence-parity`
- User prompt: "The file-backed and PostgreSQL backends now return different incident ordering for the same session. Review the parity boundary, identify the likely owner, and suggest the smallest checks before we change either backend."
- Expected primary skill: `persistence-backend-review`
- Acceptable secondary handoff: `test-strategy-review` for the cheapest validation lane after the parity contract is clear.
- Required response properties: distinguishes backend selection from data-contract parity; includes shared alert reads and incident ordering; keeps access-policy concerns separate unless evidence reaches them.
- Avoid: proposing a database redesign, treating PostgreSQL as the default runtime path, or changing API authentication without evidence.

## Align Contract Documentation

- Case ID: `align-contract-documentation`
- User prompt: "The FastAPI route implementation and regression tests now return a changed session payload, but the contract documentation still describes the old field shape. Identify the owning documentation update and the smallest validation needed after the code is already stable."
- Expected primary skill: `docs-alignment`
- Acceptable secondary handoff: `docs-drift-check` only if the actual code/test contract is still unclear before editing.
- Required response properties: starts from code and tests; identifies one owning document; replaces stale wording rather than copying the payload explanation across several documents.
- Avoid: redesigning the API, treating a wording preference as drift, or creating a broad documentation rewrite.

## Assess PR Readiness

- Case ID: `assess-pr-readiness`
- User prompt: "My branch contains detector-test refactoring, one fixture-catalog correction, and documentation updates. Assess whether it is ready for a PR to main, whether the changes should be split, and which final checks are proportionate before merge."
- Expected primary skill: `branch-pr-readiness`
- Acceptable secondary handoff: `test-strategy-review` only if the final validation lane is uncertain.
- Required response properties: evaluates scope and drift; proposes coherent commit or PR boundaries; selects proportional final checks and states remaining risks.
- Avoid: deciding detector behavior, inventing release version changes, or presenting merge readiness without inspecting branch evidence.
