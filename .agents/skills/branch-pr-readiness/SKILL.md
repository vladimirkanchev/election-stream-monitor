---
name: branch-pr-readiness
description: Use when the user wants repo-aware help keeping a branch or pull request readable and mergeable in Election Stream Monitor. Best for checking branch purpose drift, suggesting commit and PR shape, summarizing merge readiness, and recommending safe cleanup without drifting into vague project management.
---

# Branch Pr Readiness

Use this skill when the main need is:

- "is this branch still coherent, should it be split, and what can be safely merged or deleted?"
- "how should this work be grouped into commits and PRs so the branch stays readable?"
- "is this branch ready to merge, what still looks risky, and what should we clean up first?"

Typical seams here are long-lived feature branches, stacked PRs, mixed code and
docs changes, merged-vs-main confusion, and final pre-merge cleanup.

## Default approach

Check branch state before proposing action, then keep the answer tied to the
smallest useful workflow decision.

Work from:

1. branch purpose or current PR intent
2. changed file groups or commit themes
3. whether the work is still one coherent story
4. merged-vs-main or stacked-branch state
5. focused validation already run and any open risks
6. safest cleanup or next review action

## Output shape

Choose one mode. Do not mix all three unless the user clearly needs that.

For branch drift and cleanup:

1. `Branch purpose`
2. `Drift assessment`
3. `Most likely branch shape`
4. `Recommended PR shape`
5. `Merged-vs-main state`
6. `Safe cleanup actions`
7. `Best next step`

For commit and PR grouping:

1. `Branch story`
2. `Recommended commit shape`
3. `Recommended PR shape`
4. `What should stay out`
5. `Best next step`

For merge readiness:

1. `Readiness summary`
2. `What looks solid`
3. `Open risks`
4. `Missing checks`
5. `Cleanup before merge`
6. `Recommended next step`

Keep the answer narrow:

- drift
- commit shape
- PR shape
- readiness
- cleanup

Do not expand into broad release-process or project-management advice unless
the user asks for that separately.

## Project-specific rules

- Prefer one coherent branch story over broad “tooling and feature and docs” mixes.
- Prefer one coherent PR when the branch still tells one clear story.
- Split into multiple PRs only when there are genuinely different change themes or dependency layers.
- Group commits by logical slices such as harness, docs, tests, or cleanup when they are meaningfully reviewable on their own.
- Distinguish branch content already in `main` from branch names that still linger locally or remotely.
- When a child branch depends on a parent branch, say that plainly and recommend merge order or retargeting.
- Treat focused passing validation as good evidence, but say plainly when full-suite or environment-specific confidence is still missing.
- Call out unrelated dependency metadata, local-only assets, or notes that should stay out of the PR.
- Prefer non-destructive checks first, such as `just branch-cleanup`, `git status`, `git diff --stat`, and merged-vs-main checks.
- Keep this skill about branch/PR structure and merge readiness only, not broader release management.
- Prefer the smallest workflow decision that unblocks the user:
  - split or keep
  - commit shape
  - PR shape
  - merge or wait

## Skill boundaries

- Use this after at least the branch name, purpose, or current git state is available.
- If the branch history or event sequence is unclear, use `incident-timeline` first.
- If the real blocker is a failing CI check, use `ci-failure-triage` first.
- If the question becomes which validation command to run next, use `test-strategy-review` first.
- If the next question is missing confidence after a split, use `test-strategy-review` next.
- If the main question is whether dependency-file changes belong, use `dependency-change-review` first.

## Good fit examples

- a branch started as real-media hardening but now also carries detector-lab and CI work
- two stacked PRs were merged remotely and it is unclear what can now be deleted
- a harness branch needs to know whether 2 or 3 commits is the cleanest shape
- a mixed worktree needs to be split into one runtime PR and one detector-lab PR
- a workflow branch has passing focused tests but unclear commit, docs, or cleanup readiness
- a stacked PR sequence merged remotely and the final branch needs a clear merge-readiness summary

## Avoid

- recommending destructive deletion before checking whether the branch has unique commits
- forcing a PR split when the branch still has one coherent purpose
- forcing tiny commits per file or recipe when logical grouping is stronger
- confusing branch/PR structure with CI failure diagnosis
- confusing merge readiness with broad production deployment readiness
- replacing a concrete go or no-go summary with vague project-management language
