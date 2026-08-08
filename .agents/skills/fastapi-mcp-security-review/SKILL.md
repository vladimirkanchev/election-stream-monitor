---
name: fastapi-mcp-security-review
description: Use for branch-scoped Election Stream Monitor FastAPI/MCP security for share mode, auth, tool exposure, and dependency exposure. Excludes broad trust review and deployment design.
---

# Fastapi Mcp Security Review

Use this skill when the main need is: "does this FastAPI or MCP branch keep
the current security model clear enough for the repo stage?"

This repo commonly needs FastAPI/MCP security review across:

- FastAPI auth and access-mode behavior
- `share` mode boundaries and rate limiting
- MCP tool exposure and read-only assumptions
- local versus remote trust decisions
- secret/config handling and dependency exposure

## Default approach

Review the branch against the current security model before suggesting broader
platform controls. Keep this skill branch-scoped and checklist-oriented.

Work from:

1. changed FastAPI, MCP, auth, or access-policy modules
2. whether the path is local-only, `share` mode, or broader
3. what the branch exposes, protects, or newly trusts
4. the smallest realistic hardening gap
5. the cheapest validation lane or follow-up

Use this compact checklist:

1. auth: who can reach the path or tool now?
2. `share` mode: does the branch widen anything outside the intended demo path?
3. MCP boundary: are tools still read-only and appropriately scoped?
4. rate limits: did request throttling or abuse protection drift?
5. secrets/config: are tokens, keys, or trust defaults still handled safely?
6. local-versus-remote trust: did the branch silently promote a local path into
   a remote-capable one?
7. dependency exposure: did new packages or external integrations widen the
   risk surface?

## Output shape

Use this order:

1. `Security surface`
2. `Current protection`
3. `Checklist gaps`
4. `Best next hardening step`
5. `Best validation lane`

Keep the review concrete and branch-scoped.

## Project-specific rules

- Judge recommendations against the current local-first advanced-prototype
  stage, not a hosted multi-tenant platform.
- Treat FastAPI HTTP exposure and MCP `stdio` tooling as different trust
  surfaces even when they touch the same data.
- Call out when protection exists only in `share` mode versus always-on local
  behavior.
- Prefer this skill for branch-scoped hardening review, not for broad
  architecture-wide surface mapping.
- Prefer practical suggestions such as auth tightening, rate limits, clearer
  config defaults, narrower tool scopes, or docs clarification over broad
  platform redesign.
- If new dependencies matter mainly because they widen security or trust
  exposure, say that plainly even if the branch is not a dependency-focused
  branch.

## Skill boundaries

- Use this when the main question is FastAPI/MCP branch hardening, security
  review, or branch-scoped security checklist coverage.
- For a broader trust review before public exposure, reactivate the archived
  `security-surface-review`.
- If the main issue is a failing security or dependency CI job, use `ci-failure-triage` first.
- If the question is primarily docs wording drift, use `docs-alignment` first.
- If the question is branch scope or merge shape, use `branch-pr-readiness` first.

## Good fit examples

- a FastAPI route branch may have widened `share` mode beyond the intended boundary
- an MCP tool update may have drifted outside the read-only local tooling model
- an auth or rate-limit refactor needs a compact security review before merge
- a new integration may have increased dependency exposure or secret-handling risk

## Avoid

- treating every local-first limitation like an immediate hosted-service flaw
- turning the review into a full vulnerability-management program
- mixing persistence parity questions into FastAPI/MCP security review
- recommending cloud-scale controls before the branch actually changes the
  relevant exposure
