---
name: dependency-change-review
description: Use when the user wants repo-aware help judging whether local dependency metadata changes in Election Stream Monitor actually belong in the current branch. Best for classifying changes in files such as pyproject.toml and uv.lock as intentional, incidental, or branch drift.
---

# Dependency Change Review

Use this skill when the main need is: "do these dependency-file changes belong to this branch, or are they just drift?"

This repo commonly needs dependency-change review across:

- `pyproject.toml`
- `uv.lock`
- branch-scoped tooling or harness changes that may have updated local dependency metadata
- commits where code/doc changes are ready but dependency-file edits are still unclear

## Default approach

Classify the dependency change before deciding whether to keep it.

Work from:

1. changed dependency metadata files
2. the branch purpose
3. whether the dependency change is required by the branch behavior or tooling
4. whether the change is intentional, incidental, or drift
5. the safest next action

Use these classes:

- `intentional`
  - needed for the branch's actual code, harness, or test behavior
- `incidental`
  - caused by local environment actions but still plausibly related to the branch
- `branch drift`
  - not required by the branch story and best kept out

## Output shape

Use this order:

1. `Changed dependency files`
2. `Most likely classification`
3. `Why it belongs or does not belong`
4. `Best next action`
5. `Validation or follow-up`

## Project-specific rules

- Keep this skill narrow: local dependency metadata only, not supply-chain or vulnerability review.
- Judge dependency changes against the branch mission, not against general "newer is better" instincts.
- If a lockfile changed only because local commands were run, say so plainly.
- Prefer keeping unrelated dependency churn out of workflow, docs, detector, or alert-only branches.
- If a dependency change is required for the harness, test, or CI shape the branch introduced, say that clearly and keep it with the branch.
- If the right answer is "inspect the diff first," say that rather than guessing.

## Skill boundaries

- Use this when the user is deciding whether dependency metadata drift belongs in the current work.
- If the main question is branch cleanup, PR shape, or merge readiness for the whole branch, use `branch-pr-readiness` first.
- If the main question is a failing dependency-related CI job, use `ci-failure-triage` first.

## Good fit examples

- `pyproject.toml` and `uv.lock` changed during harness work and it is unclear whether they belong
- a branch looks ready except for local dependency metadata edits
- a tooling branch may genuinely need a dependency extra or lockfile refresh
- a code-only branch picked up dependency-file noise after local installs

## Avoid

- treating every lockfile change as meaningful
- treating every dependency diff as branch drift without checking the branch purpose
- expanding into security or package-governance review
- recommending commits before checking whether the dependency change supports the branch story
