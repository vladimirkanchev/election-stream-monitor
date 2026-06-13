---
name: frontend-bridge-review
description: Use when the user wants a repo-aware review of renderer, Electron bridge, session-polling, playback, or UI-runtime changes in Election Stream Monitor. Best for checking ownership, readability, drift, and missing focused confidence across the frontend/runtime seam.
---

# Frontend Bridge Review

Use this skill when the main need is:

- "does this frontend or bridge change still respect the current ownership split?"
- "is this renderer, preload, or Electron runtime change readable and correctly bounded?"
- "what is risky here around polling, playback, session status, or bridge normalization?"

Typical seams here are React renderer state, preload bridge contracts, session
polling, playback source resolution, and UI runtime behavior that crosses
frontend, bridge, and backend snapshots.

## Default approach

Start from the changed seam, then review ownership before style.

Work from:

1. changed frontend, Electron, or bridge module
2. nearest owning layer
3. whether the behavior belongs in renderer, preload, Electron main, or backend
4. visible operator impact
5. focused confidence already present or still missing

Use `docs/frontend-architecture.md` when the ownership split or bridge
boundary needs confirmation.

## Output shape

Use this order:

1. `Findings`
2. `Ownership assessment`
3. `UI/runtime impact`
4. `Missing confidence`
5. `Suggested follow-up`

Keep the review risk-first and seam-aware.

## Project-specific rules

- Respect the current split:
  - React owns UI composition and local state transitions
  - preload exposes one minimal bridge surface
  - Electron main owns bootstrap, protocol/runtime wiring, and proxy behavior
  - Python remains the source of truth for sessions and playback resolution
- Call out when polling, playback, or alert rendering logic drifts into the wrong layer.
- Prefer narrow comments about readability, coupling, and boundary drift over broad frontend redesign advice.
- Distinguish bridge normalization issues from backend contract issues.
- For session status or polling changes, mention the first visible UI state or operator-facing wording that could regress.
- For playback changes, mention whether the seam is source resolution, renderer-safe URL adaptation, or HLS/local-media handling.
- Name the best focused follow-up lane when useful, especially `just test-frontend`, bridge-focused frontend tests, or `manual-validation-planner`.

## Skill boundaries

- Use this when the main need is a frontend/runtime seam review, not a generic UI opinion.
- If the user mainly wants the smallest automated lane to run, use `test-strategy-review` first.
- If the local behavior already failed and the sequence is unclear, use `incident-timeline` first.
- If the branch needs a small human smoke path before merge, use `manual-validation-planner` next.
- If the main blocker is a failing CI lane, use `ci-failure-triage` first.
- If the issue is really backend rule or detector logic, use `detector-rule-review` first.

## Good fit examples

- a session-polling hook change may have blurred renderer versus bridge responsibilities
- a preload contract change needs review for normalization drift and test gaps
- a playback-source refactor may have pushed protocol behavior into the wrong frontend layer
- a session-status UI tweak needs review for operator-visible wording and confidence lanes

## Avoid

- turning the review into generic frontend style advice
- treating the renderer, preload, and Electron main process as one layer
- ignoring operator-visible regressions in polling, playback, or alerts
- recommending a full frontend suite when one focused bridge or checkpoint lane is enough
