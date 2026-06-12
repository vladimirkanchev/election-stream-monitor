---
name: alert-backend-parity-review
description: Use when the user wants a repo-aware review of alert-backend parity in Election Stream Monitor. Best for checking file-backed versus PostgreSQL-backed alert behavior, auth/session-alert seams, and shared read-model consistency without expanding into a broad database review.
---

# Alert Backend Parity Review

Use this skill when the main need is:

- "does file-backed versus PostgreSQL-backed alert behavior still match closely enough?"
- "did this alert-route, store, or session-alert change drift across the shared backend seam?"
- "what parity risk exists when auth, store selection, or alert-read paths change?"

Typical seams here are file-backed versus PostgreSQL-backed store behavior,
runtime-selected alert stores, session-alert read/filter/summary/incident
paths, shared FastAPI or MCP adapters, and auth or `share`-mode changes around
those paths.

## Default approach

Start from the changed alert seam, then check parity before redesign.

Work from:

1. changed alert-store, service, or adapter module
2. shared behavior that should stay consistent across backends
3. whether the change is store-level, route-level, or policy-level
4. what parity confidence already exists
5. the smallest meaningful follow-up

Use `docs/README.md` and `docs/testing-and-validation.md` when the current
alert-backend test ownership or confidence lanes need confirmation.

## Output shape

Use this order:

1. `Parity surface`
2. `What should stay the same`
3. `Main parity risk`
4. `Current confidence`
5. `Best next check`

Keep the review practical and seam-specific.

## Project-specific rules

- Treat file-backed alerts as the default runtime and PostgreSQL as an opt-in backend unless the code explicitly changes that contract.
- Distinguish alert-store parity from route auth or rate-limit policy; those are related but not the same seam.
- Prefer narrow comments about shared read-model behavior, store selection, bootstrap behavior, and adapter consistency over broad database architecture advice.
- Call out when the change affects:
  - raw alerts
  - summaries
  - grouped incidents
  - FastAPI/MCP parity
  - bootstrap or fallback behavior
- If a change is only in `share`-mode protection, say plainly that the alert-store contract may still be unchanged.
- Name the smallest useful parity lane when possible, especially `tests/test_session_alert_store_parity.py`, the focused alert-query slices, or the weekly/manual live Postgres confidence runners.

## Skill boundaries

- Use this when the main need is alert-backend parity or shared alert-service consistency.
- If the main blocker is a failing CI lane, use `ci-failure-triage` first.
- If the question is primarily route security or `share`-mode exposure, use `security-surface-review` first.
- If the user mainly needs the smallest test lane to run, use `test-strategy-review` first.
- If the issue is broader branch/merge shape rather than alert semantics, use `branch-pr-readiness` first.

## Good fit examples

- a session-alert store refactor may have changed file versus PostgreSQL grouped-incident behavior
- an alerts-router auth change needs review for whether it touched store parity or only access policy
- runtime store selection changed and the shared read-model path needs a parity check
- an MCP or FastAPI alert adapter update needs review for shared alert-backend consistency

## Avoid

- turning the review into generic PostgreSQL schema design advice
- confusing auth/rate-limit policy with alert-store parity
- recommending broad database redesign when the real issue is one shared alert-read seam
- ignoring the existing parity and live-confidence lanes already present in the repo
