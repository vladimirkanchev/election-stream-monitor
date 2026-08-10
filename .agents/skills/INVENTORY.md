# AI Harness Inventory

Baseline recorded 2026-08-08 for `chore/ai-harness-consolidation`.

This is an internal harness inventory, not a user-facing project guide. It
records the initial skill set and updates approved consolidation decisions as
they are implemented.

## Evidence Method

- Size is the current `SKILL.md` line count.
- Frequency is inferred from the current roadmap, `AGENTS.md` routing, and
  recent collaboration themes. It is not invocation telemetry.
- Every skill has deterministic inventory, frontmatter, and section-order
  coverage in `tests/test_repo_skills.py`. `tests/repo_skill_expectations.py`
  adds targeted boundary, scenario, handoff, ambiguity, and selected
  output-snapshot checks.
- Commands list only explicit focused `just` recipes named by the skill;
  `none` means it does not prescribe one.

## Final Closure Evidence

Measured against `origin/main` (`cc5faeaf`) and branch `HEAD` (`b707935`) on
2026-08-08:

- Active skills: `23 -> 18`; archived specialists: `0 -> 3`.
- Active `SKILL.md` lines: `1,688 -> 1,457` (`13.7%` lower).
- Discovery descriptions: `5,099 -> 2,909` characters (`42.9%` lower;
  average `283.3 -> 161.6`).
- Retained owners: `persistence-backend-review` owns alert parity;
  `incident-analysis` owns timeline and hypothesis modes; detector, fixture,
  real-media, testing, CI, and branch-review skills remain distinct.
- Deterministic validation on 2026-08-08: `just test-repo-skills` passed with
  `210` tests; all 18 active and 3 archived skills passed structural
  validation; `just docs-check` and `git diff --check` passed.
- The six-case manual routing exercise was a contaminated dry run, not a
  formal fresh-session baseline.
- `docs-drift-check` and `readme-alignment-review` consolidation remains
  deferred to the separate documentation-routing branch.

## Current Ownership

- `persistence-backend-review` includes alert-parity review; `incident-analysis`
  selects timeline or root-cause mode from the available evidence.
- Planning, branch readiness, test strategy, detector/rule, fixture, real-media,
  CI, and frontend review remain separate active seams.
- `architecture-diagram-review`, `postgres-migration-rollout-review`, and
  `security-surface-review` are explicit-only specialists under
  `../archived-skills/`.
- `docs-drift-check` and `readme-alignment-review` remain active until their
  separate documentation-routing consolidation.

Discovery descriptions are one line, target 120--180 characters, and are
guarded at 100--200 characters. The deterministic harness protects required
primary seams and realistic exclusions without comparing complete prose or
calling a model.

## Historical Retired Skill Record

This is the only human-facing inventory section that retains identifiers for
skills removed through consolidation. They are historical migration evidence,
not active or archived routing options.

| Retired skill | Surviving owner |
| --- | --- |
| `alert-backend-parity-review` | `persistence-backend-review` |
| `incident-timeline` | `incident-analysis` |
| `root-cause-suggestion` | `incident-analysis` |
