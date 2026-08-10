---
name: architecture-diagram-review
description: Use when the user wants a concise repo-aware review of an Election Stream Monitor architecture diagram. Best for checking runtime/control versus data-flow arrows, subsystem and trust boundaries, visual clarity, and whether labels and layout still match the current local-first project stage.
---

# Architecture Diagram Review

Use this skill when the main need is:

- "does this diagram still match the current runtime and storage shape?"
- "are these arrows showing execution flow, data flow, or just a summary relationship?"
- "do these labels or boundaries make the project look more mature or distributed than it is?"

Typical seams are Electron versus FastAPI ownership, detached-session-worker execution, session-files versus alert-backend persistence, MCP versus FastAPI trust boundaries, and summary README diagrams that may over-compress the real runtime seams.

## Default approach

Review one diagram version at a time.

Work in this order:

1. current runtime code and owning docs
2. the exact diagram revision
3. arrow meaning and visual clarity
4. subsystem and trust boundaries
5. current-project-stage honesty
6. smallest useful fixes

Use these flow classes explicitly:

- `runtime/control flow`
  - start, handoff, spawn, execution, request/response ownership
- `data flow`
  - persisted writes, reads, derived snapshots, shared backend paths
- `concept/summary relationship`
  - grouped direction, trust-boundary notes, or summary routing that is not a literal call edge

Check `Arrow-origin check` and `Arrow-end check` on purpose:

- arrows should usually start from real owned components, not decorative group borders
- arrows should end on the component or store that actually receives the call, read, write, or relationship

## Output shape

Use this order:

1. `Diagram rating`
2. `Visual quality`
3. `What matches well`
4. `Flow arrow review`
5. `Boundary review`
6. `Arrow-origin check`
7. `Arrow-end check`
8. `Stage honesty`
9. `Biggest mismatch`
10. `Smallest useful fixes`

Keep the answer concise unless the user asks for a fuller walkthrough.

## Project-specific rules

- Distinguish `runtime/control flow`, `data flow`, and `concept/summary relationship` instead of treating every line as the same arrow type.
- Review whether labels or box names overstate maturity, distribution, deployment, or security hardening beyond the current code.
- Keep Electron, FastAPI, detached session worker, persistence, and MCP boundaries explicit when the diagram is about the current desktop runtime.
- Treat MCP versus FastAPI as a meaningful trust-boundary check in the current project stage.
- Do not let a diagram imply that PostgreSQL already owns all persistence when session state is still file-backed.
- Do not force call-graph precision onto a summary-level README diagram, but do call out places where summary arrows are being mistaken for execution flow.
- If visual styling already separates runtime arrows from data arrows, say so and rate the clarity instead of asking for more diagram chrome.
- Rate diagrams against the current local-first advanced-prototype stage, not a future distributed platform.

## Skill boundaries

- Use this when the main question is whether a diagram is technically honest, visually clear, and aligned with the current project architecture.
- If the main question is root README wording, section fit, or whether a diagram explanation is too heavy for the root README, use `readme-alignment-review` first.
- If the main question is whether an architecture doc or diagram is actually outdated and which doc owns the fix, use `docs-drift-check` first.
- If the user already knows the diagram needs updates and mainly wants the text or owning docs edited, use `docs-alignment` next.
- If the main question is MCP/FastAPI security scope rather than visual correctness, use `security-surface-review` first.

## Good fit examples

- a README architecture diagram may now blur Electron, FastAPI, and detached-worker ownership
- a worker arrow may look like a data relationship instead of execution flow
- a new diagram version needs a before-versus-after rating on flow arrows and current-stage honesty
- MCP and FastAPI both appear in a diagram and it is unclear whether the trust boundary is still shown honestly
- a label may now make the local-first runtime look like a broader deployed platform
- a diagram uses multiple arrow styles and we need to check whether readers can tell control flow from data flow

## Avoid

- turning one diagram review into a full architecture redesign by default
- treating every layout preference as a real architecture mismatch
- collapsing README prose review into diagram review
- recommending extra subsystem boxes or styling when the current diagram is already honest and readable
- implying more runtime maturity, deployment scope, or security hardening than the code supports
