---
name: manual-validation-planner
description: Use for concise Election Stream Monitor operator-facing local smoke plans. Excludes automated test selection, CI triage, and frontend seam review.
---

# Manual Validation Planner

Use this skill when the main need is:

- "what should I click or run locally before merge?"
- "what is the smallest honest manual smoke check for this branch?"
- "which local app flow should I verify after backend, playback, or alert changes?"

Typical seams here are Electron startup and session flow, FastAPI local or
`share` mode, playback and polling behavior, alert rendering, and
operator-visible `api_stream` confirmation.

## Default approach

Start from the changed seam, then keep the plan short and executable.

Work from:

1. changed boundary or discussed risk
2. nearest user-visible or operator-visible flow
3. smallest realistic local setup
4. what to click, run, or watch
5. success signal versus failure signal
6. next best automated or focused follow-up if the manual step fails

Prefer the shortest honest smoke path that checks the behavior people will
actually see.

## Output shape

Use this order:

1. `Validation target`
2. `Best local flow`
3. `What to click/run`
4. `What to watch for`
5. `Failure signal`
6. `Best follow-up automation`

Keep it concrete and short.

## Project-specific rules

- Prefer one small end-to-end manual path over a broad exploratory checklist.
- Distinguish desktop app checks from backend-only checks.
- Name the owning seam plainly:
  - Electron shell
  - frontend bridge
  - FastAPI route
  - playback flow
  - alert rendering
  - session progress
- For playback or polling changes, include the first visible UI state to confirm.
- For alert-related changes, include where alerts or incidents should appear.
- For FastAPI or `share` mode changes, mention the smallest safe local startup path.
- If the branch already has strong focused automated coverage, say the manual pass is only a smoke check, not the main confidence source.
- If the behavior is not realistically manual to verify locally, say that and point to the best focused automated lane instead.

## Skill boundaries

- Use this when the main need is a local human-run validation path.
- If the user mainly needs the smallest automated lane to run, use `test-strategy-review` first.
- If the branch shape or merge readiness is still unclear, use `branch-pr-readiness` first.
- If the local behavior already failed and the event order is unclear, use `incident-analysis` first.
- If the main blocker is a failing CI job, use `ci-failure-triage` first.

## Good fit examples

- before merge, what should I click locally after touching playback status and alert rendering?
- a FastAPI share-mode change needs a small manual smoke plan rather than a full release checklist
- a session lifecycle change needs one quick desktop-path verification before merging
- an `api_stream` UI polish change needs the smallest local operator-visible check

## Avoid

- turning the answer into a full QA plan
- recommending broad manual exploration without a target seam
- replacing a clear local smoke plan with only automated commands
- pretending a manual step is enough when the main confidence should still come from focused tests
