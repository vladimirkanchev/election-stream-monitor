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

## Discovery Description Baseline

This table records current active-skill discovery metadata before wording is
shortened. Character counts exclude YAML quotation marks. All 18 descriptions
currently exceed the 120--180 character editorial target; the guard range for
the next edit is 100--200 characters. Frequency remains inferred, not measured.

| Skill | Characters | Frequency | Primary seam | Nearest competing route | Invocation |
| --- | ---: | --- | --- | --- | --- |
| `branch-pr-readiness` | 245 | High | branch scope and merge readiness | task planning | automatic |
| `ci-failure-triage` | 275 | High | CI-failure classification and reproduction | incident analysis | automatic |
| `dependency-change-review` | 273 | Medium | dependency-file branch fit | branch readiness | automatic |
| `detector-rule-review` | 261 | High | production detector and rule boundaries | test strategy | automatic |
| `docs-alignment` | 303 | High | implementation-oriented documentation alignment | docs drift | automatic |
| `docs-drift-check` | 273 | Medium | pre-edit documentation drift audit | docs alignment | automatic |
| `fastapi-mcp-security-review` | 329 | Medium | branch-scoped FastAPI and MCP hardening | broad security review | automatic |
| `fixture-environment-safety` | 272 | High | test fixture and tool portability | real-media validation | automatic |
| `frontend-bridge-review` | 264 | Medium | renderer, Electron, and backend seam | manual validation | automatic |
| `incident-analysis` | 286 | Medium | incident reconstruction or cause hypothesis | CI triage | automatic |
| `manual-validation-planner` | 252 | Medium | operator-facing local smoke plan | test strategy | automatic |
| `persistence-backend-review` | 341 | Medium | session and alert persistence parity | security review | automatic |
| `readme-alignment-review` | 248 | Medium | root README section fit | docs alignment | automatic |
| `real-media-validation-review` | 330 | High | media-confidence lane selection | fixture safety | automatic |
| `release-version-readiness` | 368 | Medium | version-change semantics | branch readiness | automatic |
| `summarization` | 275 | Medium | concise repository or change summary | incident analysis | automatic |
| `task-planning-evaluation` | 257 | High | prioritization and sequencing | branch readiness | automatic |
| `test-strategy-review` | 247 | High | coverage value and validation lane | detector or media review | automatic |

The pre-edit active descriptions total 5,099 characters, averaging 283.3
characters. Archived architecture, PostgreSQL-rollout, and broad-security
specialists are explicit-only and retain their existing source unchanged.

## Final Discovery Description Baseline

The active descriptions now total 2,909 characters, averaging 161.6. The
shortening reduced discovery metadata by 2,190 characters (42.9%) from the
pre-edit baseline. All 18 descriptions are one line and fall within the
120--180 editorial target; tests enforce the wider 100--200 safety range.

`tests/repo_skill_expectations.py` owns required primary-seam phrases and
important exclusions. `tests/test_repo_skills.py` checks those meanings and
size boundaries without asserting complete description strings or using live
model calls. Archived specialists remain outside the active inventory and are
covered by explicit reactivation documentation.

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

## Historical Retired Skill Record

This is the only human-facing inventory section that retains identifiers for
skills removed through consolidation. They are historical migration evidence,
not active or archived routing options.

| Retired skill | Surviving owner |
| --- | --- |
| `alert-backend-parity-review` | `persistence-backend-review` |
| `incident-timeline` | `incident-analysis` |
| `root-cause-suggestion` | `incident-analysis` |

## Initial Skill Inventory

This is the pre-consolidation inventory. Its line counts and descriptions are
baseline evidence, not the current active discovery set.

| Skill | Current description and subsystem owner | Lines | Inferred frequency / future value | Targeted evidence | Commands |
| --- | --- | ---: | --- | --- | --- |
| Former alert-parity review | File/PostgreSQL alert parity and shared alert reads | 78 | Low now; high before PostgreSQL rollout | parity scenarios | none |
| `branch-pr-readiness` | Branch scope, commit shape, PR readiness, and safe cleanup | 167 | High; high | scenarios, snapshots, handoffs | `just branch-cleanup` |
| `ci-failure-triage` | Classify CI failures and choose the smallest reproduction | 75 | High; high | incident scenarios | `just ci-local`, focused test lanes |
| `dependency-change-review` | Decide whether dependency metadata belongs in a branch | 73 | Medium; high | dependency scenarios | none |
| `detector-rule-review` | Detector, alert-rule, and processor ownership review | 67 | High during detector work; high | detector scenarios | none |
| `docs-alignment` | Align project or code docs with behavior and ownership | 105 | High; high | docs scenarios and boundary pairs | none |
| `docs-drift-check` | Classify documentation drift before editing | 91 | Medium; medium | drift scenarios and boundary pairs | none |
| `fastapi-mcp-security-review` | Branch-scoped FastAPI/MCP hardening review | 93 | Medium; high before deployment | security scenarios | none |
| `fixture-environment-safety` | Fixture, tool, socket, and local-asset CI safety | 66 | High during detector/media work; high | environment scenarios | none |
| `frontend-bridge-review` | Renderer, preload, Electron, and backend seam review | 78 | Medium; high | frontend scenarios | `just test-frontend` |
| `incident-analysis` | Mode-selected timeline reconstruction or cause hypothesis | 89 | Low-medium; medium | incident scenarios and snapshots | none |
| `manual-validation-planner` | Small local operator smoke plans | 82 | Medium; high | manual-validation scenarios | none |
| `persistence-backend-review` | Session/alert persistence defaults, parity, and runtime selection | 89 | Medium; high before cloud work | persistence scenarios | `just test-session-store`, `just test-session-runtime` |
| `readme-alignment-review` | Root README fit, stage honesty, and section placement | 85 | Low-medium; medium | README scenarios and boundary pairs | none |
| `real-media-validation-review` | Real-media and stream confidence-lane review | 79 | High during detector work; high | real-media scenarios | `just test-real-media` |
| `release-version-readiness` | Patch/minor milestone readiness and release truth | 85 | Medium; high | release scenarios | none |
| `summarization` | Concise change, behavior, and next-action summaries | 94 | Medium; medium | summary scenarios and snapshots | none |
| `task-planning-evaluation` | Task priority, sequencing, and proportional closure | 104 | High; high | planning scenarios | none |
| `test-strategy-review` | Test value, ownership, and cheapest honest validation lane | 121 | High; high | test scenarios and handoffs | focused test lanes, `just docs-check`, `just ci-local` |

## Inventory Conclusions

- The final active inventory has 18 skills and 1,457 `SKILL.md` lines. The
  main cost is overlapping routing and maintenance, not any single oversized
  skill.
- The preceding active baseline had 1,688 lines; the four high-traffic skills
  now total 263 lines, down from 494, for a 231-line (13.7%) active reduction.
- Three archived specialists retain 252 `SKILL.md` lines and their snapshots,
  so the reduction removes routine discovery cost without deleting deferred
  deployment knowledge.
- Persistence parity and incident analysis now have one surviving owner each.
  Documentation-review consolidation remains deferred to its separate routing
  and documentation branch.
- Detector, fixture, real-media, and test-strategy skills remain distinct for
  the upcoming detector-improvement work, but should receive a later
  terminology refresh rather than a new detector-tuning skill.
- PostgreSQL and broad-security skills are low-frequency today but should be
  preserved as future deployment gates.
- Current tests prove skill-file structure and selected routing behavior; they
  do not measure real skill invocation frequency or live-model response
  quality.

## Consolidation Decision Criteria

Apply one proposed action per skill only after comparing its primary trigger,
workflow, output, and deterministic evidence with named alternatives.

| Action | Objective meaning | Required evidence |
| --- | --- | --- |
| Keep | Owns a distinct, currently useful boundary or output. | A primary prompt class or risky-change seam has no equally focused owner. |
| Merge | Substantially overlaps another skill's trigger, workflow, and output. | Name the surviving skill and migrate needed modes, scenarios, and handoffs. |
| Narrow | Remains valuable but its description or scope activates too broadly. | State the primary trigger and explicit exclusions without losing its distinct capability. |
| Archive | Has credible future value but little current relevance. | Record the reactivation condition and keep it available only for explicit use. |
| Remove | Has no distinct capability after consolidation. | Name the surviving owner and remove or migrate every test, reference, and snapshot. |

### Decision Rules

- Do not use low inferred frequency, small file size, or low recent visibility
  as sufficient evidence for archive or removal.
- Do not merge skills that share a subsystem but answer materially different
  questions, such as branch-scoped hardening versus broad trust-boundary
  review.
- Preserve a specialized skill when a broader alternative would make its
  expected validation lane, rollout concern, or operator outcome less clear.
- Treat archive as reversible scope reduction, not deletion. PostgreSQL and
  broad-security work are current examples of skills that may fit this action.
- Do not approve a merge or removal until deterministic expectations identify
  the surviving skill and still protect the intended boundary.

## Proposed Consolidation Matrix

Frequency is inferred, not measured. `Archive` means remove a skill from
ordinary discovery while retaining it for an explicit reactivation condition;
it does not mean delete its knowledge.

| Skill | Proposed action | Primary owner | Overlap candidate | Frequency | Future value | Rationale |
| --- | --- | --- | --- | --- | --- | --- |
| Former alert-parity review | Merged | `persistence-backend-review` | generic persistence review | Low | High | Alert parity is now an explicit mode of persistence review, not a separate first-choice routing boundary. |
| `architecture-diagram-review` | Archived | `.agents/archived-skills/` | README and docs review | Low | Medium | Reactivate only for concrete architecture-diagram work. |
| `branch-pr-readiness` | Narrowed | itself | release and summary work | High | High | Keeps branch scope, commits, PR shape, and merge readiness without repeated closure detail. |
| `ci-failure-triage` | Keep | itself | incident analysis | High | High | CI failure classification and smallest reproduction remain a distinct operational outcome. |
| `dependency-change-review` | Keep | itself | branch readiness | Medium | High | Dependency ownership is a focused, recurring decision that branch review should hand off. |
| `detector-rule-review` | Keep | itself | test strategy and real media | High | High | Owns production detector/rule boundaries; refresh terminology after consolidation. |
| `docs-alignment` | Keep | itself | docs drift and README fit | High | High | Becomes the surviving implementation-oriented documentation skill. |
| `docs-drift-check` | Merge, deferred | `docs-alignment` | documentation review | Medium | Medium | Its audit mode can become an explicit pre-edit mode in the surviving skill; implement with the separate routing/docs branch. |
| `fastapi-mcp-security-review` | Keep | itself | broad security review | Medium | High | Branch-scoped hardening remains distinct from pre-deployment surface mapping. |
| `fixture-environment-safety` | Keep | itself | real-media validation | High | High | Owns fixture/tool/socket availability rather than detector confidence itself. |
| `frontend-bridge-review` | Keep | itself | manual validation | Medium | High | Owns renderer/preload/main-process technical seam; manual validation is a different output. |
| `incident-analysis` | Merged | itself | timeline and root-cause analysis | Medium | Medium | One mode-selecting workflow owns both reconstruction and evidence-backed cause analysis. |
| `manual-validation-planner` | Keep | itself | test strategy and frontend review | Medium | High | Small operator smoke plans are not the same as automated-test selection. |
| `persistence-backend-review` | Keep and expand | itself | alert-backend parity | Medium | High | Survives as the persistence family owner and gains alert-parity mode. |
| `postgres-migration-rollout-review` | Archived | `.agents/archived-skills/` | persistence review | Low | High | Reactivate before migration or cloud persistence rollout. |
| `readme-alignment-review` | Merge, deferred | `docs-alignment` | documentation review | Low | Medium | Root-README fit can be a clearly bounded mode of the surviving docs skill; implement with the separate routing/docs branch. |
| `real-media-validation-review` | Keep | itself | fixtures and test strategy | High | High | Owns confidence-lane choice for decoded/local/stream media, not fixture availability or broad test policy. |
| `release-version-readiness` | Keep | itself | branch readiness | Medium | High | Version semantics remain separate from whether a branch is technically merge-ready. |
| `security-surface-review` | Archived | `.agents/archived-skills/` | FastAPI/MCP hardening | Low | High | Reactivate before broad trust review or public exposure. |
| `summarization` | Narrowed | itself | branch readiness and incident analysis | Medium | Medium | Keeps concise repository/change summaries; specialized skills own PR and incident work. |
| `task-planning-evaluation` | Narrowed | itself | branch readiness and test strategy | High | High | Keeps prioritization, sequencing, and proportional closure without absorbing PR or test ownership. |
| `test-strategy-review` | Narrowed | itself | detector, fixture, and real-media reviews | High | High | Keeps coverage value and cheapest honest validation without repeating the command catalog. |

### Approved Queue

1. Completed: merged the former alert-parity review into
   `persistence-backend-review`.
2. Completed: merged the former timeline and root-cause reviews into
   `incident-analysis`.
3. Completed: archived `architecture-diagram-review`,
   `postgres-migration-rollout-review`, and `security-surface-review` with
   their reactivation criteria.
4. Completed: narrowed branch/PR readiness, summarization, task planning, and
   test strategy while retaining their output modes and handoffs.
5. Defer the `docs-drift-check` and `readme-alignment-review` mergers until
   the separate user/agent documentation-routing branch. They should not be
   changed as incidental work in this harness branch.

The current harness has 18 ordinary-discovery skills, three archived specialist
skills, and two documentation-skill decisions intentionally deferred.

## Decision Validation and Frozen Boundaries

The proposed actions satisfy the decision criteria:

| Capability changing shape | Surviving owner or retention path | Evidence to migrate later |
| --- | --- | --- |
| Alert-backend parity | `persistence-backend-review` alert-parity mode | parity scenarios, boundary handoffs, `AGENTS.md` routing |
| Incident reconstruction and cause analysis | `incident-analysis` with timeline and hypothesis modes | both scenario sets, handoffs, and selected snapshots |
| Documentation audit and README fit | `docs-alignment`, deferred to the documentation-routing branch | docs scenarios, ambiguity pairs, `AGENTS.md`, and `docs/README.md` routing |
| Architecture-diagram review | archived skill; reactivate for a concrete diagram revision | skill source and output example in `.agents/archived-skills/` |
| PostgreSQL rollout review | archived skill; reactivate before migration, live rollout, or cloud persistence work | skill source and output example in `.agents/archived-skills/` |
| Broad security-surface review | archived skill; reactivate before public exposure or broad trust review | skill source and output example in `.agents/archived-skills/` |

No capability is proposed for irreversible removal. Archive actions preserve
their source and test evidence outside ordinary discovery until their named
reactivation condition applies.

### Completed Implementation Boundary

The active-skill consolidation is complete. It retained explicit boundaries and
deterministic coverage while reducing ordinary discovery to the current focused
owners. It did not consolidate general project documentation or implement the
deferred documentation-skill mergers.

### Deferred Boundaries

- The `docs-drift-check` and `readme-alignment-review` mergers belong to the
  separate documentation-routing branch because they require coordinated
  changes to user and agent documentation.
- Archived PostgreSQL and broad-security skills are future deployment gates,
  not current detector or local-pilot work.
- Detector, fixture, real-media, and test-strategy terminology refresh is a
  later focused follow-up after the next detector-improvement cycle confirms
  the stable workflow.
