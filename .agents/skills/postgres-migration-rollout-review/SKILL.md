---
name: postgres-migration-rollout-review
description: Use when the user wants a repo-aware review of PostgreSQL migration rollout work in Election Stream Monitor. Best for checking rollout state, schema ownership, backfill expectations, rollback paths, live smoke plans, and failure-mode confidence without collapsing the question into general persistence parity or broad release management.
---

# Postgres Migration Rollout Review

Use this skill when the main need is:

- "is this PostgreSQL migration branch operationally ready, not just adapter-complete?"
- "what still needs to be true before we roll this persistence path forward?"
- "do rollback, backfill, and failure handling look honest enough for this repo stage?"

Typical seams here are session-store or alert-store migrations, opt-in backend
rollouts, schema ownership questions, rollout docs, and confidence that needs
to go beyond parity tests.

## Default approach

Review the rollout contract before treating a migration branch like a finished
storage milestone.

Work from:

1. what the branch migrates: sessions, alerts, or both
2. whether PostgreSQL is opt-in, default, or only partially wired
3. schema ownership and bootstrap expectations
4. backfill, rollback, and live-smoke expectations
5. failure modes that could leave parent, worker, or reader paths disagreeing

Use this compact checklist:

1. rollout state: is PostgreSQL still opt-in, or is the default path changing?
2. schema ownership: who creates, validates, or evolves the tables?
3. backfill: does historical data need migration, or is the new path forward-only?
4. rollback: what happens if the branch must fall back to file-backed behavior?
5. live smoke: what focused real-database confidence exists, and what is still manual or optional?
6. failure modes: what happens on partial writes, missing tables, startup mismatch, or worker/backend disagreement?

## Output shape

Use this order:

1. `Rollout surface`
2. `Current rollout state`
3. `Main rollout risks`
4. `Missing rollout evidence`
5. `Best next rollout check`

Keep the review operational and rollout-scoped.

## Project-specific rules

- Treat file-backed storage as the default until runtime config, docs, and
  tests all clearly say otherwise.
- Keep parity confidence separate from rollout confidence: a backend can match
  the contract and still be incomplete as a migration path.
- Name schema ownership plainly instead of assuming migrations are someone
  else's layer.
- Prefer explicit backfill or forward-only wording over vague "supports
  PostgreSQL" claims.
- Prefer focused optional live PostgreSQL smoke over forcing fragile database
  setup into routine CI before it earns the cost.
- Call out rollback truth directly when a branch could strand data or make the
  file-backed fallback unclear.

## Skill boundaries

- Use this when the main question is PostgreSQL migration rollout readiness,
  rollback shape, backfill honesty, or live rollout confidence.
- If the main question is shared backend behavior or parity, use
  `persistence-backend-review` first.
- If the main question is whether the branch justifies a new version or named
  milestone, use `release-version-readiness` first.
- If the main question is which tests to add or trim, use
  `test-strategy-review` first.
- If the main question is merge/readiness workflow, use `branch-pr-readiness`
  first.

## Good fit examples

- a session migration branch passes parity tests but still has no clear rollback story
- an alert-store rollout needs a plain answer about whether backfill is required
- PostgreSQL table bootstrap works locally, but schema ownership is still fuzzy
- a live smoke check exists, but it is unclear whether it belongs in routine CI or a slower optional lane

## Avoid

- treating adapter parity as proof that rollout is finished
- assuming live database CI is required before the branch shape is stable
- mixing release-version semantics into rollout review unless the user asks
- turning one migration branch into a full database-platform redesign
