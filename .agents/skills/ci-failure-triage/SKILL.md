---
name: ci-failure-triage
description: Use when the user wants fast, repo-aware help understanding a failing CI check in Election Stream Monitor. Best for classifying whether a failure is a code bug, stale test, environment issue, or CI/policy drift, then suggesting the smallest useful local reproduction command.
---

# Ci Failure Triage

Use this skill when the main need is: "what kind of CI failure is this, who owns it, and what is the cheapest way to reproduce it locally?"

Typical seams here are backend test lanes, backend lint/type checks, frontend
checkpoint/lint/typecheck, docs/workflow consistency guards, and gate jobs that
only summarize earlier failures.

## Default approach

Classify the failure before suggesting fixes.

Work from:

1. failing check name
2. shortest error text that changes the diagnosis
3. closest owning boundary
4. failure class
5. smallest useful local reproduction command

Use these failure classes:

- `code bug`
  - runtime behavior, import, typing, lint, or contract regression in project code
- `stale test or expectation`
  - tests or fixtures no longer match the current intended behavior
- `environment issue`
  - missing tool, missing dependency, missing fixture, socket or local-only assumption, or host-policy limitation
- `CI or policy drift`
  - manifest, path-filter, branch-protection, target-registration, or docs-consistency mismatch

## Output shape

Use this order:

1. `Failing checks`
2. `Most likely failure class`
3. `Owning boundary`
4. `Evidence for it`
5. `Evidence against it`
6. `Smallest local reproduction`
7. `Best next fix`

## Project-specific rules

- Prefer one strong classification over a list of weak guesses.
- Name the owning lane or module family plainly: backend tests, detector-lab, frontend checkpoint, HLS loader, docs consistency, or branch policy.
- If the real problem is missing `.venv`, missing `just`, missing fixtures, or blocked local sockets, call it an environment issue instead of a code regression.
- If the failing check is only a gate summarizing earlier failures, point back to the first failing leaf check.
- Favor existing harness lanes such as `just ci-local`, `just test-fast`, `just docs-check`, `just test-hls`, and `just test-detector-lab` when they are the cheapest honest reproduction.
- If the failure is on GitHub policy or stale merge state rather than repo code, say that plainly.

## Skill boundaries

- Use this after at least one failing check name or error snippet is available.
- If the main need is ordered reconstruction across logs and files, use `incident-timeline` first.
- If enough evidence already supports one specific technical cause, hand off to `root-cause-suggestion`.
- If the code change is understood and the remaining question is missing confidence, use `test-strategy-review` next.

## Good fit examples

- `backend-tests` fails after detector or alert-rule changes
- `docs-consistency` fails after CI-target edits
- `feature-gate` is red even though only one leaf check actually matters
- local `just test-real-media` fails because the fixture lane expects a missing environment dependency

## Avoid

- proposing broad fix lists before classifying the failure
- treating every red CI job as a code bug
- suggesting the full project test suite when one focused lane is enough
- hiding GitHub policy or environment problems behind vague “flake” language
