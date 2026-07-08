---
name: test-strategy-review
description: Use when the user wants repo-aware help deciding what tests to add, what low-value tests to trim, or what the smallest honest local validation step is in Election Stream Monitor. Best for keeping test decisions practical, lane-aware, and tied to the current repo seams instead of expanding into whole-suite generation.
---

# Test Strategy Review

Use this skill when the main need is:

- "what confidence is still missing after this change?"
- "which tests here are high-signal, which are weak, and what cleanup is actually worth doing?"
- "what is the cheapest useful command to run for this change?"

Typical seams here are runtime detectors and rules, processor/session flow,
HLS or `api_stream`, frontend/bridge behavior, detector-lab work, and docs or
workflow-only changes.

## Default approach

Start from the current change or current test suite. Work from:

1. changed files, discussed behavior, or current test file
2. closest owning boundary
3. whether the need is add, trim, or validate
4. behavior coverage versus implementation detail coverage
5. runtime cost and environment sensitivity
6. cheapest honest lane that fits the decision

Use `docs/testing-and-validation.md` for current validation lanes.

Force the test decision before recommending commands:

- what existing focused test or `just docs-check` already proves the change?
- if none, is one nearby focused test worth adding before broader validation?
- if no honest automated lane fits yet, say `manual confidence only for now`
  and name the manual step plainly

Use this validation-lane chooser before recommending commands:

- docs, repo-skill, or workflow-only change
  - start with `just docs-check` or the focused repo-skill test slice
- one narrow runtime boundary
  - start with the nearest focused lane such as `just test-detectors`,
    `just test-alert-rules`, `just test-processor`, or `just test-hls`
- several production runtime boundaries changed together
  - start with `just test-fast`
- push or PR readiness question
  - use `just ci-local` after the focused lane, not before it
- real-media or environment-coupled confidence need
  - use the focused confidence lane only when the change actually needs it

## Output shape

Choose one mode first.

For missing coverage:

1. `Gap`
2. `Why it matters`
3. `Best test layer`
4. `Recommended lane`
5. `Cheapest useful test`

For test-quality review:

1. `Strong tests`
2. `Weak or low-value tests`
3. `Main risk`
4. `Best cleanup`
5. `What not to cut`

For local validation choice:

1. `Change area`
2. `Closest owning boundary`
3. `Best first command`
4. `Why this lane fits`
5. `When to run something broader`
6. `Next broader option`

Keep add, trim, and validate outputs distinct. If two modes matter, finish the
main mode first and keep the second short.

## Project-specific rules

- Prefer one focused test over broad redundant suites.
- Name the nearest changed module family and the nearest current test owner.
- Prefer extending existing nearby test files before proposing a new suite.
- Distinguish slow-but-valuable real-media confidence tests from genuinely low-value repetition.
- Call out environment-coupled tests separately from redundant tests; they are not the same problem.
- Place proposed coverage in the cheapest honest lane: `fast lane`, `slow lane`, or `confidence lane`.
- Prefer focused harness lanes such as `just test-detectors`, `just test-processor`, `just test-alert-rules`, `just test-hls`, `just test-frontend`, `just test-detector-lab`, `just test-real-media`, and `just docs-check` before recommending `just ci-local`.
- Use `just test-fast` when several production runtime seams changed together, not for every small edit.
- Use `just ci-local` as the main "ready to push?" lane, not as the default first response.
- For detector-lab work, keep synthetic and real-media lanes distinct.
- For docs or repo-skill-only changes, prefer `just docs-check` or the focused repo-skill test slice before broader validation.
- If a behavior is intentionally manual-only for now, say `manual confidence only for now`.
- Prefer the cheapest lane that still protects the real risk.

## Skill boundaries

- Use this after the behavior or current test area is understood well enough to judge add, trim, or validate decisions.
- If the user still does not understand what happened, use `summarization` or `incident-timeline` first.
- If the real blocker is a failing CI job, use `ci-failure-triage` first.
- If the branch itself is messy and the question is really merge/readiness workflow, use `branch-pr-readiness` first.

## Good fit examples

- a blur-rule tweak needs `test-alert-rules` rather than the whole suite
- an HLS loader change should use `test-hls` before `ci-local`
- detector-lab tests feel over-specific and need a trim pass
- a test file has many small threshold cases that may be better merged into parameterized coverage
- a contract gap needs the cheapest focused lane rather than a weekly suite
- a detector-lab scoring change should start with `test-detector-lab` and only use `test-real-media` if the change needs the confidence lane

## Avoid

- asking for every possible test
- treating every slow test as low quality
- recommending broad deletions without checking confidence loss
- defaulting to a slow lane when a focused fast lane would protect the change
- recommending the full project test suite for every change
- turning the review into a request to rewrite the whole suite
