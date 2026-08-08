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

## Current Skills

| Skill | Current description and subsystem owner | Lines | Inferred frequency / future value | Targeted evidence | Commands |
| --- | --- | ---: | --- | --- | --- |
| `alert-backend-parity-review` | File/PostgreSQL alert parity and shared alert reads | 78 | Low now; high before PostgreSQL rollout | parity scenarios | none |
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
| `task-planning-evaluation` | Task priority, scope, complexity, and execution sequencing | 104 | High; high | planning scenarios | none |
| `test-strategy-review` | Test value, ownership, and cheapest honest validation lane | 121 | High; high | test scenarios and handoffs | focused test lanes, `just docs-check`, `just ci-local` |

## Inventory Conclusions

- The harness has 18 skills and roughly 1,700 skill lines. The main cost is
  overlapping routing and maintenance, not any single oversized skill.
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
| `alert-backend-parity-review` | Merged | `persistence-backend-review` | generic persistence review | Low | High | Alert parity is now an explicit mode of persistence review, not a separate first-choice routing boundary. |
| `architecture-diagram-review` | Archived | `.agents/archived-skills/` | README and docs review | Low | Medium | Reactivate only for concrete architecture-diagram work. |
| `branch-pr-readiness` | Narrow | itself | release and summary work | High | High | Keep its unique merge/commit scope; trim repeated closure and PR-template detail. |
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
| `summarization` | Narrow | itself | branch readiness and incident analysis | Medium | Medium | Retain only concise repository/change summaries; specialized skills own PR and incident summaries. |
| `task-planning-evaluation` | Narrow | itself | branch readiness and test strategy | High | High | Keep prioritization and sequencing; add the proportional closure phase without absorbing PR or test ownership. |
| `test-strategy-review` | Narrow | itself | detector, fixture, and real-media reviews | High | High | Keep the lane chooser; remove repeated lane listings that other skills can reference. |

### Approved Queue

1. Completed: merged `alert-backend-parity-review` into
   `persistence-backend-review`.
2. Completed: merged `incident-timeline` and `root-cause-suggestion` into
   `incident-analysis`.
3. Completed: archived `architecture-diagram-review`,
   `postgres-migration-rollout-review`, and `security-surface-review` with
   their reactivation criteria.
4. Narrow the four high-traffic owners: branch/PR readiness, summarization,
   task planning, and test strategy.
5. Defer the `docs-drift-check` and `readme-alignment-review` mergers until
   the separate user/agent documentation-routing branch. They should not be
   changed as incidental work in this harness branch.

This queue leaves 16 ordinary-discovery skills, three archived specialist
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

### Remaining Implementation Boundary

The remaining implementation work may only:

1. narrow branch readiness, summarization, task planning, and test strategy.

It must update affected deterministic expectations and harness references in
the same change, then run the focused repo-skill tests. It must not consolidate
general project documentation or implement the deferred documentation-skill
mergers.

### Deferred Boundaries

- The `docs-drift-check` and `readme-alignment-review` mergers belong to the
  separate documentation-routing branch because they require coordinated
  changes to user and agent documentation.
- Archived PostgreSQL and broad-security skills are future deployment gates,
  not current detector or local-pilot work.
- Detector, fixture, real-media, and test-strategy terminology refresh is a
  later focused follow-up after the next detector-improvement cycle confirms
  the stable workflow.
