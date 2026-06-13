---
name: task-planning-evaluation
description: Use when the user wants repo-aware help prioritizing work in Election Stream Monitor. Best for rating tasks by importance, urgency, scope, and complexity, then suggesting phased plans, next steps, and practical sequencing.
---

# Task Planning Evaluation

Use this skill when the main need is: "what should we do next, how big is it, and what sequence makes sense for this repo?"

This repo commonly needs planning help across:

- detector and alert-rule roadmap choices
- workflow, harness, and AI-skill improvements
- CI, testing, and docs hardening
- runtime versus `detector_lab` prioritization
- interview-friendly project framing and next-step planning

## Default approach

Rate the task before recommending the plan.

Work from:

1. current project stage
2. task goal and expected value
3. risks or blockers
4. impact on runtime, workflow, or maintainability
5. best next phase or sequence

Scale the planning depth to the task:

- simple, obvious, low-risk tasks
  - do the work directly
- medium tasks
  - use the short checklist
- broad or shared-boundary tasks
  - give the fuller staged plan

Use these rating categories:

- `importance`
  - how much the task helps the project succeed
- `urgency`
  - how soon the task should be done
- `scope`
  - how broad the likely change surface is
- `complexity`
  - how hard the task is to implement or validate well

## Short checklist

Use this for medium tasks when a full plan would be more structure than value:

1. What boundary changes?
2. What behavior must stay the same?
3. What test needs update or addition?
4. What smallest validation command should run?
5. Any docs or harness update needed?
6. Still inside branch scope?

For the human-readable owner of this checklist and the matching branch
execution pattern, use [docs/branch-purpose-template.md](../../../docs/branch-purpose-template.md).

## Output shape

Use this order:

1. `Task`
2. `Importance`
3. `Urgency`
4. `Scope`
5. `Complexity`
6. `Why it matters now`
7. `Recommended phase`
8. `Best next step`

## Project-specific rules

- Rate tasks against the current local-first advanced-prototype stage, not an imagined later platform.
- Distinguish core runtime/product work from workflow, harness, CI, docs, and detector-lab support work.
- Prefer phased plans that keep branch scope readable and validation practical.
- Do not over-structure simple tasks. If the change is small and obvious, say so.
- If a task is valuable but not urgent, say so instead of inflating it.
- When relevant, call out whether the task is especially good for interview storytelling, operator value, or maintainability.
- Favor concrete next steps over abstract roadmap language.

## Skill boundaries

- Use this when the user wants prioritization, sequencing, or roadmap thinking.
- If the main question is branch shape or safe cleanup, use `branch-pr-readiness` first.
- If the main question is missing confidence after a change, use `test-strategy-review` first.
- If the main question is docs drift rather than task priority, use `docs-alignment` first.

## Good fit examples

- deciding whether to work on detectors, CI, harness, or docs next
- rating optional harness additions for the current branch
- building a 2-week versus 2-month project roadmap
- framing project work into interview-friendly categories

## Avoid

- rating everything as urgent
- proposing large future-platform work as if it were the next obvious step
- giving roadmap advice without considering the current repo stage
- replacing concrete next steps with generic product-management language
