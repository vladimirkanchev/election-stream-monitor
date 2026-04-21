# API Stream Election Policy Task List

This note turns the current `api_stream` inventory and election-profile
comparison into a concrete decision list for future policy work.

Related notes:

- [api-stream-operational-inventory.md](./api-stream-operational-inventory.md)
- [api-stream-election-profile-comparison.md](./api-stream-election-profile-comparison.md)

This is an internal planning note for maintainers and coding agents.

## Goal

Decide which parts of the current generic `api_stream` runtime should stay
generic, which should become profile-driven for election monitoring, and which
should remain deferred until the system needs more semantic richness.

## Mini Decision Checkpoint

This checkpoint reflects the current backend code and the focused recovery
tests added in the same branch.

Current decision:

- keep the stable `status_reason` vocabulary small for now
- continue using `status_detail` for most loader/runtime-specific `api_stream`
  failure detail
- treat idle exhaustion as the only clearly unresolved semantic tension
- avoid adding richer interrupted/degraded lifecycle categories in this branch

Why this checkpoint matters:

- it keeps the current branch focused on evidence-backed clarification rather
  than semantic expansion
- it narrows later implementation work to the one area that still appears
  meaningfully questionable for election streams: idle exhaustion semantics

## Decision Task 1: Idle Exhaustion Semantics

### Question

When an election stream stops producing new segments and the idle polling budget
is exhausted, should the final session still persist as:

- `completed`

or should it later map to something more interruption-oriented?

### Current behavior

- loader stop reason: `idle_poll_budget_exhausted`
- persisted terminal session:
  - `status = completed`
  - `status_reason = idle_poll_budget_exhausted`
  - `status_detail = Idle poll budget exhausted`

### Why this matters

For Bulgarian polling-station monitoring, a feed silently going idle may mean:

- camera/network interruption
- upstream provider stall
- operational loss of visibility

That is often not equivalent to a healthy successful completion.

### Decision alternatives

#### A. Keep current behavior globally

Pros:

- simplest
- no contract changes
- keeps current frontend messaging stable

Cons:

- likely too optimistic for civic-monitoring streams

#### B. Make idle exhaustion profile-driven later

Pros:

- best fit for mixed stream classes
- avoids forcing one meaning across all election feeds

Cons:

- requires profile infrastructure

#### C. Change generic behavior now

Pros:

- clearer for election monitoring immediately

Cons:

- bigger contract change
- may be too broad for non-election live streams

### Recommended direction

- **current branch outcome:** apply the narrow clarification now by persisting
  `status_reason = idle_poll_budget_exhausted` while keeping `status = completed`
- still prefer later profile-aware policy work if different election stream
  classes need different idle semantics beyond this clarification
- avoid a broader generic semantic rewrite until profile work is ready

## Decision Task 2: Which Budgets Become Profile-Driven First

### Question

Which operational limits should be the first candidates for profile-based
defaults rather than one generic `api_stream` policy?

### Candidate budgets

- reconnect budget
- idle poll budget
- max session runtime
- playlist refresh limit
- fetch byte budget
- temp storage budget

### Decision criteria

Use these criteria to rank them:

- biggest effect on election-stream operator trust
- biggest mismatch between current generic defaults and long-running civic feeds
- lowest cross-layer churn
- easiest to explain in profile terms

### Recommended first tier

These are the best first profile-driven candidates:

1. idle poll budget
2. max session runtime
3. reconnect budget
4. playlist refresh limit

### Why these first

- they are the most clearly tied to stream behavior and operational meaning
- they affect election-stream suitability more than low-level fetch/storage
  safety rails do

### Recommended second tier

- fetch byte budget
- temp storage budget

These should likely remain global safety rails until a stronger operational need
appears.

## Decision Task 3: Whether To Add A Richer Interrupted/Degraded Concept

### Question

Does election monitoring need one extra stable concept beyond the current
baseline of:

- `completed`
- `cancel_requested`
- `source_unreachable`
- `validation_failed`
- `terminal_failure`

### Why this matters

Current semantics are stable and intentionally compact, but election operations
may eventually want to distinguish:

- fully failed
- temporarily degraded
- feed interrupted but not conclusively dead

### Decision alternatives

#### A. Keep current stable reason vocabulary

Pros:

- simplest
- preserves clean cross-layer semantics
- minimizes frontend churn

Cons:

- some election-specific operational meaning stays implicit

#### B. Add richer semantics later through profile-aware UX first

Meaning:

- keep lifecycle reasons stable
- let profile-specific frontend wording interpret existing statuses differently

Pros:

- lower contract risk
- good intermediate step

Cons:

- semantics stay partly indirect

#### C. Add a new stable interrupted/degraded session concept

Pros:

- stronger operator meaning
- clearer election-stream interpretation

Cons:

- bigger backend/API/bridge/frontend contract change
- higher long-term maintenance cost

### Recommended direction

- prefer **A** or **B** first
- defer **C** unless current semantics clearly stop serving operators well

## Current Branch Outcome

Applying the conservative sequence for this branch leads to:

1. checkpoint the real ambiguity first
2. keep stable reasons compact where they are already serving well
3. apply one narrow semantic clarification for idle exhaustion
4. defer any richer interrupted/degraded split unless a later branch proves it
   necessary

That means the current branch now carries one targeted persisted-lifecycle
clarification:

- `status = completed`
- `status_reason = idle_poll_budget_exhausted`
- `status_detail = Idle poll budget exhausted`

while still avoiding broader reason-taxonomy churn.

## Suggested Execution Order

### Phase 1: policy decisions without behavior change

1. decide target meaning for idle exhaustion
2. rank budgets by profile-value
3. decide whether richer lifecycle semantics are truly needed or only richer
   profile-aware UX

### Phase 2: profile-ready implementation work

1. make first-tier budgets profile-driven
2. keep fetch/storage as global safety defaults unless evidence says otherwise
3. align frontend wording with the chosen election-stream profile defaults

### Phase 3: richer lifecycle semantics only if necessary

1. revisit interrupted/degraded concept
2. only introduce a new stable lifecycle state or reason if existing UX-based
   distinctions are clearly insufficient

## Recommended Default Stance For Now

If a new branch starts from these notes today, the safest planning defaults are:

- keep `status` stable unless there is a strong user-facing reason to change it
- allow `status_reason` to become more specific only when the meaning is both
  operationally important and cross-layer stable
- treat idle exhaustion as clarified for now, but revisit whether different
  election profiles should interpret it differently

- idle exhaustion is the highest-priority semantic question
- runtime/reconnect/idle/refresh budgets are the first profile-driven knobs
- fetch and temp-storage remain global safety rails
- richer interrupted/degraded semantics stay deferred until profile-aware UX is
  proven insufficient

## Bottom Line

The next election-focused policy work should begin with:

1. deciding what idle exhaustion really means for civic monitoring
2. deciding which operational budgets should become profile-driven first
3. deliberately deferring richer lifecycle semantics unless current stable
   reasons prove inadequate
