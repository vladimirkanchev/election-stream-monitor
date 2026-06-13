---
name: summarization
description: Use when the user wants a concise, repo-aware summary of code, behavior, a subsystem, an incident, or recent work in Election Stream Monitor. Best for fast understanding of what changed, what matters, whether behavior changed, and what to do next.
---

# Summarization

Use this skill for short, high-signal summaries grounded in the current repo:
local-first runtime, session-driven behavior, explicit contracts, and active
MCP/server evolution without overcommitting to future architecture.

## Default approach

Read only what is needed.

When the user asks about runtime behavior or boundary meaning, prefer this order:

1. `docs/README.md`
2. `docs/architecture.md`
3. `docs/contracts.md`
4. `docs/session-model.md`
5. the target code files

When the user asks about a narrow implementation detail, start with the target
code and nearby tests first. Use docs only to confirm boundary or contract
meaning.

Keep the summary grounded in current repo vocabulary:

- `session`
- `snapshot`
- `bridge`
- `api_stream`
- `detector`
- `alert rule`
- `worker`

It also owns the change-summary use case: PR-ready or commit-ready summaries of
work that already happened, including whether the change looks
behavior-preserving.

## Output shape

Use this structure unless the user asks for something narrower.

Core summary:

1. `What it is`
2. `What changed` or `What is happening`
3. `Why it matters`
4. `Behavior impact` or `Contract/lifecycle/operator impact`
5. `Next safest action`

Use these only when they add real value:

6. `Validation` when the confidence of a behavior-preserving claim matters
7. `Best concise framing` when the summary needs a PR-ready or commit-ready close

Keep it short. Prefer direct statements over long explanation.

## Project-specific rules

- Distinguish current code truth from future ideas.
- Mention docs only when they clarify the runtime boundary or contract.
- If behavior crosses frontend/backend, say which side owns what.
- If confidence is limited, say what is confirmed and what is inferred.
- Do not inflate implementation details into architecture if the repo still treats them as local seams.
- For completed work, say plainly whether the change appears structural, behavioral, or mixed.
- Preserve the stronger behavior-impact framing from the earlier change-summary workflow.
- Prefer a short high-signal summary over changelog-style file inventories.
- Prefer one clear summary over a stack of partial summaries.

## Good fit examples

- summarize a PR or local changes
- summarize what changed, why it matters, and whether the behavior moved
- a detector-lab refactor needs a short explanation of the new family split and whether behavior changed
- a harness branch needs a PR-ready summary that includes docs and tests but avoids a file-by-file dump
- summarize the current session lifecycle
- summarize an incident after reading logs and code
- summarize the current MCP/server direction in repo terms

## Skill boundaries

- Use `incident-timeline` when the main need is ordered reconstruction.
- Use `root-cause-suggestion` when the user wants the most likely explanation.
- Use `test-strategy-review` when the user mainly wants missing-confidence analysis.
- Use `branch-pr-readiness` first when the main question is merge readiness, branch drift, or PR shape.
- Use `docs-alignment` first when the main question is docs drift rather than summary.

## Avoid

- dumping file-by-file changelogs
- repeating obvious code
- giving speculative future design unless the user asks for it
- claiming behavior was preserved without enough evidence
