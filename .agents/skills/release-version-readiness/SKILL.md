---
name: release-version-readiness
description: Use when the user wants repo-aware help deciding whether an Election Stream Monitor branch or merge should change the project version, and if so whether the change looks like a patch, minor, or larger milestone step. Best for judging version bump semantics against actual code, tests, docs, and rollout state without turning the question into broad release management.
---

# Release Version Readiness

Use this skill when the main need is:

- "does this branch justify `0.5.2`, `0.5.3`, `0.6.0`, or no version bump yet?"
- "is this change still patch-level, or did it become a new minor milestone?"
- "what needs to be true before we describe this work as the next version?"

Typical seams here are persistence rollouts, alert/backend milestones, CI and
harness hardening, real-media confidence expansions, and version questions that
sit between branch readiness and project storytelling.

## Default approach

Judge version semantics from the shipped meaning of the branch, not only from
how much code changed.

Work from:

1. current base version named in code or docs
2. the branch's main user-visible or maintainer-visible outcome
3. whether the change is patch, minor, or still pre-versioning cleanup
4. rollout truth: default path, opt-in path, and what is still incomplete
5. whether tests and docs support the claim the version label would make

Ask these before recommending a bump:

1. did the default runtime behavior change?
2. did a supported capability become newly real, not just experimental or opt-in?
3. would release notes describe one coherent milestone rather than scattered cleanup?
4. do code, tests, and owning docs all support that milestone claim?

## Output shape

Use this order:

1. `Current base version`
2. `Change class`
3. `Recommended version`
4. `Why not smaller`
5. `Why not larger`
6. `What must be true first`

Keep the answer concrete and branch-scoped.

## Project-specific rules

- Prefer patch-level framing for focused fixes, docs cleanup, harness hardening,
  and confidence improvements that do not materially change the supported
  runtime surface.
- Prefer a minor milestone only when a new supported capability or materially
  stronger backend/runtime path is truly ready to be described in docs and
  tests.
- Do not treat an opt-in adapter, partial migration, or hidden experimental
  path as a finished milestone by itself.
- When persistence or alert-storage work is still split between file-backed
  defaults and PostgreSQL opt-in behavior, say that plainly before recommending
  a larger version step.
- Use version language that matches current repo maturity: local-first
  advanced prototype, not fully productized release trains.

## Skill boundaries

- Use this when the main question is version meaning, milestone readiness, or whether a branch justifies a named project version step.
- If the main question is merge readiness or commit/PR grouping, use `branch-pr-readiness` first.
- If the user mainly wants a short PR or release summary, use `summarization` first.
- If the question is roadmap priority rather than version semantics, use `task-planning-evaluation` first.
- If dependency metadata changed and it is unclear whether that belongs in the version story, use `dependency-change-review` first.

## Good fit examples

- a PostgreSQL session-store branch may look big, but the default runtime is still file-backed
- real-media confidence improvements may justify `0.5.3` but not `0.6.0`
- a branch may merge cleanly while still not earning the next named milestone
- a new alert-storage path may need more docs and tests before it should count as a version step

## Avoid

- treating every large diff as a larger version bump
- recommending a milestone version before docs and tests support the claim
- confusing merge readiness with release readiness
- turning a version question into full roadmap or changelog planning
