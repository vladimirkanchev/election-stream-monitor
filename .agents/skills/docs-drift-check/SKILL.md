---
name: docs-drift-check
description: Use when the user wants a concise repo-aware audit of whether Election Stream Monitor docs are actually drifting from current code, tests, contracts, or workflow. Best for classifying drift, naming the owning doc, and deciding the smallest correct follow-up before editing.
---

# Docs Drift Check

Use this skill when the main need is:

- "is this doc really outdated, or just lighter than the owning maintainer doc?"
- "what kind of drift is this, and how serious is it?"
- "which doc should change first before we start polishing?"

Typical seams are root docs versus maintainer docs, contract-sensitive notes, validation and CI ownership docs, and subsystem docs that may no longer match runtime behavior.

## Default approach

Check evidence before calling something drift.

Work in this order:

1. changed code, tests, contracts, or workflow files
2. the claimed doc target
3. the closest owning doc
4. `Drift class` and severity
5. the smallest correct follow-up

Use this `Drift class` explicitly:

- `no real drift`
  - the doc is still accurate at its intended level
- `wording drift`
  - wording is stale or awkward, but behavior meaning still matches
- `behavior drift`
  - runtime or user-visible behavior changed and the doc no longer matches
- `contract drift`
  - API, CLI, persisted data, or bridge semantics drifted
- `workflow drift`
  - validation, CI, harness, or maintainer workflow docs no longer match reality

Use this severity explicitly:

- `low`
- `medium`
- `high`

## Output shape

Use this order:

1. `Drift target`
2. `Current accuracy`
3. `Drift class`
4. `Severity`
5. `Owning doc`
6. `Smallest useful fix`
7. `What should move with it`

Keep the answer diagnostic and concise.

## Project-specific rules

- Do not call something drift just because one doc is shorter, broader, or more overview-level than another.
- The root `README.md` can stay intentionally lighter than maintainer docs if it is still accurate.
- Check code and tests first; evidence comes before polish.
- If the issue touches API, CLI, persisted data, or bridge shape, treat it as potential `contract drift` and check `docs/contracts.md` plus nearby boundary tests.
- If the issue touches CI, validation lanes, skills, or harness commands, treat it as potential `workflow drift` and check `docs/testing-and-validation.md` and `docs/README.md` first.
- Prefer one owning doc and one smallest fix over synchronized rewrite plans.
- If there is `no real drift`, say so plainly and avoid unnecessary edits.

## Skill boundaries

- Use this when the main question is whether docs are truly drifting and what owns the fix.
- If the user already knows the docs need updates and wants the edit pass, use `docs-alignment` next.
- If the main question is root README fit or readability, use `readme-alignment-review` first.
- If the main question is diagram honesty or visual architecture drift, use `architecture-diagram-review` first.
- If the main question is branch scope or whether the docs change belongs in the branch, use `branch-pr-readiness` first.

## Good fit examples

- a README section is shorter than the maintainer docs and we need to know whether that is real drift
- a FastAPI auth doc may now describe the wrong protected boundary after route changes
- the harness commands changed and it is unclear whether the README, maintainer docs, or testing guide is the real owner
- a subsystem doc still describes an older runtime behavior and we need to classify how serious that is
- a doc may feel stale, but we first need to know whether the problem is wording drift, behavior drift, contract drift, or workflow drift

## Avoid

- turning the answer into a full docs rewrite plan
- treating every wording preference as meaningful drift
- replacing owning-doc analysis with broad README edits
- collapsing drift detection into general docs polishing
- implying contract or runtime drift without checking code and tests first
