---
name: test-coverage-gaps
description: Use when the user wants to know what confidence is missing after a code change, incident, or architectural shift in Election Stream Monitor. Best for identifying the smallest valuable tests still missing across backend, bridge, session lifecycle, and operator-visible behavior.
---

# Test Coverage Gaps

Use this skill to find missing confidence, not to generate a huge test wishlist.

The repo already values tests, so the job here is to find the next most useful gaps after a change, bug, or design shift.

## Default approach

Check the changed or discussed behavior against these layers:

1. contract shape
2. session lifecycle and persistence
3. recovery/error path
4. integration boundary
5. operator-visible frontend behavior
6. slow/manual-only confidence

Use `docs/testing-and-validation.md` to align with the current validation model.

## Output shape

For each gap, provide:

1. `Gap`
2. `Why it matters`
3. `Best test layer`
4. `Cheapest useful test`

Only include gaps that are worth fixing soon.

## Project-specific gap categories

- `contract gap`
  Missing protection for request/response, bridge normalization, or snapshot shape
- `lifecycle gap`
  Missing coverage for pending/running/cancelling/completed/failed transitions
- `recovery gap`
  Missing coverage for transient read failures, reconnects, retries, or worker lag
- `operator gap`
  Missing coverage for visible UI state, disabled controls, session status, or alert presentation
- `integration boundary gap`
  Missing seam coverage between frontend, bridge, API, service, runner, or loader
- `manual-only gap`
  Behavior currently validated only by ad hoc runtime checks

## Project-specific rules

- Prefer one focused test over broad redundant suites.
- Prefer extending existing nearby test files before proposing a new suite.
- Favor stable seams that already exist in the repo.
- If the behavior is mostly side-effectful, suggest the narrowest reliable integration test.
- If a behavior is intentionally manual-only for now, say that instead of pretending it should already be fully automated.

## Skill boundaries

- Use this after the behavior or incident is already understood well enough to judge missing confidence.
- If the user still does not understand what happened, use `summarization` or `incident-timeline` first.

## Avoid

- asking for every possible test
- proposing deep refactors just to make one test possible
- treating advisory checks as missing required coverage
