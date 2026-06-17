---
name: readme-alignment-review
description: Use when the user wants repo-aware review or polish for one root README section in Election Stream Monitor. Best for checking current-project accuracy, root-README fit, readability, and whether a section should stay, shrink, or move to deeper docs.
---

# Readme Alignment Review

Use this skill for one root `README.md` section at a time when the main need is:

- "does this section still match the current project?"
- "is this section too heavy for the root README?"
- "what is the smallest useful polish here?"

Typical seams are project-stage framing, wording and flow, reader-versus-maintainer balance, and whether detail belongs in `README.md` or a narrower doc.

## Default approach

Work in this order:

1. current code and tests
2. owning docs for the touched subsystem
3. the exact README section
4. root-README fit
5. smallest useful edit

Bias toward trimming, clarifying, or rerouting before rewriting.

Use this `README fit` decision explicitly:

- `keep here`
  - the section belongs in the root README at its current level
- `shrink here`
  - the section belongs here, but carries too much detail
- `move to deeper docs`
  - the topic is real, but the owning detail belongs in a narrower doc

## Output shape

Use this order:

1. `Section`
2. `Rating`
3. `What works`
4. `README fit`
5. `Stage honesty`
6. `Heavy-section warning`
7. `Smallest useful rewrite`

Keep the answer short unless the user asks for a broader pass.

## Project-specific rules

- Do not let the root README imply more maturity, deployment readiness, or feature coverage than the code supports.
- Rate sections against the current local-first advanced-prototype stage, not a future platform shape.
- Keep the root README overview-first. If a section becomes maintainer-heavy, runbook-heavy, or workflow-catalog-heavy, recommend moving detail out.
- If a section is accurate but heavy, prefer `shrink here` over calling it drift.
- If a section touches API, CLI, persisted data, or bridge shape, check `docs/contracts.md` before recommending broader wording.
- Keep three audiences in view:
  - casual interested readers
  - mid/senior engineers
  - AI-assisted coding agents
- Prefer narrow owner docs such as `docs/README.md`, `docs/testing-and-validation.md`, and `docs/architecture.md` over growing the root README indefinitely.

## Skill boundaries

- Use this when the main question is root-README fit, wording, or current-stage accuracy.
- If the main problem is repo-wide docs drift, use `docs-drift-check` first.
- If the main question is diagram correctness or runtime-boundary clarity, use `architecture-diagram-review` first.
- If the user already knows the README needs edits and wants the wording pass, this skill can lead directly into `docs-alignment`.
- If the main question is branch scope or whether the README change belongs in the branch, use `branch-pr-readiness` first.

## Good fit examples

- a root README section feels too heavy and may belong in deeper docs
- a root README workflow section feels too heavy and may need to shrink and point to deeper docs
- the project stage changed and the README may now overstate maturity
- the root README may now overstate project maturity after a runtime boundary refactor
- a section reads well for engineers but not for casual interested readers
- the README matches the code, but still needs trimming to stay readable

## Avoid

- turning one section review into a whole-doc rewrite by default
- treating every wording preference as real drift
- expanding the root README when a narrower owner doc is the better home
- collapsing maintainer-doc detail into the root README
- implying more product or runtime maturity than the code supports
