---
name: security-surface-review
description: Use when the user wants a repo-aware review of security-sensitive surfaces in Election Stream Monitor. Best for checking FastAPI routes, MCP tooling, local sharing paths, auth/rate-limit seams, and trust-boundary drift without expanding into a full security program.
---

# Security Surface Review

Use this skill when the main need is: "what are the meaningful security-sensitive surfaces here, and do they look appropriately bounded for the current repo stage?"

This repo commonly needs security-surface review across:

- FastAPI auth and rate-limit behavior
- alert routes and local sharing mode
- MCP read-only tool surfaces
- `api_stream` trust and source-validation boundaries
- Electron or local desktop paths that proxy or expose media/runtime access

## Default approach

Review exposed boundaries before suggesting hardening.

Work from:

1. changed security-sensitive module or route
2. current trust boundary
3. whether the surface is local-only, shared-demo, or broader
4. what is already protected versus still intentionally out of scope
5. the smallest meaningful risk or follow-up

## Output shape

Use this order:

1. `Security surface`
2. `Current protection`
3. `Main risk`
4. `Best next hardening step`
5. `What is intentionally out of scope`

## Project-specific rules

- Judge security recommendations against the current local-first advanced-prototype stage, not a full hosted platform model.
- Distinguish FastAPI HTTP exposure from MCP `stdio` local tooling; they are not the same surface.
- Call out when a route or path is protected only in `share` mode versus always local-only.
- Prefer narrow practical hardening suggestions such as auth, rate limits, trust-policy checks, or clearer defaults over broad platform redesigns.
- If the current behavior is acceptable for local/demo use but not for broader deployment, say that plainly.
- Keep this skill about security surface review, not full vulnerability management or dependency scanning.

## Skill boundaries

- Use this when the user wants a security-oriented review of current code or architecture surfaces.
- If the main issue is a failing security CI job, use `ci-failure-triage` first.
- If the main question is broad project planning, use `task-planning-evaluation` first.
- If the main question is docs drift in security guidance, use `docs-alignment` first.

## Good fit examples

- a FastAPI route change may have drifted outside the intended auth or rate-limit boundary
- MCP local tooling needs a clear statement on what is and is not protected
- local sharing mode is useful now, but the repo needs a realistic note on its current limits
- an `api_stream` trust policy change needs review for boundary clarity rather than full platform redesign

## Avoid

- treating the repo like a public multi-tenant hosted service when it is still local-first
- expanding into generic security checklists with no repo fit
- confusing local/demo limitations with immediate critical product failures
- mixing dependency or vulnerability audit work into this skill
