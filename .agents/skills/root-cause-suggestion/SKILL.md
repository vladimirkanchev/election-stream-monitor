---
name: root-cause-suggestion
description: Use when the user wants the most likely explanation for a bug, failure, or confusing runtime state in Election Stream Monitor, along with concrete evidence and the cheapest validation step. Best for narrowing incidents without spraying many weak guesses.
---

# Root Cause Suggestion

Use this skill after enough evidence has been gathered to make a disciplined hypothesis.

This is not a brainstorming skill. Prefer one strong explanation, with a second only when it is genuinely competitive.

## Default approach

Work from:

1. observed symptom
2. closest owning boundary
3. evidence from logs/code/session artifacts
4. cheapest validation step

If event order is still unclear, use `incident-timeline` first.

In this repo, common owning boundaries are:

- frontend UI state
- bridge normalization
- FastAPI route mapping
- session service / worker spawn
- session runner lifecycle
- `api_stream` loader/runtime policy
- persistence/session files
- CI/ruleset/branch protection

## Output shape

Use this structure:

1. `Most likely root cause`
2. `Confidence`
3. `Evidence for it`
4. `Evidence against it`
5. `Cheapest next validation`

If a second hypothesis is needed, keep it shorter than the first.

## Project-specific rules

- Prefer causes tied to an owning module or boundary, not vague "system issues".
- Say explicitly when the symptom is likely transient by design rather than a true failure.
- If the probable cause is GitHub policy/state rather than repo code, say that plainly.
- If the real issue is stale state, cache, or merge evaluation, distinguish that from failing tests.
- Do not call something a root cause if it is only a visible symptom.

## Good fit examples

- session start succeeded but first read 404s
- playback resolve fails while session creation succeeds
- UI controls stay frozen after a state transition
- PR is green but merge remains blocked

## Skill boundaries

- Use this after enough evidence exists to support a real hypothesis.
- If the user mainly wants ordered reconstruction, use `incident-timeline` instead.

## Avoid

- listing many low-confidence possibilities
- proposing fixes before naming the likely cause
- collapsing symptom, workaround, and cause into one statement
