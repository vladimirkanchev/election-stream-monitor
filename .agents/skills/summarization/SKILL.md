---
name: summarization
description: Use for concise Election Stream Monitor repository, subsystem, or completed-change summaries. Excludes PR shaping, incident diagnosis, planning, and test strategy.
---

# Summarization

Own concise repository and completed-change summaries. Read only the code,
tests, or owning docs needed to distinguish confirmed behavior from inference.

## Default approach

For a narrow implementation question, start with the target code and nearby
tests. For a runtime or contract summary, confirm it against the owning docs:
`docs/README.md`, `docs/architecture.md`, `docs/contracts.md`, and
`docs/session-model.md` as needed.

State the current result, why it matters, and whether the change is structural,
behavioral, mixed, or plausibly behavior-preserving. Name the frontend/backend
owner when a boundary crosses both sides. Do not turn a file inventory into an
architecture claim.

## Output shape

Use the smallest useful form.

Core summary:

1. `What it is`
2. `What changed` or `What is happening`
3. `Why it matters`
4. `Behavior impact` or `Contract/lifecycle/operator impact`
5. `Next safest action`

Add `Validation` only when it supports a behavior-preserving claim. Add `Best concise framing` only for a PR-ready or commit-ready summary.

## Skill boundaries

- Use `incident-analysis` for event reconstruction or an evidence-backed likely cause.
- Use `branch-pr-readiness` first for branch drift, commit grouping, merge readiness, or PR shape.
- Use `task-planning-evaluation` for priority or sequencing.
- Use `test-strategy-review` for missing-confidence analysis or lane selection.
- Use `docs-alignment` first for documentation drift.

## Avoid

- file-by-file changelogs
- speculative future design
- claiming behavior was preserved without evidence
- turning a concise summary into PR, incident, planning, or test-strategy work
