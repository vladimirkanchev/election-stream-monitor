---
name: summarization
description: Use when the user wants a concise, repo-aware summary of code, behavior, a subsystem, an incident, or recent work in Election Stream Monitor. Best for fast understanding of what changed, what matters, and what to do next.
---

# Summarization

Use this skill for short, high-signal summaries that match the current repo stage:

- local-first runtime
- session-driven behavior
- explicit contracts
- active MCP/server evolution without overcommitting to future architecture

## Default approach

Read only what is needed.

When the user asks about runtime behavior or boundary meaning, prefer this order:

1. `docs/README.md`
2. `docs/architecture.md`
3. `docs/contracts.md`
4. `docs/session-model.md`
5. the target code files

When the user asks about a narrow implementation detail, start with the target
code and nearby tests first, then use docs only to confirm boundary or
contract meaning.

Keep the summary grounded in current repo vocabulary:

- `session`
- `snapshot`
- `bridge`
- `api_stream`
- `detector`
- `alert rule`
- `worker`

## Output shape

Use this structure unless the user asks for something narrower:

1. `What it is`
2. `What changed` or `What is happening`
3. `Why it matters`
4. `Contract/lifecycle/operator impact`
5. `Next safest action`

Keep it short. Prefer direct statements over long explanation.

## Project-specific rules

- Distinguish current code truth from future ideas.
- Mention docs only when they clarify the runtime boundary or contract.
- If behavior crosses frontend/backend, say which side owns what.
- If confidence is limited, say what is confirmed and what is inferred.
- Do not inflate implementation details into architecture if the repo still treats them as local seams.

## Good fit examples

- summarize a PR or local changes
- summarize the current session lifecycle
- summarize an incident after reading logs and code
- summarize the current MCP/server direction in repo terms

## Skill boundaries

- Use `incident-timeline` when the main need is ordered reconstruction.
- Use `root-cause-suggestion` when the user wants the most likely explanation.
- Use `test-coverage-gaps` when the user mainly wants missing-confidence analysis.

## Avoid

- dumping file-by-file changelogs
- repeating obvious code
- giving speculative future design unless the user asks for it
