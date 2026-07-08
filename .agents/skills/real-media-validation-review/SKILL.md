---
name: real-media-validation-review
description: Use when the user wants a repo-aware review of real-media, stream, or file-validation work in Election Stream Monitor. Best for checking checked-in versus local-only assets, flaky stream behavior, confidence-lane choice, and whether real-media coverage still matches the branch purpose without expanding into a broad test rewrite.
---

# Real Media Validation Review

Use this skill when the main need is: "does this real-media or stream/file
test work stay honest about assets, flakiness, and validation cost?"

This repo commonly needs real-media validation review across:

- checked-in fixtures versus local-only media assets
- remote HLS or stream behavior that can be flaky or timing-sensitive
- stream/file branches that need one honest confidence lane
- real-media tests that may belong in slow, weekly, or manual validation paths
- docs or branch notes that may overclaim what the tests really prove

## Default approach

Start from the current media branch or test area, then check whether the
confidence story matches the actual assets and runtime assumptions.

Work from:

1. changed media-handling code, test file, or fixture set
2. whether the branch uses checked-in fixtures, local-only assets, or remote sources
3. whether failures look like code regressions, fixture/environment drift, or known flakiness
4. the cheapest honest validation lane
5. whether the branch story still matches the real-media confidence it claims

Use this checklist:

1. fixture ownership: are the required assets checked in, optional, or local-only?
2. stream stability: does the branch depend on flaky remote timing, sockets, or live sources?
3. validation lane: should this stay in a focused local lane, slow lane, weekly lane, or manual-only path?
4. branch scope: is the branch still about real-media confidence, or has it widened into unrelated runtime or CI work?
5. docs honesty: do docs and PR notes describe exactly what the media tests prove and what they do not?

## Output shape

Use this order:

1. `Validation target`
2. `Fixture reality`
3. `Flaky or environment-sensitive risk`
4. `Best confidence lane`
5. `Best next cleanup`

Keep the review narrow and confidence-focused.

## Project-specific rules

- Distinguish checked-in fixtures from local-only research assets plainly.
- Treat flaky remote streams and deterministic checked-in media as different confidence surfaces.
- Prefer one honest lane such as `just test-real-media`, a focused pytest slice, a weekly path, or a manual-only note over stacking redundant validation.
- If a stream case depends on sockets, host networking, or unstable upstream media, say that clearly and route it out of routine fast CI.
- Keep branch scope tight: real-media confidence work should not silently become a general CI or runtime refactor.
- If docs or PR text overstate what the branch proves, call that out directly.

## Skill boundaries

- Use this when the main question is real-media coverage quality, media-fixture honesty, flaky stream risk, or validation-lane choice for media-heavy branches.
- If the main issue is fixture portability or missing local tools, use `fixture-environment-safety` first.
- If the main question is the cheapest automated lane in general, use `test-strategy-review` first.
- If the user needs a human-run smoke path instead of automated confidence, use `manual-validation-planner` first.
- If the branch itself is messy and needs split/merge advice, use `branch-pr-readiness` first.

## Good fit examples

- a stream/file branch may rely on local-only clips that should not be treated like checked-in fixtures
- a remote HLS confidence test may now be too flaky for routine PR validation
- a real-media branch may be claiming CI confidence that really belongs in a weekly or manual lane
- a media-validation branch may now mix fixture work with unrelated runtime cleanup

## Avoid

- treating every real-media test as inherently high value
- promoting flaky remote-stream confidence into routine CI without saying why
- confusing local-only fixture drift with product runtime regressions
- turning the review into a request to redesign the whole test matrix
