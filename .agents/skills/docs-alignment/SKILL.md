---
name: docs-alignment
description: Use when the user wants repo-aware help keeping project docs or code docs aligned with the current Election Stream Monitor code, tests, and CI shape. Best for checking documentation drift, proposing concise updates, and removing low-value repetition without turning the task into endless docs polishing.
---

# Docs Alignment

Use this skill when the main need is:

- "which project docs are drifting, what is the owning doc, and what is the smallest useful update?"
- "do the module, class, or function docstrings still describe what this code actually does?"

Typical seams here are root and maintainer docs, testing/CI guides, repo-local
skill and harness docs, runtime-versus-`detector_lab` explanations, and module
or helper docstrings that no longer match current responsibilities.

## Default approach

Check code and tests first, then update only the owning docs or closest
high-signal docstrings. Work from:

1. changed code, tests, or CI/workflow files
2. current user-facing docs, maintainer docs, or nearby docstrings
3. source-of-truth ownership
4. smallest concise update
5. low-value repetition that can be removed instead of copied

Prefer one owner, not three copies. Use this docs-owner hint to choose the
smallest surface that owns the change.

- project overview or contributor entrypoint: root `README.md`
- maintainer routing, branch workflow, or skill/doc map: `docs/README.md`
- validation lanes, CI checks, or harness command guidance: `docs/testing-and-validation.md`
- branch purpose, execution pattern, or medium-task checklist: `docs/branch-purpose-template.md`
- subsystem behavior, contracts, or promotion rules: closest narrower doc under `docs/`
- code-level responsibility drift: nearest module, class, or function docstring

Use this public-contract check before concluding that docs updates are local
only:

- does the change affect an API route, CLI output, persisted session data, or
  frontend/backend bridge shape?
- if yes, check `docs/contracts.md` first, then the nearest boundary tests
- if no, keep the update in the nearest owning maintainer doc or docstring

## Output shape

Use this order:

1. `Drift summary` or `Docstring drift`
2. `Owning docs` or `Owning code surface`
3. `Recommended updates`
4. `Repetition to remove` or `Low-value wording to remove`
5. `Best next doc pass` or `Best next code-doc pass`

Keep the split explicit:

- use the `Drift summary` / `Owning docs` wording for README and maintainer-doc work
- use the `Docstring drift` / `Owning code surface` wording for module, class,
  and function docstring work
- do not mix both modes unless the same change really affects both public docs
  and code docs

## Project-specific rules

- Follow the repo source-of-truth order: code and tests first, then contract/lifecycle docs, then architecture/reviewer docs, then README-level summaries.
- Prefer small targeted edits over broad documentation rewrites.
- Name the owning doc instead of updating the same guidance in multiple files.
- If a doc already says the right thing at the right level, leave it alone.
- Keep the runtime-vs-`detector_lab` split explicit when detector experimentation changes.
- When CI, skills, or harness commands change, check `docs/testing-and-validation.md`, `docs/README.md`, and the root `README.md` before touching anything broader.
- Keep docstrings aligned to current code purpose, not historical
  implementation details.
- Prefer short high-signal docstrings over restating obvious code mechanics.
- For tests, describe behavioral intent rather than repeating the test name in prose.
- If the best explanation already exists in an owning maintainer doc, keep the
  docstring short and point at responsibility rather than copying the whole
  explanation.
- If the drift is only wording preference, say so and avoid unnecessary edits.

## Skill boundaries

- Use this after the relevant code, tests, or workflow changes are understood.
- If the main problem is a failing CI policy or docs check, use `ci-failure-triage` first.
- If the behavior itself is still unclear, use `summarization` or `incident-timeline` first.
- If the next question is missing confidence rather than docs drift, use `test-strategy-review` next.
- If the next question is broader task priority rather than documentation
  drift, use `task-planning-evaluation` first.

## Good fit examples

- the harness commands changed and the README plus testing guide no longer match
- detector-lab structure changed and the runtime-versus-experimental split is now unclear in docs
- CI lane ownership changed and the maintainer docs still describe the old shape
- several docs repeat the same guidance and one owning doc should replace the copies
- `practical_alerts.py` docstrings no longer match the newer evaluation-context shape
- a production runtime module docstring still sounds dict-shaped after typed-row refactors
- a test-helper docstring explains mechanics instead of test purpose

## Avoid

- treating every wording preference as real drift
- rewriting large docs when one or two targeted edits would fix the problem
- duplicating the same guidance across README, maintainer docs, and subsystem docs
- polishing docs before the underlying code or workflow change is stable
- rewriting README-level guidance into code docstrings
- adding long comments where a short docstring is enough
