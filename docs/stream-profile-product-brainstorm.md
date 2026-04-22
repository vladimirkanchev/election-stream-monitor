# Stream Profile Product Brainstorm

This note captures the recent brainstorming discussion about how the current
monitoring project could evolve into a more adaptable stream-monitoring product.

It is written for maintainers, product thinkers, and coding agents. It is not
end-user documentation.

## Core Product Direction

The strongest next-project concept discussed was:

- an adaptive live stream monitoring platform
- profile-driven rather than hardcoded for one source type
- suitable for multiple stream classes with different QoS and QoE needs

Examples of stream classes:

- stable sports broadcast feeds
- betting and odds-adjacent low-latency feeds
- amateur or mobile live streams with higher instability
- event or venue streams with mixed operator skill levels

## Main Design Principle

Separate these concerns:

- transport/source adapter
- operational policy
- detector bundle
- rule bundle
- session lifecycle semantics

That means the adaptable unit should become:

- profile + adapter + detector pack + rule pack

not:

- scattered provider-specific conditionals
- UI-level low-level knobs
- detector-specific lifecycle semantics

## Stream Profiles

The key idea was to introduce a stream profile system.

A profile would define:

- source assumptions
- retry/reconnect policy
- idle policy
- runtime and storage budgets
- expected latency sensitivity
- acceptable instability/degradation
- default detectors
- default rules
- operator-facing messaging defaults

Illustrative profile examples:

- `broadcast_balanced`
- `betting_low_latency`
- `amateur_mobile_live`
- `unstable_network_tolerant`

## Audience For Profile Configuration

The profile system should not be primarily driven by agents.

Recommended hierarchy:

1. built-in presets
2. config-file overrides
3. optional simple UI chooser
4. agent assistance for recommendation and generation
5. backend/FastAPI persistence later if needed

Agents should act as:

- recommendation helpers
- config generators
- explainers of tradeoffs

Agents should not be:

- the system of record
- the canonical storage for user profile information

## UI Philosophy

The discussion strongly favored avoiding UI overload.

Recommended split:

- UI = user intent
- config = expert control
- backend = policy enforcement
- agent = setup/config assistant

Main-screen UI should only expose high-level intent such as:

- source type
- monitoring profile
- perhaps a small number of priority modes

It should not expose raw runtime knobs such as:

- reconnect budget
- byte budget
- temp storage cap
- idle poll count
- refresh limit

Those belong in:

- config files
- backend defaults
- advanced settings later

## Detectors And Rules

Detectors and rules fit naturally into the profile-driven model.

Recommended interpretation:

- detectors are capabilities
- rules are interpretation/policy
- profiles choose defaults for both

This keeps the main UI simpler because users can choose intent/profile first,
while detector/rule defaults follow from that choice.

Important architectural boundary:

- session lifecycle should stay platform-level and stable
- detector/rule specifics should mostly appear in alerts and results

When adding future detectors or rules, ask:

- does this change session lifecycle meaning?
- or only analysis findings / alerts?

Usually it should affect:

- alerts
- results

not:

- session lifecycle semantics

## Stable Lifecycle Semantics

The recommended long-term approach was to keep a small stable runtime/session
vocabulary and avoid provider-specific or detector-specific lifecycle sprawl.

Suggested stable `status_reason` style:

- `completed`
- `cancel_requested`
- `source_unreachable`
- `idle_poll_budget_exhausted`
- `terminal_failure`
- `validation_failed`

Use:

- `status_reason` for small stable machine-readable meanings
- `status_detail` for diagnostic explanation
- alerts/results for detector- and rule-specific findings

## Policy Ideas For Different Stream Classes

### Betting / low-latency streams

Priorities:

- freshness
- low latency
- fast failure detection
- strict stale-data tolerance

Operational preference:

- lower retry tolerance
- lower idle tolerance
- stronger degraded-state signaling

### Amateur / mobile / fragile streams

Priorities:

- recovery tolerance
- graceful degraded mode
- reduced operator noise during brief outages

Operational preference:

- more retries
- larger recovery windows
- softer instability handling before terminal stop

### Broadcast / professional sports feeds

Priorities:

- continuity
- moderate latency tolerance
- clearer distinction between transient and terminal provider issues

Operational preference:

- balanced retry policy
- stronger long-run operational stability

## Recommended Product Targets

The most promising client categories discussed were:

- sports broadcasters and sports media operations teams
- betting and odds-adjacent organizations
- amateur and semi-pro sports streaming platforms
- event production teams
- managed media monitoring providers

Strongest suggested initial target:

- sports and betting-adjacent live stream operations

Why:

- high value of timeliness and reliability
- clear operational pain
- strong fit for adaptive profiles and differentiated policies

## How This Fits The Current Project

This direction was assessed as a good fit for the current codebase because the
project already has improving separation across:

- backend/session semantics
- FastAPI boundary semantics
- Electron wiring/composition
- frontend contract normalization
- detector/rule distinction

So a future stream-profile branch would fit best as:

- policy/config extensibility

not:

- a rewrite
- or immediate support for every provider type

## Recommended Next-Branch Direction

The suggested next branch theme was:

- build the extensibility foundation for stream/source profiles and operational policy

not:

- support every new stream type immediately

Recommended first-step scope for such a branch:

1. define profile and policy concepts
2. add an internal schema/model
3. route one or two current `api_stream` policies through it
4. document extension boundaries for future sources, detectors, and rules

## Guidance For FastAPI And MCP

FastAPI was considered a strong place to host:

- profile selection
- source capability validation
- policy defaults
- request/response schemas for source policy

MCP was considered useful later for:

- profile discovery
- detector and rule catalog access
- AI-assisted safe configuration
- configuration generation and recommendation

Best long-term role:

- FastAPI = policy authority
- MCP = discovery/configuration helper layer

## Summary

The main conclusion of the discussion was:

- keep lifecycle semantics small and stable
- move adaptability into profiles/policies
- keep the main UI simple
- let config and backend carry the complexity
- let agents assist, not own, configuration

This note is intended to preserve that design direction for future planning.
