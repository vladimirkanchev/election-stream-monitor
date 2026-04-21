# API Stream Operational Inventory

This note maps the current `api_stream` failure and recovery behavior before
adding more soak checks, election-specific policy, or broader UX changes.

It is written for maintainers and coding agents. It is not end-user
documentation.

This version follows the "Option B" approach:

- record what the code and tests currently do
- add a suitability note for Bulgarian polling-station election video streams
- separate current truth from future policy decisions

## Scope

This inventory focuses on:

- reconnect retries
- idle budgets
- runtime budgets
- byte and storage limits
- upstream HTTP and network failures
- terminal `status_reason` and `status_detail`

Primary sources:

- [`src/stream_loader.py`](../src/stream_loader.py)
- [`src/session_runner.py`](../src/session_runner.py)
- [`tests/test_stream_loader_http_hls_reconnect.py`](../tests/test_stream_loader_http_hls_reconnect.py)
- [`tests/test_stream_loader_http_hls_limits.py`](../tests/test_stream_loader_http_hls_limits.py)
- [`tests/test_session_runner_api_stream_http_hls.py`](../tests/test_session_runner_api_stream_http_hls.py)

## Reviewer Checklist

Use this short checklist when reviewing current `api_stream` operational
behavior before proposing new election-stream policy:

- confirm which upstream failures are retryable vs terminal
- confirm where reconnect budget exhaustion becomes terminal
- confirm what idle poll exhaustion currently persists as
- confirm which safety rails are global runtime protections rather than
  election-specific policy choices
- confirm which terminal meanings are stable in `status_reason`
- confirm which detail is intentionally left in `status_detail`
- flag where election-stream suitability differs from current generic meaning

## Settled Current Behavior

At the end of the current branch, the intended `api_stream` operational
baseline is:

- transient upstream and polling failures may show up as reconnecting behavior
  in the frontend while the backend keeps the last good session snapshot
- retryable loader failures consume reconnect budget and become terminal only
  after that budget is exhausted
- runtime, refresh, fetch-size, and temp-storage limits remain global safety
  rails rather than election-specific policy
- idle polling exhaustion now persists as:
  - `status = completed`
  - `status_reason = idle_poll_budget_exhausted`
  - `status_detail = "Idle poll budget exhausted"`
- failed live runs intentionally keep a compact stable
  `status_reason = source_unreachable` while preserving loader/runtime detail in
  `status_detail`
- frontend live UX now distinguishes:
  - reconnecting
  - retry budget exhausted
  - runtime safety stop
  - unsupported source
  - completed live run with idle-budget warning

This note remains the detailed maintainer inventory. The canonical docs should
only carry the settled behavior above, not the full planning analysis.

## Quick Baseline Table

This table is the shortest summary of what step 1 currently tells us.

| Area | Current behavior | Evidence level | Election-stream note |
| --- | --- | --- | --- |
| reconnect retries | retryable failures consume reconnect budget and eventually fail terminally | explicitly tested | baseline is good; tolerance likely needs tuning later |
| idle budgets | idle exhaustion stops cleanly and currently persists as `completed` with `status_reason=idle_poll_budget_exhausted` | explicitly tested | biggest likely mismatch for polling-station monitoring |
| runtime budgets | session runtime and refresh counts are bounded by hard safety limits | explicitly tested | likely need longer defaults for civic all-day runs |
| byte/storage limits | fetch size and temp storage are bounded by terminal safety limits | explicitly tested | meaning is acceptable; tuning may change later |
| upstream HTTP/network failures | timeout, `URLError`, and selected HTTP statuses are retryable; others are terminal | partly tested, partly code-derived | current classification is a reasonable baseline |
| terminal status mapping | failed `api_stream` runs currently collapse into `source_unreachable` with detail preserved separately | explicitly tested for key outcomes, broader mapping is code-derived | stable baseline now; richer distinction may be needed later |

## Current Behavior Summary

### Reconnect retries

Current behavior:

- playlist fetch retries happen inside `HttpHlsApiStreamLoader._fetch_playlist_text_with_retries(...)`
- only `retryable_failure` values consume reconnect budget
- reconnect backoff uses `API_STREAM_RECONNECT_BACKOFF_SEC`
- exhausting the reconnect budget becomes a terminal loader failure:
  - `api_stream reconnect budget exhausted: ...`
- reconnect telemetry is tracked:
  - `reconnect_attempt_count`
  - `reconnect_budget_exhaustion_count`
  - `terminal_failure_reason`
- replayed chunks are skipped across reconnect and restart using persisted
  `api_stream_seen_chunks.jsonl`

Current classification source:

- `_classify_api_stream_fetch_exception(...)`
- HTTP `408`, `429`, `500`, `502`, `503`, `504` are retryable
- `TimeoutError` is retryable
- `URLError` is retryable
- other HTTP failures are terminal

Evidence level:

- explicitly tested for repeated `503` and timeout exhaustion cases
- partly code-derived for the full HTTP status classification boundary

Current test evidence:

- reconnect resumes after outage when playlist window moves
- replayed segments are skipped after reconnect
- repeated `503` failures exhaust reconnect budget terminally
- repeated timeout failures exhaust reconnect budget terminally
- explicit cancel during reconnect backoff stops cleanly

Election-stream suitability note:

- this is directionally good for Bulgarian polling monitoring streams because
  municipal and polling-station networks can be unstable and brief outages
  should not immediately kill monitoring
- the current retry set is probably reasonable as a baseline
- the likely future policy question is not classification first, but tolerance:
  current reconnect budgets may be too small for long-running civic streams

### Idle budgets

Current behavior:

- when no new segments appear and no `ENDLIST` is seen, idle polls are counted
- once `max_idle_playlist_polls` is reached, the loader stops cleanly with:
  - `self._stop_reason = "idle_poll_budget_exhausted"`
- this path currently results in a completed session outcome at runner level
- session progress currently persists:
  - `status = "completed"`
  - `status_reason = "idle_poll_budget_exhausted"`
  - `status_detail = "Idle poll budget exhausted"`

Current test evidence:

- `test_run_local_session_http_hls_api_stream_stops_cleanly_after_idle_poll_budget(...)`

Evidence level:

- explicitly tested

Election-stream suitability note:

- this is the most important currently questionable behavior for election
  monitoring
- a polling-station feed going idle all day is often more like:
  - interrupted
  - unavailable
  - degraded
  than a true successful completion
- keeping this as `completed` may be too optimistic for civic monitoring, even
  though it is internally consistent today
- this should be flagged as a likely future policy change candidate

### Runtime budgets

Current behavior:

- loader-level session runtime is capped by
  `API_STREAM_MAX_SESSION_RUNTIME_SEC`
- if exceeded, loader raises terminal failure:
  - `api_stream session runtime exceeded max duration`
- playlist refresh count is separately capped by
  `API_STREAM_MAX_PLAYLIST_REFRESHES`
- if exceeded, loader raises terminal failure:
  - `api_stream playlist refresh limit exceeded`

Current telemetry:

- terminal failure reason records the exact loader-side cause

Current test evidence:

- runtime limit enforcement test
- playlist refresh limit enforcement test

Evidence level:

- explicitly tested

Election-stream suitability note:

- these limits are useful as safety rails
- but default values suitable for ordinary live HLS testing may not be suitable
  for all-day election monitoring
- election deployments likely need:
  - longer session runtime budgets
  - clearer distinction between "safety stop" and "source disappeared"

### Byte and storage limits

Current behavior:

- upstream responses are read incrementally through
  `_read_api_stream_response_bytes(...)`
- fetch size is capped by `API_STREAM_MAX_FETCH_BYTES`
- if exceeded, the loader raises terminal failure:
  - `api_stream fetch exceeded max byte budget`
- temp media materialization is capped by `API_STREAM_TEMP_MAX_BYTES`
- if exceeded, the loader raises terminal failure:
  - `api_stream temp storage exceeded max byte budget`

Current test evidence:

- temp storage budget enforcement test
- max fetch byte budget enforcement test

Evidence level:

- explicitly tested

Election-stream suitability note:

- these protections are still valuable for election monitoring
- they protect the operator machine from runaway upstream behavior
- however, election streams are long-lived, so the defaults may need to be
  larger or paired with stronger rolling cleanup assumptions
- the current semantics are likely acceptable; the future question is tuning,
  not meaning

### Upstream HTTP and network failures

Current behavior:

- timeouts become retryable failures
- `URLError` becomes retryable failure
- HTTP `408`, `429`, `500`, `502`, `503`, `504` become retryable failures
- other HTTP failures become terminal failures
- malformed playlist refreshes can be treated as temporarily malformed and
  retryable during live refresh
- temporary segment failures are downgraded to `temporary_failure` and skipped
  so later segments can continue

Current test evidence:

- temporary segment outage is skipped while later segments continue
- repeated timeout failures exhaust reconnect budget
- repeated `503` failures exhaust reconnect budget

Evidence level:

- explicitly tested for the major transient failure paths above
- partly code-derived for the complete HTTP status and malformed-playlist
  classification boundary

Election-stream suitability note:

- this split is a good starting shape for polling-stream monitoring
- it favors continuity during noisy upstream conditions
- it still fails clearly for likely-invalid or non-recoverable provider states
- future refinement may be needed around election-specific provider quirks, but
  the current classification boundary is reasonable

### Terminal `status_reason` and `status_detail`

Current behavior at runner level:

- cancelled sessions map to:
  - `status_reason = "cancel_requested"`
  - `status_detail` varies by exact cancel timing
- failed `api_stream` sessions currently map to:
  - `status_reason = "source_unreachable"`
  - `status_detail = terminal_failure_reason` or error text
- validation failures map to:
  - `status_reason = "validation_failed"`
- completed sessions map to:
  - `status_reason = "completed"`
  - optional detail such as humanized stop reason

Important current nuance:

- multiple distinct loader safety failures currently collapse into the same
  persisted `api_stream` failure reason:
  - `source_unreachable`
- the specific cause remains only in `status_detail`, for example:
  - reconnect budget exhausted
  - runtime exceeded
  - refresh limit exceeded
  - fetch/storage budget failure

Current test evidence:

- reconnect-budget exhaustion persists:
  - `status = failed`
  - `status_reason = source_unreachable`
  - `status_detail` mentioning reconnect budget exhaustion
- idle poll exhaustion persists:
  - `status = completed`
  - `status_reason = idle_poll_budget_exhausted`
  - `status_detail = Idle poll budget exhausted`
- cancel-after-iteration persists:
  - `status_reason = cancel_requested`
  - detailed cancel timing note

Evidence level:

- explicitly tested for failed, completed-idle, and cancel terminal outcomes
- partly code-derived for the full runner mapping matrix in
  `_build_terminal_progress_status(...)`

Election-stream suitability note:

- the current small stable reason vocabulary is good for cross-layer
  consistency
- but for election monitoring, `source_unreachable` may be too broad if you
  later want to distinguish:
  - unstable but retrying
  - safety stop
  - feed interrupted
  - provider ended normally
- for now, this is acceptable as a stable baseline
- later policy work may decide whether election monitoring needs:
  - a richer degraded-state concept
  - a different idle-stop outcome
  - or more specific stable failure reasons

## Current Gaps And Open Questions

These are not changes yet. They are inventory findings that likely matter for
 future election-stream policy.

### 1. Idle exhaustion semantics

Current behavior:

- clean `completed` outcome

Why it matters:

- a polling feed that silently stops publishing new segments may not be a
  successful completion in operator terms

### 2. Runtime and refresh defaults for long-running civic streams

Current behavior:

- strong safety budgets exist

Why it matters:

- election monitoring may run for many hours and need different defaults than
  ordinary live-stream experiments

### 3. Stable reason granularity

Current behavior:

- many terminal `api_stream` failures map to `source_unreachable`

Why it matters:

- this is simple and stable today
- future election operations may benefit from one additional layer of
  distinction without exploding the contract

## Suggested Next-Step Questions

These are the policy questions this inventory sets up for later work:

1. Should idle poll exhaustion remain `completed` for election monitoring?
2. Which safety budgets need different defaults for long-running polling feeds?
3. Is `source_unreachable` still sufficient as the main failed-stream reason,
   or does civic monitoring need one additional stable category?
4. Should the frontend eventually surface a distinct "interrupted feed"
   experience without overloading the core lifecycle vocabulary?

## Bottom Line

Current `api_stream` behavior is already fairly robust for generic unstable live
sources:

- retries are explicit
- reconnect exhaustion is explicit
- temp/storage/runtime safety rails are explicit
- cancel behavior is coherent
- terminal details are preserved

For Bulgarian election polling streams, the biggest likely mismatch is not raw
network failure handling. It is the meaning of:

- idle exhaustion
- very long runtime expectations
- and possibly whether a stopped-but-not-explicitly-ended feed should still
  look like `completed`

That makes this inventory a good foundation for later election-specific policy
work without changing current contracts prematurely.

## Baseline Use

For the current branch, treat this note as:

- the baseline map of current `api_stream` semantics
- the reference for what is already explicitly covered by tests
- the place to start before proposing election-specific policy changes in a
  later branch

Do not treat this note itself as a contract change. It is an inventory of
current truth plus election-stream suitability commentary.
