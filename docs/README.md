# Docs Index

This folder is the maintainer reference set for contributors, reviewers, and
AI-assisted development. It routes work to the document that owns the current
behavior or policy; it is not a second architecture, test, or source-code
inventory.

Start with the root [README](../README.md) for product orientation and a first
local run. Use [CONTRIBUTING.md](../CONTRIBUTING.md) for everyday branch flow,
setup, and validation. Use [AGENTS.md](../AGENTS.md) for the shortest safe path
through AI-assisted changes and risky seams.

Use the repo-local interpreter or a `just` recipe for Python commands. The
workspace does not auto-activate `.venv`. The root
[environment contract](../README.md#version-contract) owns supported,
contributor-default, and CI-validated tool versions.

## First Reads

For a new or returning maintainer:

1. [NEXT_SESSION.md](../NEXT_SESSION.md) when resuming work.
2. [architecture.md](./architecture.md) for runtime responsibility placement.
3. [contracts.md](./contracts.md) for stable public and cross-layer shapes.
4. [session-model.md](./session-model.md) for lifecycle and persistence meaning.
5. The task route below for the seam you are changing.

## Document Ownership

Each document has one primary role. A short summary elsewhere is appropriate
only when it serves a different audience, introduces no independent policy,
and links to this owner.

| Document(s) | Primary role | Audience | Status |
| --- | --- | --- | --- |
| [README.md](../README.md) | Product entry point | User, contributor | Active |
| [CONTRIBUTING.md](../CONTRIBUTING.md) | Contribution workflow | Contributor | Active |
| [AGENTS.md](../AGENTS.md) | Safe AI-agent entry point | AI agent, contributor | Active |
| `docs/README.md` | Maintainer routing | Contributor, maintainer, AI agent | Stable |
| [architecture.md](./architecture.md), [architecture-decision-fastapi.md](./architecture-decision-fastapi.md), [frontend-architecture.md](./frontend-architecture.md), [fastapi-boundary.md](./fastapi-boundary.md) | Architecture and boundary responsibility | Contributor, maintainer | Stable |
| [contracts.md](./contracts.md), [session-model.md](./session-model.md), [data-models.md](./data-models.md) | Stable contracts and lifecycle meaning | Contributor, maintainer, AI agent | Stable |
| [adding-an-analyzer.md](./adding-an-analyzer.md), [adding-an-alert-rule.md](./adding-an-alert-rule.md), [detector-template.md](./detector-template.md) | Detector and rule extension guide | Contributor, AI agent | Active |
| [testing-and-validation.md](./testing-and-validation.md), [api-stream-local-validation.md](./api-stream-local-validation.md), [git-hooks.md](./git-hooks.md) | Commands and validation procedures | Contributor, maintainer, operator | Active |
| [branch-purpose-template.md](./branch-purpose-template.md), [merge-readiness-checklist.md](./merge-readiness-checklist.md), [reviewer-guide.md](./reviewer-guide.md) | Branch and review workflow | Contributor, maintainer, AI agent | Active |
| [ci-maintainer-guide.md](./ci-maintainer-guide.md), [fixture-environment-policy.md](./fixture-environment-policy.md), [development-environment-audit.md](./development-environment-audit.md), [release-versioning.md](./release-versioning.md) | Maintainer policy | Maintainer, contributor, AI agent | Stable |
| [mcp-server.md](./mcp-server.md) | MCP boundary policy | Contributor, maintainer | Active |
| [detector-validation-ownership.md](./detector-validation-ownership.md), [coverage-evidence.md](./coverage-evidence.md) | Detector validation evidence | Maintainer, detector engineer, AI agent | Active |
| [detector-lab-analysis.md](./detector-lab-analysis.md), [motion-coherence.md](./motion-coherence.md) | Experimental detector evidence | Detector engineer, AI agent | Active; non-contractual |
| [dependency-ownership-audit.md](./dependency-ownership-audit.md), [static-analysis-audit.md](./static-analysis-audit.md), [session-persistence-audit.md](./session-persistence-audit.md) | Readiness and ownership evidence | Maintainer, contributor | Active; used at named follow-up gates |
| [api-stream-operational-inventory.md](./api-stream-operational-inventory.md) | Operational evidence | Maintainer, operator | Deferred |
| [api-stream-election-policy-task-list.md](./api-stream-election-policy-task-list.md), [stream-profile-product-brainstorm.md](./stream-profile-product-brainstorm.md) | Planning note | Maintainer, product contributor | Deferred |

Deferred and planning documents are discoverable context, not current runtime
or onboarding policy. Archive or remove a document only after its remaining
meaning has a named owner and incoming links have been checked.

## Task-Based Reading Paths

### Understand Or Change Runtime Behavior

Read [architecture.md](./architecture.md) first. Move to
[contracts.md](./contracts.md) for payload or bridge shapes, and to
[session-model.md](./session-model.md) for lifecycle or persistence meaning.

### Add Or Tune A Detector Or Alert Rule

Use [adding-an-analyzer.md](./adding-an-analyzer.md) or
[adding-an-alert-rule.md](./adding-an-alert-rule.md), then
[testing-and-validation.md](./testing-and-validation.md). Keep supported
runtime behavior separate from experimental work in
[detector_lab/README.md](../detector_lab/README.md). For reviewed test and
fixture ownership, use [detector-validation-ownership.md](./detector-validation-ownership.md).

### Work On Session Or Alert Persistence

Read [session-model.md](./session-model.md) and [contracts.md](./contracts.md),
then [session-persistence-audit.md](./session-persistence-audit.md) for the
file-backed default, explicit PostgreSQL selection, rollout evidence, and
deferred migration work. Use [testing-and-validation.md](./testing-and-validation.md)
to choose the smallest honest validation lane.

### Change FastAPI, MCP, Or Trust Boundaries

Read [contracts.md](./contracts.md), [fastapi-boundary.md](./fastapi-boundary.md),
and [mcp-server.md](./mcp-server.md). FastAPI share-mode protection and local
stdio MCP trust are distinct boundaries; do not infer one policy from the
other.

### Change Frontend, Electron, Or Playback

Start with [frontend-architecture.md](./frontend-architecture.md). Read
[contracts.md](./contracts.md) for bridge shapes and
[testing-and-validation.md](./testing-and-validation.md) for focused frontend,
bridge, and runtime validation.

### Choose Tests, CI, Or Fixture Handling

Use [testing-and-validation.md](./testing-and-validation.md) for local
commands, lane meaning, and manual versus automated confidence. Use
[ci-maintainer-guide.md](./ci-maintainer-guide.md) for required, advisory,
informational, weekly, and protected-PR policy. Use
[fixture-environment-policy.md](./fixture-environment-policy.md) before making
local assets, host tools, sockets, or generated media part of shared tests.

The shared CI target manifest is `.github/ci_test_targets.json`; its Python
reader is `.github/scripts/ci_target_manifest.py`. The protected shared
contract groups are `backend_contract`, `mcp_fastapi_parity`, and
`frontend_contract`. `.github/scripts/check_ci_target_drift.py` verifies that
workflow, policy, and required documentation references stay aligned, while
`.github/scripts/check_main_pr_consistency.py` owns the narrower protected
`main` pull-request policy.

### Change Setup, Dependencies, Or Static Analysis

Use [development-environment-audit.md](./development-environment-audit.md) for
tool and optional-capability ownership, [dependency-ownership-audit.md](./dependency-ownership-audit.md)
for Python dependency sources, and [static-analysis-audit.md](./static-analysis-audit.md)
for lint, formatter, and typing policy. `justfile` is the local command owner;
[CONTRIBUTING.md](../CONTRIBUTING.md) is the short setup and branch-flow route.

### Plan, Review, Or Release A Branch

Start with [branch-purpose-template.md](./branch-purpose-template.md), keep
the PR template current, and finish with
[merge-readiness-checklist.md](./merge-readiness-checklist.md). Use
[reviewer-guide.md](./reviewer-guide.md) for review context and
[release-versioning.md](./release-versioning.md) plus
[CHANGELOG.md](../CHANGELOG.md) for version and release meaning.

### Work On Repo-Local AI Harnesses

Use [AGENTS.md](../AGENTS.md) for safe repository routing. The active and
archived skill inventory, consolidation evidence, and explicit reactivation
conditions live in [`.agents/skills/INVENTORY.md`](../.agents/skills/INVENTORY.md).
Use [testing-and-validation.md](./testing-and-validation.md#repo-local-skill-tests)
for the deterministic harness-validation lane.

## Extension And Visual References

Detector and rule extension guides:

- [adding-an-analyzer.md](./adding-an-analyzer.md)
- [adding-an-alert-rule.md](./adding-an-alert-rule.md)
- [detector-template.md](./detector-template.md)

Visual references:

- [runtime-flow.svg](./runtime-flow.svg)
- [plugin-structure.svg](./plugin-structure.svg)
- [frontend-overview.svg](./frontend-overview.svg)
- [frontend-flow.svg](./frontend-flow.svg)
- [detector-and-alert-extension-flow.svg](./detector-and-alert-extension-flow.svg)

## Update Rules

- Code and tests decide current behavior when documentation drifts.
- Update the closest owner when a contract, lifecycle, trust boundary, or
  validation/CI ownership changes.
- Keep README-level summaries shorter than their owning guide and link to it.
- Do not copy source-file inventories, test inventories, command catalogs, or
  full skill catalogs into this index.
