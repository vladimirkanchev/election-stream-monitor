---
name: test-strategy-review
description: Use when the user wants repo-aware help deciding what Election Stream Monitor tests to add, trim, or run first. Best for judging coverage value and selecting the cheapest honest validation lane without expanding into generic test-suite generation.
---

# Test Strategy Review

Own coverage value and the cheapest honest validation. Start from a known
behavior, changed seam, or current test area; do not infer a test plan from a
branch title alone.

## Default approach

Identify the closest owning boundary, then decide whether the need is to add,
trim, or validate. Compare observable behavior, failure signal, runtime cost,
and environment sensitivity. Slow or environment-coupled tests are not
automatically low value.

Force the decision before naming a command:

1. What existing focused test, workflow check, or `just docs-check` already proves the change?
2. If none, what single nearby test would protect the missing contract gap?
3. If no automated lane is honest, say `manual confidence only for now` and name the manual step.

Use the validation-lane chooser in
[docs/testing-and-validation.md](../../../docs/testing-and-validation.md).
Start with the nearest focused harness lanes; use `just test-fast` only when
several production seams changed and `just ci-local` for push readiness after
the focused signal.

## Output shape

Choose one mode.

For a gap:

1. `Gap`
2. `Why it matters`
3. `Best test layer`
4. `Recommended lane`
5. `Cheapest useful test`

For quality:

1. `Strong tests`
2. `Weak or low-value tests`
3. `Main risk`
4. `Best cleanup`
5. `What not to cut`

For validation:

1. `Change area`
2. `Closest owning boundary`
3. `Best first command`
4. `Why this lane fits`
5. `When to run something broader`
6. `Next broader option`

## Skill boundaries

- Use `summarization` or `incident-analysis` first when the behavior is still unclear.
- Use `ci-failure-triage` first for a failing CI job.
- Use `branch-pr-readiness` first for branch drift or merge workflow.
- Use detector, fixture, real-media, frontend, or manual-validation skills when their specialized seam is the real decision; return here for the general cheapest-lane choice.

## Avoid

- generating every possible test
- treating every slow test as weak
- deleting tests without comparing lost confidence
- repeating the full command catalog from the validation guide
