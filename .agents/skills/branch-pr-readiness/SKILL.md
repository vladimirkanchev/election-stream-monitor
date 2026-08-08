---
name: branch-pr-readiness
description: "Use for Election Stream Monitor branch scope, commit grouping, PR shape, drift, and merge readiness. Excludes generic summaries, roadmap priority, and test selection."
---

# Branch Pr Readiness

Own branch scope, commits, PR shape, and merge readiness. Start once the
branch name, purpose, or current Git state is known.

## Default approach

Inspect the branch purpose, changed themes, merge-base state, focused evidence,
and open risks. Then decide whether the work is one coherent PR, needs a
reviewable commit split, or belongs in a follow-up branch.

Use this drift test:

1. does the branch still have one primary user-visible or maintainer-visible outcome?
2. do code, tests, and owning docs support that outcome?
3. does one validation story cover the changed seam?
4. do dependency, fixture, or CI changes directly support it?

When the answer becomes two stories, use this follow-up extraction hint:

- keep direct support work in the branch;
- split independently reviewable work into its own commit;
- move unrelated but useful work to a follow-up branch.

Strong split signals are an independently mergeable change, a different
validation seam, or an extra PR explanation that needs repeated “also”. Prefer
non-destructive evidence such as `git status`, `git diff --stat`, and
merged-vs-main checks.

## Output shape

Choose one mode.

For drift:

1. `Branch purpose`
2. `Drift assessment`
3. `Most likely branch shape`
4. `Recommended PR shape`
5. `Merged-vs-main state`
6. `Safe cleanup actions`
7. `Best next step`

For commit grouping, use:

1. `Branch story`
2. `Recommended commit shape`
3. `Recommended PR shape`
4. `What should stay out`
5. `Best next step`

Use one commit for one validation story, two for a meaningful implementation
and evidence split, and three only for three independently reviewable themes.
Prefer one coherent PR when the branch still has one outcome.

For merge readiness:

1. `Readiness summary`
2. `What looks solid`
3. `Open risks`
4. `Missing checks`
5. `Cleanup before merge`
6. `Recommended next step`

Before recommending merge, confirm focused evidence, explicit docs and
fixture/environment impact, dependency-file fit, and an honestly complete PR
template when one is required.

## Skill boundaries

- If history or event order is unclear, use `incident-analysis` first.
- If a CI check is failing, use `ci-failure-triage` first.
- If the question is which validation to run, use `test-strategy-review` first.
- If confidence is missing after a split, use `test-strategy-review` next.
- If dependency-file ownership is the main question, use `dependency-change-review` first.
- Do not replace `summarization` with a PR-ready change summary or `task-planning-evaluation` with roadmap priority.

## Avoid

- forcing a split when the branch has one coherent purpose
- proposing destructive cleanup before checking unique commits
- treating merge readiness as release or deployment readiness
- substituting vague project management for a concrete split, keep, merge, or wait decision
