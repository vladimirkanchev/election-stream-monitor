---
name: fixture-environment-safety
description: Use for Election Stream Monitor test fixture, host-tool, socket, and local-asset portability. Excludes detector confidence and real-media assertion review.
---

# Fixture Environment Safety

Use this skill when the main need is: "is this test or fixture setup portable enough for the repo, or is it leaking local assumptions?"

This repo commonly needs fixture and environment safety checks across:

- checked-in media fixtures versus local-only research assets
- socket-backed HLS or local HTTP tests
- detector-lab real-media confidence lanes
- missing local tools such as `just`, `ffmpeg`, or repo-local virtualenv expectations
- tests that assume repo paths, writable caches, or machine-specific setup

## Default approach

Check portability before assuming the failure is a code bug.

Work from:

1. fixture path or described environment dependency
2. whether the asset or capability is committed, optional, or local-only
3. whether the test is meant for fast CI, slow confidence, or local/manual use
4. the cheapest safe fix
5. whether the issue should become a skip, an injected temp path, or a docs/policy clarification

## Output shape

Use this order:

1. `Risk summary`
2. `Environment dependency`
3. `CI safety assessment`
4. `Best fix shape`
5. `Cheapest validation`

## Project-specific rules

- Distinguish checked-in fixtures from local-only research assets plainly.
- If a test depends on sockets, local servers, or restricted host capabilities, say whether it belongs in a slow or environment-sensitive lane.
- Prefer temp-path injection, monkeypatching, or explicit skips over hidden repo-path writes.
- Treat missing `.venv`, missing `just`, and missing `ffmpeg` as environment issues first, not product regressions.
- For detector-lab work, keep synthetic, real-media, and local-research inputs clearly separated.
- If an asset should stay local-only, recommend `.gitignore` or doc guidance instead of forcing it into CI.

## Skill boundaries

- Use this when the main question is fixture portability or environment coupling.
- If the main question is which local command to run, use `test-strategy-review`.
- If the main problem is a red CI job and the classification is still unclear, use `ci-failure-triage` first.
- If the question becomes missing confidence after a safe fixture split, use `test-strategy-review` next.

## Good fit examples

- a detector-lab test unexpectedly depends on local baseline clips that are not committed
- an HTTP/HLS test fails only because local sockets are unavailable in the environment
- a new command assumes `.venv/bin/pytest` exists without setup guidance
- a test writes cache files into repo paths instead of using temporary locations

## Avoid

- calling every environment-coupled test “bad” when it may simply belong in a slower or optional lane
- recommending committed fixtures for local-only research assets without a real project need
- confusing missing tools with detector or alert regressions
- hiding repo-path or host-capability assumptions behind vague flaky-test language
