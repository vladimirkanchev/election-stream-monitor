---
name: detector-rule-review
description: Use for Election Stream Monitor production detector, alert-rule, and nearby processor boundary review. Excludes broad test selection and real-media lane choice.
---

# Detector Rule Review

Use this skill when the main need is: "is this detector or alert-rule change well shaped for the repo, and what important risks or missing tests remain?"

This repo commonly needs detector/rule review across:

- production detector metric contracts
- production alert-rule entry, suppression, recovery, and re-alert behavior
- processor and runtime-row seams near detector/rule evaluation
- `detector_lab` experiment structure and practical alert policies
- promotion-boundary questions between production runtime and `detector_lab`

## Default approach

Review risks before style nits.

Work from:

1. changed detector, rule, or processor files
2. nearest owning tests
3. runtime versus `detector_lab` boundary
4. coupling or readability risks
5. missing confidence that is still worth adding

## Output shape

Use this order:

1. `Findings`
2. `Boundary assessment`
3. `Missing confidence`
4. `Suggested follow-up`

If there are no real findings, say that explicitly and mention any remaining test or validation gap briefly.

## Project-specific rules

- Prioritize behavior regressions, policy drift, and missing tests over style-only comments.
- Check whether detector logic is staying in detectors and alert creation is staying in the rule layer.
- Call out when runtime logic starts looking detector-lab-shaped, or detector-lab work starts looking production-ready without an explicit promotion path.
- Prefer readable function-oriented seams over unnecessary class extraction.
- When a production change touches detector or rule behavior, expect the nearest focused test lane or a clear reason not to add one.
- Distinguish review comments about production runtime code from comments about experiment readability in `detector_lab`.

## Skill boundaries

- Use this when the user wants a review or quality pass on detector/rule-area changes.
- If the main question is which test to run first, use `test-strategy-review`.
- If the main question is missing test coverage after the design is already understood, use `test-strategy-review` first.
- If the main question is planning future detector/rule work, use `task-planning-evaluation`.

## Good fit examples

- a blur-rule refactor needs review for behavior risk and test gaps
- a detector output contract changed and it is unclear whether processor and rules still line up
- `detector_lab` motion-blur work may be drifting toward production responsibilities
- a runtime-row refactor touched detectors, rules, and processor seams together

## Avoid

- turning the review into generic Python style advice
- pushing class-heavy redesigns when small helpers and explicit seams are clearer
- treating detector-lab experiments as production regressions without checking the boundary first
- listing every possible improvement when only one or two findings matter
