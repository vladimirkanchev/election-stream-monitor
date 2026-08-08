---
name: persistence-backend-review
description: Use when the user wants a repo-aware review of session or alert persistence behavior in Election Stream Monitor. Best for checking file-backed versus PostgreSQL-backed defaults, runtime store selection, alert read-model parity, parity tests, docs alignment, and migration drift without turning the task into broad database architecture work.
---

# Persistence Backend Review

Use this skill when the main need is: "does this session or alert persistence
change keep file-backed and PostgreSQL-backed behavior honest?"

This repo commonly needs persistence review across:

- session-store and alert-store contracts
- default file-backed behavior versus opt-in PostgreSQL behavior
- runtime store selection in parent processes and detached workers
- parity coverage, runtime smoke coverage, and docs alignment
- migration branches that may accidentally expand beyond persistence ownership

## Default approach

Review the persistence contract before proposing broader architecture changes.

Work from:

1. changed session-store, alert-store, runtime-config, service, or route module
2. the default backend and the explicit opt-in backend
3. behavior that must stay shared across backends
4. the smallest parity, runtime, or docs gap
5. whether the branch is drifting beyond persistence work

For sessions, check metadata, latest progress, ordered results, cancel intent,
snapshot shape, missing-session reads, and detached-worker backend agreement.

For alerts, use **Alert-parity mode**:

- raw alert reads, summaries, and incident grouping
- store bootstrap and adapter behavior
- FastAPI/MCP read-model consistency

Keep alert-store parity separate from route auth, rate-limit, or share-mode
policy: those controls can change without changing the shared alert contract.

## Output shape

Use this order:

1. `Persistence surface`
2. `Default versus opt-in behavior`
3. `Shared contract risk`
4. `Current confidence`
5. `Best next check`

Keep the review practical and migration-focused.

## Project-specific rules

- Treat file-backed storage as the default unless the code and docs explicitly
  change that rollout contract.
- Treat PostgreSQL as a supported opt-in backend when the relevant runtime
  config, store adapter, docs, and tests all support that claim.
- Prefer contract and parity checks over internal schema commentary unless the
  schema change affects observable behavior.
- Keep session persistence and alert persistence distinct, but call out when a
  branch needs both to tell one coherent release story.
- Check that runtime selection is consistent between FastAPI/service code and
  detached workers before trusting read-after-start behavior.
- Name the smallest useful validation lane when possible, such as
  `just test-session-store`, `just test-session-runtime`, alert-store parity
  tests, or optional live PostgreSQL smoke checks.

## Skill boundaries

- Use this when the main question is persistence behavior, backend selection,
  parity confidence, or migration drift.
- Use Alert-parity mode when the question is limited to shared alert reads,
  filters, summaries, incidents, or adapter behavior across backends.
- Use `ci-failure-triage` first for a failing CI lane.
- Use `security-surface-review` first for route exposure, auth, rate limits,
  MCP access, or share-mode risk.
- Use `test-strategy-review` first to choose tests to add or trim.
- Use `branch-pr-readiness` first for branch cleanup or merge shape.

## Good fit examples

- a session-store branch may have changed file versus PostgreSQL snapshot semantics
- a detached worker may no longer inherit the same store backend as the parent
- an alert-store migration needs a small parity check before broader route work
- an alerts-router auth change touched store parity or only access policy
- a session-alert store refactor changed file/PostgreSQL grouped-incident behavior
- docs now imply PostgreSQL stores artifacts that still remain file-backed

## Avoid

- turning every persistence review into full database design
- assuming PostgreSQL is the default just because an adapter exists
- mixing security exposure review into store parity review
- recommending live database CI before focused contract and runtime confidence
  justify the cost
