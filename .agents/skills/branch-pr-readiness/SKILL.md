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

When checking drift, explicitly ask:

1. What changed outside the branch purpose?
2. Should that work stay, become a separate commit, or move to a follow-up branch?
3. Does the PR description explain why any adjacent work belongs here?

Use this quick drift test before recommending keep versus split:

1. does the branch still have one primary user-visible or maintainer-visible outcome?
2. do the code, tests, and docs still point at the same changed seam?
3. does the validation story still fit one review unit?
4. did dependency metadata, fixtures, or CI changes appear only because they support that same story?

When the answer starts becoming "two stories," prefer a split.

Use this follow-up extraction hint when the branch is still useful but getting
wider:

- keep work in the branch when it directly supports the stated purpose
- split it into a separate commit when it belongs here but should review on its
  own
- move it to a follow-up branch when it is useful but no longer part of the
  branch story

Treat these as strong split signals:

- a second validation lane is needed for a different seam
- a second owning doc is updated for a different reason than the main branch purpose
- unrelated dependency metadata or fixture changes appear
- the PR description needs "also" more than once to justify the branch
- one part could merge safely even if the other part were reverted

When a follow-up branch is the right answer, prefer a short descriptive name
such as:

- `docs/...` for docs or harness-owner cleanup
- `refactor/...` for internal structure cleanup
- `fix/...` for narrow behavior corrections

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

For commit grouping, use this hint before suggesting the final shape:

1. one commit
   - one narrow theme with one validation story
2. two commits
   - one reviewable split such as runtime/test or code/docs
3. three commits
   - only when the branch really has three distinct review themes such as
     runtime, tests, and docs

For merge readiness:

1. `Readiness summary`
2. `What looks solid`
3. `Open risks`
4. `Missing checks`
5. `Cleanup before merge`
6. `Recommended next step`

For branch-end closure, reuse the merge checklist and confirm:

1. focused validation was run
2. the changed seam has explicit evidence:
   - existing focused test
   - updated nearby test
   - new focused test
   - or docs/workflow-only check when no runtime behavior changed
3. the PR template is honestly filled before CI has to catch it:
   - `Validation Run` lists actual commands
   - `Why these lanes were enough` explains the chosen validation scope
   - `Fixture / Environment Impact` is explicit
   - `Docs Impact` is explicit
   - `Dependency Drift` is explicit when dependency metadata changed
4. docs impact and fixture/environment impact are explicit
5. contract-sensitive work moved with the owning docs and nearby tests
6. any `pyproject.toml` or `uv.lock` change belongs to the branch story or is
   moved out
7. branch purpose still matches the actual content
8. unrelated drift is excluded before merge

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
- When docs or tests change only because the branch widened, say whether they should move with the matching code or leave in a follow-up branch.
- Prefer keeping the code, tests, and owning docs together when they describe one seam; split when they describe different seams.
- Prefer non-destructive checks first, such as `just branch-cleanup`, `git status`, `git diff --stat`, and merged-vs-main checks.
- Keep this skill about branch/PR structure and merge readiness only, not broader release management.
- Before saying a branch is merge-ready, make sure the PR text is complete enough to satisfy the repo's PR-template guard instead of leaving that for CI to discover later.
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
- a PR is almost merge-ready but CI would fail if `Validation Run`, `Fixture / Environment Impact`, or `Docs Impact` are still missing
- a PR is technically ready but still missing `Validation Run`, `Fixture / Environment Impact`, or `Docs Impact`
- docs and tests changed only because the branch widened and now may need to move with different code

## Avoid

- recommending destructive deletion before checking whether the branch has unique commits
- forcing a PR split when the branch still has one coherent purpose
- forcing tiny commits per file or recipe when logical grouping is stronger
- confusing branch/PR structure with CI failure diagnosis
- confusing merge readiness with broad production deployment readiness
- replacing a concrete go or no-go summary with vague project-management language
