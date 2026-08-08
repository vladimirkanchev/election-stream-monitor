---
name: task-planning-evaluation
description: Use when the user wants repo-aware prioritization, sequencing, task sizing, or proportional closure for Election Stream Monitor work. Best for rating next work by importance, urgency, scope, and complexity without deciding branch/PR shape or specific tests.
---

# Task Planning Evaluation

Own prioritization, sequencing, and proportional closure. Rate work against the
current local-first pilot stage, not an imagined production platform.

## Default approach

Start from current project stage, expected outcome, risk, affected seam, and
the cheapest credible closure. Separate product/runtime work from supporting
CI, harness, documentation, and detector-lab work.

Use proportional planning:

- small and obvious: perform it directly with one focused check;
- medium: use the checklist in
  [docs/branch-purpose-template.md](../../../docs/branch-purpose-template.md);
- broad or shared-boundary: stage the work and name validation lanes.

Do not inflate a valuable but non-urgent task. Prefer a clear next phase over a
long roadmap. Before recommending new tests, ask whether an existing focused
test or docs check already closes the actual risk.

## Output shape

1. `Task`
2. `Importance`
3. `Urgency`
4. `Scope`
5. `Complexity`
6. `Why it matters now`
7. `Recommended phase`
8. `Best next step`

Use 1–10 ratings and say what assumption would change the recommendation.

## Skill boundaries

- Use `branch-pr-readiness` first for branch shape, commit grouping, or safe cleanup.
- Use `test-strategy-review` first for missing confidence or a validation choice.
- Use `docs-alignment` first for documentation drift.
- Use `summarization` first when current behavior or completed work is unclear.

## Avoid

- rating every task urgent
- proposing cloud-scale work as the immediate next step
- replacing a practical phase with generic roadmap language
- absorbing PR structure, detailed test design, or implementation execution
