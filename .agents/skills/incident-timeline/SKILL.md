---
name: incident-timeline
description: Use when the user needs an ordered reconstruction of a bug, failure, CI problem, runtime incident, or GUI/backend mismatch in Election Stream Monitor. Best for turning logs, snapshots, and code paths into a clear timeline of facts and likely transitions.
---

# Incident Timeline

Use this skill when the main need is: "what happened, in what order, and where did it go wrong?"

This repo often needs timeline reconstruction across:

- frontend polling and playback
- FastAPI routes
- detached session worker startup
- persisted session files
- `api_stream` loader behavior
- CI and protected-branch workflow state

## Default approach

Collect facts first, then infer transitions.

Preferred evidence sources:

1. logs and command output
2. `session.json`, `progress.json`, `alerts.jsonl`, `results.jsonl`, `worker.log`
3. route/service/runner code
4. frontend hook and bridge behavior
5. CI/workflow state if the incident is on GitHub

## Output shape

Use this order:

1. `Observed facts`
2. `Reconstructed sequence`
3. `Trigger`
4. `First visible symptom`
5. `Backend events`
6. `Frontend events`
7. `Persistence/session-file events`
8. `Terminal state`
9. `Unknowns still left`

## Project-specific rules

- Separate observed facts from inference.
- Call out the ownership boundary when the event crosses frontend, bridge, API, runner, or loader.
- When relevant, distinguish:
  - start request accepted
  - worker started
  - first session snapshot persisted
  - frontend polling/read behavior
- If a 404/validation error is transient by design, say so explicitly.

## Skill boundaries

- Use this before `root-cause-suggestion` when event order is still unclear.
- Hand off to `root-cause-suggestion` once the sequence is stable enough to support a disciplined hypothesis.

## Good fit examples

- session starts but UI falls back to idle
- `api_stream` reconnect or idle-budget incidents
- branch protection / CI merge incidents
- "button disabled / cannot stop monitoring" style operator reports

## Avoid

- jumping straight to root cause before the sequence is clear
- mixing "likely" statements into the factual timeline
