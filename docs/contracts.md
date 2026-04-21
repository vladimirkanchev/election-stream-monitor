# Contracts

This document defines the current shared contracts between the Python backend,
the Electron bridge, and the frontend.

The project is still in an advanced prototype stage, so these contracts are
kept intentionally compact.

The goal is:

- make important interfaces explicit
- reduce accidental contract drift
- prepare later `api_stream` and service/API evolution

Use this doc for stable payload and seam contracts.
Do not use it as the main architecture narrative or as the detailed explanation
of persisted session files; see [architecture.md](./architecture.md) and
[session-model.md](./session-model.md) for those.

## At a glance

This is the document to use when you need to know:

- what the frontend is allowed to send
- what the backend promises to return
- which fields should be treated as stable by tests, tools, and UI code

For code-level truth, the closest sources are:

- [`src/source_validation.py`](../src/source_validation.py)
- [`src/stream_loader.py`](../src/stream_loader.py)
- [`frontend/src/bridge/contract.ts`](../frontend/src/bridge/contract.ts)
- [`frontend/src/types.ts`](../frontend/src/types.ts)

## Current Source Of Truth

For the current project stage:

- backend session snapshot source of truth:
  - [`src/session_io.py`](../src/session_io.py)
  - [`src/session_models.py`](../src/session_models.py)
  - [`src/session_runner.py`](../src/session_runner.py)
- frontend bridge normalization source of truth:
  - [`frontend/src/bridge/contract.ts`](../frontend/src/bridge/contract.ts)
  - [`frontend/src/types.ts`](../frontend/src/types.ts)
- FastAPI request/response contract source of truth:
  - [`src/api/schemas.py`](../src/api/schemas.py)
  - [`src/api/routers/`](../src/api/routers)

## Do Not Drift These Together By Accident

When changing one of these, review the others too:

- [`src/api/schemas.py`](../src/api/schemas.py)
- [`frontend/src/bridge/contract.ts`](../frontend/src/bridge/contract.ts)
- [`frontend/src/types.ts`](../frontend/src/types.ts)
- [`docs/session-model.md`](./session-model.md)
- [`tests/test_api_boundary.py`](../tests/test_api_boundary.py)
- [`frontend/src/bridge/contract.test.ts`](../frontend/src/bridge/contract.test.ts)

## API Stream Source Contract v1

Purpose:

- define the current accepted shape for live remote inputs
- keep validation, bridge payloads, playback resolution, and live loading in sync

Current source shape:

```json
{
  "kind": "api_stream",
  "path": "https://example.com/live/playlist.m3u8",
  "access": "api_stream"
}
```

Current rules:

- `path` must be a non-empty URL
- only `http` and `https` are accepted
- only direct `.m3u8` and `.mp4` paths are accepted
- credentials in URLs are rejected
- local/private-network targets are rejected by default in local mode
- optional allowlisting may narrow accepted hosts further
- webpage URLs such as video platform pages are rejected early

The backend is the source of truth for this validation.

Trust-policy notes:

- local mode remains strict by default:
  - private and loopback hosts are rejected unless explicitly enabled
  - optional allowlists may narrow accepted public hosts further
- service mode is stricter:
  - an explicit host allowlist is required
  - private and loopback hosts remain rejected by default
  - only direct media manifests/files should be fetched remotely
  - webpage extraction, credentialed URLs, and arbitrary remote browsing are
    outside the allowed service-mode fetch boundary

This policy keeps future service deployments closer to a deliberate media-ingest
allowlist than to a general-purpose remote fetcher.

## API Stream Start-Session Contract v1

Purpose:

- define the current bridge payload shape for starting live sessions
- keep frontend request meaning stable while live loading evolves behind the seam

Current request shape:

```json
{
  "mode": "api_stream",
  "input_path": "https://example.com/live/playlist.m3u8",
  "selected_detectors": ["video_blur", "video_metrics"]
}
```

Current response shape from `start-session`:

```json
{
  "session_id": "session-20260405-abc123",
  "mode": "api_stream",
  "input_path": "https://example.com/live/playlist.m3u8",
  "selected_detectors": ["video_blur", "video_metrics"],
  "status": "pending"
}
```

Notes:

- this keeps live start-session semantics aligned with local modes
- remote URL validation happens before the detached session process is spawned
- runtime loader failures later surface through normal session status and
  snapshot reads, not through a separate live-only session model

## Why version them now

These contracts already exist in code and tests.

Naming them as `v1` does not mean they are frozen forever. It means changes to
them should be conscious rather than accidental.

## Detector Catalog v1

Purpose:

- describe detectors to the frontend
- drive detector selection UI
- communicate detector role and ownership

Current shape:

```json
{
  "id": "video_blur",
  "display_name": "Blur Check",
  "description": "Flags blurry video using rolling frame samples and normalized blur scoring.",
  "category": "quality",
  "origin": "built_in",
  "status": "optional",
  "default_rule_id": "video_blur.default_rule",
  "default_selected": false,
  "produces_alerts": true,
  "supported_modes": ["video_segments", "video_files", "api_stream"],
  "supported_suffixes": [".ts", ".mp4"]
}
```

Notes:

- `origin` describes ownership:
  - `built_in`
  - `user`
- `status` describes product role or maturity:
  - `core`
  - `optional`
  - `experimental`
- `default_rule_id` points to the bundled default alert policy for this detector
  when one exists

### Bundled default rule concept

The project keeps detector execution and alert policy as separate concepts.

At the same time, a detector can declare a `default_rule_id` so one installable
capability can still come with a sensible built-in rule.

This supports a future model where:

- a plugin may ship both a detector and a default rule
- the runtime still treats detectors and rules as separate contracts
- later project or user overrides can replace the bundled default rule without
  replacing the detector itself

## Session Snapshot v1

Purpose:

- give the frontend one read model for session state
- combine stable metadata, live progress, alerts, and results

Current shape:

```json
{
  "session": {
    "session_id": "session-20260402-abc123",
    "mode": "video_segments",
    "input_path": "/data/streams/segments",
    "selected_detectors": ["video_blur"],
    "status": "running"
  },
  "progress": {
    "session_id": "session-20260402-abc123",
    "status": "running",
    "processed_count": 12,
    "total_count": 42,
    "current_item": "segment_0012.ts",
    "latest_result_detector": "video_blur",
    "latest_result_detectors": ["video_metrics", "video_blur"],
    "alert_count": 2,
    "last_updated_utc": "2026-04-02 12:34:56"
  },
  "alerts": [],
  "results": [],
  "latest_result": null
}
```

Notes:

- `session` may be `null` before a session exists
- `progress` may be `null` before initialization or after lookup failure
- `alerts` and `results` are append-oriented event views
- playback state is not part of this contract
- `api_stream` sessions use the same snapshot contract as local modes

### Route failures vs session state

The current project intentionally uses two different failure channels:

- immediate request failure
  - returned as a structured API error payload
- ongoing or terminal session lifecycle state
  - returned through the session snapshot

Important snapshot progress fields are:

- `progress.status`
- `progress.status_reason`
- `progress.status_detail`

This keeps request-level problems distinct from the state of an already-running
session.

### Lifecycle edge contract notes

The current lifecycle hardening makes these edge rules explicit:

- terminal session reads remain successful snapshot reads
  - `completed`, `failed`, and `cancelled` states are returned through the
    normal session snapshot contract
- invalid lifecycle actions fail at the request boundary
  - for example, `cancel-session` against a terminal session returns a
    structured route failure rather than a synthetic success
- missing-session route failures stay distinct from snapshot normalization
  - backend persistence helpers may degrade missing files to a stable empty
    shape internally
  - API and bridge layers turn missing-session route lookups into structured
    failures such as `session_not_found`
- frontend bridge normalization preserves structured lifecycle failures
  - typed bridge errors keep `backend_error_code`, `status_reason`, and
    `status_detail` instead of flattening them into generic failures
- cancel success still allows `null`
  - a successful cancel request may return either an updated `SessionSummary`
    or `null` when no immediate summary payload is available

Frontend lifecycle behavior now also depends on two intentionally stable
consumer rules:

- polling reads are tolerant of transient failures and keep the last good
  session state in the UI instead of immediately clearing it
- duplicate in-flight cancel requests are suppressed so the frontend keeps one
  active stop request rather than fanning out repeated cancels
- once the UI has already settled into terminal `completed`, the app suppresses
  a late extra stop request instead of issuing a cancel action that can no
  longer change the session outcome

## Alert Event v1

Purpose:

- represent one alert raised by the backend
- support frontend list rendering and playback-aligned reveal

Current shape:

```json
{
  "session_id": "session-20260402-abc123",
  "timestamp_utc": "2026-04-02 12:35:02",
  "detector_id": "video_blur",
  "title": "Blur warning",
  "message": "segment_0206.ts entered a blurry state.",
  "severity": "warning",
  "source_name": "segment_0206.ts",
  "window_index": 206,
  "window_start_sec": 206.0
}
```

Notes:

- `timestamp_utc` is backend detection time, not playback display time
- `source_name` is the detector-side item identity
- `window_index` and `window_start_sec` are optional but important for temporal
  playback alignment

### Current built-in rule metadata preparation

The rule layer now also has lightweight internal metadata with stable ids such
as:

- `video_metrics.default_rule`
- `video_blur.default_rule`

Current rule metadata includes:

- `id`
- `detector_id`
- `display_name`
- `description`
- `origin`
- `status`

This is preparation for future user-extensible rule registration. It is not yet
a full rule-plugin loading system.

## Plugin Security Rules v1

Purpose:

- make future plugin loading safer before dynamic loading exists
- keep built-in and user-owned extension bundles distinct
- prevent silent detector or rule id takeover

Current intended manifest rules:

- every plugin manifest must declare:
  - `plugin_id`
  - `display_name`
  - `origin`
  - `detector_ids`
  - `rule_ids`
  - `enabled_by_default`
- `origin` must be explicit:
  - `built_in`
  - `user`
- detector ids and rule ids must be non-empty strings
- detector ids and rule ids must not contain duplicates within one manifest
- detector ids and rule ids must not conflict with existing built-in
  registrations
- user plugins are disabled by default until explicitly enabled by the runtime
  or operator

Why this matters now:

- manifest validation becomes a correctness and security boundary before plugin
  loading is introduced
- explicit ownership helps the runtime distinguish shipped capabilities from
  later user- or agent-authored extensions

## Notes For Agents

- If you change a bridge payload, update this file and the corresponding tests.
- If you change validation rules, update this file and
  [`src/source_validation.py`](../src/source_validation.py).
- If a field is described here as stable, do not silently rename or repurpose
  it inside frontend or backend code.
- duplicate-id rejection prevents silent override of built-in detectors or
  rules
- disabled-by-default user plugins keeps future extension trust explicit

## Playback Source Resolution v1

Purpose:

- define what the frontend can ask the bridge to resolve for playback
- keep playback-source behavior explicit across local and future remote sources

Request shape:

```json
{
  "source": {
    "kind": "video_segments",
    "path": "/data/streams/segments",
    "access": "local_path"
  },
  "currentItem": "segment_0012.ts"
}
```

Response shape:

```json
{
  "source": "local-media://media/repo/data/streams/segments/index.m3u8"
}
```

Current behavior:

- local files and playlists resolve to `local-media://...`
- already-remote sources may later resolve to direct `https://...`
- `currentItem` is optional context for playback resolution

### API Stream playback behavior

For `api_stream`, playback resolution currently returns the validated original
remote URL directly:

```json
{
  "source": "https://example.com/live/playlist.m3u8"
}
```

This keeps playback transport simple while live monitoring is still
file-backed-and-polled elsewhere.

Important architectural rule:

- playback resolution is intentionally separate from live monitoring ingestion
- the player only needs a playable source URL
- stream loading, reconnect behavior, and chunk iteration belong to the
  backend loader seam

Why this matters:

- playback can stay simple while monitoring evolves
- player issues do not need to share logic with loader retry/failure behavior
- `api_stream` can feel like a new source mode, not a second architecture

## API Stream Session Snapshot Semantics v1

Purpose:

- keep live-session reads compatible with the existing session snapshot model
- avoid introducing a second frontend state model for remote monitoring

Current snapshot semantics for `api_stream`:

- `session.mode` is `api_stream`
- `session.input_path` keeps the validated remote URL
- `progress.current_item` is the latest live slice/chunk identity
- `progress.processed_count` is the number of slices processed so far
- `progress.total_count` is the loader-provided bounded slice count in current
  tests and placeholder flows
- `alerts`, `results`, and `latest_result` keep the same meaning as local modes

Important current limitation:

- the project does not implement an open-ended live session model yet
- the placeholder loader and current tests use bounded, deterministic slice
  sets so the existing snapshot contract stays stable

Open-ended live default for the upcoming real loader:

- while a live session is still `running`, `progress.total_count` means the
  latest known number of collected chunks so far
- `progress.total_count` stays a non-null integer in the current snapshot
  model
- before the first chunk arrives, `progress.total_count` may be `0`
- the frontend should treat `api_stream` progress as live activity, not as a
  stable completion percentage, until the session reaches a terminal status
- the current UI expectation is live wording such as "Live, N chunks
  analyzed", with optional debug-only "N analyzed, M discovered" detail rather
  than `N/M` batch-style progress

## API Stream Loader Seam v1

Purpose:

- define one backend component responsible for future live loading
- keep stream connection and chunk iteration separate from session orchestration

Current seam responsibilities:

- connect to one validated live source
- fetch and materialize chunk/segment work units
- yield normalized `AnalysisSlice` values
- close and release loader resources

Current non-responsibilities:

- session status transitions
- persistence
- detector execution
- alert rule evaluation

Why this separation matters:

- `session_runner` can stay focused on lifecycle and persistence
- `processor` can stay focused on running detectors and collecting alerts
- `alert_rules` can stay focused on policy, not transport behavior
- tests can use deterministic fake loaders today
- the first bounded HTTP/HLS loader now fits behind the same seam without
  changing detector or session snapshot contracts
- playback resolution can remain a simple remote-URL passthrough while the
  loader grows more sophisticated

## API Stream HTTP/HLS Loader Contract v1

Purpose:

- define the exact return shape expected from the first real remote loader
- keep future HTTP/HLS implementation work narrow, deterministic, and testable

Current decided contract:

- the loader returns normalized `AnalysisSlice` values only
- every yielded slice is backed by one session-scoped temp media file on disk
- the first real loader accepts:
  - direct media playlist URLs
  - master playlist URLs
- the default polling cadence is `API_STREAM_POLL_INTERVAL_SEC`

Current master-playlist policy:

- if the validated source resolves to a master playlist, the first version of
  the loader chooses the first listed variant
- it does not yet apply bandwidth, resolution, or codec heuristics

Why this matters:

- the first implementation stays deterministic and easy to test
- loader behavior becomes explicit before network code exists
- later improvements can change one named policy instead of silently changing
  runtime behavior

Current implementation note:

- the first concrete loader now supports bounded HTTP/HLS flows
- it fetches the initial playlist, resolves master playlists to the first
  listed variant, polls media playlists for new segments, downloads those
  segments to temp files, and yields normalized analysis slices
- master-playlist selection intentionally stays on the first listed variant
  even if later variants advertise higher bandwidth or resolution
  - this keeps first-run behavior deterministic on real feeds and avoids
    hidden quality-selection heuristics in v1
- open-ended live monitoring is still constrained by the current
  slice-collection session runner
- sliding playlist windows are allowed
  - older segments may disappear from later playlist refreshes without causing
    failures
  - replayed surviving segments are skipped by de-duplication
  - if the live window has advanced past some not-yet-seen segments, the
    loader resumes from the next visible segment instead of trying to recreate
    missing history
- target-duration drift is tolerated
  - the loader treats the configured poll interval as an upper bound
  - if the playlist later advertises a shorter target duration, the next poll
    uses that shorter cadence
- every playlist and segment fetch is bounded by `API_STREAM_FETCH_TIMEOUT_SEC`
  and `API_STREAM_MAX_FETCH_BYTES`
- session-scoped temp media is bounded by `API_STREAM_TEMP_MAX_BYTES`
  before a newly downloaded segment is written to disk

## API Stream Local HTTP Integration Harness v1

Purpose:

- define the smallest realistic integration-test shape for the future real
  HTTP/HLS loader
- keep real-loader tests local, deterministic, and controllable

Current planned harness:

- one small local HTTP test server
- serves HLS fixtures from the checked-in fixture tree
- entrypoint playlist is `index.m3u8`
- serves both:
  - playlist responses
  - segment responses

Current fixture-serving strategy:

- use checked-in HLS fixture folders as static source material
- serve one playlist and its referenced `.ts` files through local HTTP instead
  of direct filesystem loading
- keep fixture content deterministic so loader behavior, reconnect handling,
  and slice identity can be asserted cleanly

Current controllable failure plan:

- scripted timeout
- scripted disconnect
- scripted `503` response
- scripted playlist replay of already seen segments

Why this matters:

- the first real-loader integration tests can stay offline and reproducible
- failure/reconnect behavior can be exercised without unstable external
  dependencies
- the test harness mirrors real transport shape while keeping fixture control
  local

Current implementation note:

- the test suite now includes a small local HTTP harness for:
  - direct media playlists
  - master-playlist selection
  - low-quality but still playable first-variant selection
  - malformed master-playlist entries that still expose a later valid variant
  - playlist refresh with newly discovered segments
  - longer multi-refresh local HLS runs
  - temporary segment outage handling
  - retryable playlist failures and reconnect-budget exhaustion
  - duplicate segment replay during playlist refresh
  - sliding-window playlist histories
  - repeated refreshes with no new segments
  - target-duration drift
  - media playlists missing optional tags such as `#EXT-X-TARGETDURATION`

Frontend transport note for the current stage:

- the real loader does not require a transport upgrade to exist
- current frontend polling is still sufficient for bounded live-session
  snapshots
- SSE, WebSocket, or FastAPI-style transport upgrades are optional later
  improvements, not prerequisites for the first real loader

## API Stream Failure Semantics v1

Purpose:

- define the intended failure contract for future `api_stream` support before
  the runtime is implemented
- keep live-stream behavior explicit instead of letting retry/reconnect rules
  leak into unrelated layers

Current intended failure classes:

- `temporary failure`
  - one chunk/window cannot be fetched, decoded, or analyzed
  - the session remains `running`
  - no result or alert is emitted for that failed live slice
  - failure is logged with session and item context
- `retryable failure`
  - the upstream stream or playlist refresh fails in a way that may recover
  - the session remains `running` while reconnect attempts are still allowed
  - reconnect attempts should be bounded and visible in logs
- `terminal failure`
  - the source is invalid, permanently unavailable, or exceeds the reconnect
    budget
  - the session transitions to `failed`
  - final persisted progress must also be `failed`

Reconnect behavior:

- reconnect should only apply to `retryable failure`
- reconnect should use bounded retries with backoff
- reconnect should not duplicate already persisted results or alerts
- once reconnect succeeds, processing resumes from the next not-yet-persisted
  live slice/window
- once reconnect budget is exhausted, the failure becomes `terminal`

Current HLS parsing resilience:

- incomplete live refreshes such as a dangling `#EXTINF` without a following
  segment URI are tolerated and treated as "no new work yet"
- temporarily malformed live refreshes, such as a non-HLS body returned during
  a transient upstream glitch, are treated as retryable live noise instead of
  immediate terminal failure
- the first runtime also tolerates one common master-playlist quirk by
  resolving nested master playlists until it reaches a media playlist, up to a
  small bounded depth
- malformed numeric playlist tags such as invalid `MEDIA-SEQUENCE`,
  `TARGETDURATION`, or `EXTINF` values still fail clearly instead of being
  guessed

Live playlist idle behavior:

- for non-`#EXT-X-ENDLIST` playlists, "keep waiting" currently means:
  - continue polling while consecutive refreshes with no newly discovered
    segments stay below `API_STREAM_MAX_IDLE_PLAYLIST_POLLS`
  - stop the current bounded live run cleanly once that idle poll budget is
    exhausted
- `#EXT-X-ENDLIST` remains an explicit stop signal and completes the bounded
  live run immediately once the visible playlist segments are exhausted,
  without falling back to idle polling
- an explicit session cancel remains an immediate stop signal owned by the
  session runner; the runner stops after the in-flight chunk finishes and
  persists a `cancelled` snapshot
- the concrete HTTP/HLS loader also checks for cancel safely during:
  - idle polling waits
  - reconnect backoff waits
  - segment download/read loops
  - the gap between download completion and temp-file materialization
- this is intentionally a local-first bounded-live policy, not a claim of
  permanent endless monitoring yet

Current status expectations:

- `temporary failure`:
  - session status remains `running`
  - progress status remains `running`
- `retryable failure`:
  - session status remains `running`
  - progress status remains `running`
  - reconnect budget decreases
- `terminal failure`:
  - session status becomes `failed`
  - progress status becomes `failed`

Current reconnect budget:

- the runtime policy exposes `max_reconnect_attempts`
- this is the upper bound for retryable reconnect attempts before the runtime
  must treat the problem as terminal
- duplicate persisted results and duplicate alerts are not allowed after
  reconnect

What is intentionally not introduced yet:

- no extra frontend session status beyond the current `running` / `failed`
  model
- no SSE/WebSocket-specific semantics
- no plugin-specific retry policies

This contract is intentionally lightweight for the current stage, but it gives
`api_stream` a clear failure model before the implementation work begins.

## API Stream Reconnect De-Dup Policy v1

Purpose:

- define where replay protection lives before a real upstream reconnect loop
  exists
- prevent duplicate persisted results or alerts after chunk replay

Current decided policy:

- reconnect de-dup uses both loader/runtime memory and persisted session state
- replayed chunks are skipped before they reach persistence
- the reconnect-safe identity key remains:
  - `source_group`
  - `window_index`
  - `source_name`

Why this matters:

- the first implementation stays simple and local-first
- duplicate prevention is still explicit and testable
- later persistent de-dup can be added as an intentional upgrade instead of
  an accidental coupling to session storage

## API Stream Loader Exception Policy v1

Purpose:

- define exactly which live-loader failures the loader seam absorbs and which
  ones become session-fatal
- keep reconnect ownership explicit before the real HTTP/HLS loader exists

Current decided policy:

- the loader seam owns reconnect attempts
- the session runner does not implement its own reconnect loop for
  `api_stream`
- `temporary_failure` is skipped inside the loader seam and the session keeps
  running
- `retryable_failure` is handled inside the loader seam while reconnect budget
  remains
- `terminal_failure` escapes the loader seam and should fail the session
  immediately

Current runner behavior:

- if a terminal loader error happens before live slice discovery completes, the
  runner persists a failed session snapshot and re-raises the error
- if the loader seam skips temporary or retryable failures, the runner sees
  only valid `AnalysisSlice` values and keeps existing result/alert semantics

Current implementation note:

- the concrete HTTP/HLS loader retries playlist fetches internally using the
  configured reconnect budget and backoff
- accepted live-slice identity keys are persisted session-side so a replayed
  segment can be skipped even after reconnect or repeated loader startup
- if reconnect or playlist sliding means some missed segments are no longer in
  the playlist window, the loader resumes from the next visible segment and
  logs the gap instead of failing the whole run
- segment-download network failures are downgraded to per-segment temporary
  failures so one bad chunk can be skipped without failing the whole bounded
  run

Why this matters:

- reconnect logic stays in one place
- the runner keeps one clear responsibility: lifecycle and persistence
- failed live startup attempts become visible to the frontend as real failed
  sessions instead of disappearing before persistence

## API Stream Observability v1

Purpose:

- make live-ingestion decisions inspectable before full remote loading exists
- reduce silent failures during future retry/reconnect work

Current logging expectations at the loader seam:

- log when live-slice collection starts
- log selected master-playlist variant when one is chosen
- log accepted slices with:
  - `source_group`
  - `current_item`
  - `chunk_index`
- log playlist refresh stats with:
  - `playlist_refresh_count`
  - `new_segment_count`
  - `skipped_replay_count`
- log temporary failures with:
  - redacted source URL
  - current item when known
  - failure kind
- log retryable failures with:
  - reconnect attempt
  - reconnect budget
- log reconnect-budget exhaustion as an error
- log invalid/replayed/malformed slices that are skipped before persistence
- log live-window advancement when some missed segments are no longer visible
  after reconnect or playlist sliding

Why this matters:

- future `api_stream` problems will usually be ingestion and retry problems,
  not detector bugs
- these logs make it easier to debug live behavior without changing session
  snapshot semantics
- resume-gap logs make reconnect edge cases easier to understand when a real
  live playlist has already moved on

## API Stream Operator Messages v1

Purpose:

- define frontend-safe language for common live-stream failure states
- keep operator-facing messaging stable before richer live UI states exist

Current intended messages:

- `stream unavailable`
  - "The selected live stream is unavailable right now."
- `reconnecting`
  - "The live stream is temporarily unavailable. Monitoring is reconnecting."
- `reconnect budget exhausted`
  - "The live stream could not be reconnected. Monitoring stopped after the retry budget was exhausted."
- `unsupported source`
  - "The selected live stream source is not supported by the current monitoring runtime."

Notes:

- the current frontend maps these from bridge-safe error details
- this keeps the UI understandable without exposing low-level transport
  language directly to operators

## API Stream Temp-File Lifecycle v1

Purpose:

- define where fetched live chunks should live before HTTP/HLS downloading is
  implemented
- make cleanup, failure handling, and disk guardrails explicit

Current decided policy:

- downloaded chunks live under:
  - `API_STREAM_TEMP_ROOT / <session_id>`
- temp media is session-scoped so one live session can be cleaned up without
  touching another
- temp media is deleted on:
  - successful completion
  - explicit cancel
  - terminal failure
- the first implementation should respect a shared disk guardrail exposed as
  `API_STREAM_TEMP_MAX_BYTES`

Why this matters:

- temp media ownership is clear before the loader exists
- cleanup behavior does not have to be invented during failure handling
- disk usage gets one named guardrail early instead of growing accidentally

## API Stream Trust Policy v1

Purpose:

- define acceptable remote-source shapes before `api_stream` is implemented
- prevent local-first development from expanding into arbitrary remote or
  internal-network probing
- name the reconnect and fetch safety limits before transport code exists

Current allowlist rules:

- allowed URL schemes:
  - `https`
  - `http`
- URLs must include a host
- URLs must not include embedded credentials
- obvious local-network targets are rejected by default in local mode:
  - `localhost`
  - `localhost.localdomain`
  - literal loopback or private IP addresses

## API Stream Slice Identity Rules v1

Purpose:

- make live chunks addressable across progress updates, alerts, and reconnects
- prevent duplicate persistence after upstream replay or reconnect
- keep rolling rule state tied to one stable live source

Current rules:

- `source_group` must stay stable for the whole live source
  - today the default stable identity is the validated source URL
- `window_index` must be monotonic
  - each next live slice must have a strictly larger index than the previous one
- `current_item` must be readable and stable
  - if the upstream loader has no better name yet, a fallback such as
    `live-chunk-000007` is used
- persistence should treat the tuple below as the reconnect-safe identity key:
  - `source_group`
  - `window_index`
  - `source_name`

Why this matters:

- stable `source_group` keeps rolling detector/rule state attached to one live
  stream instead of leaking across sources
- monotonic chunk indexes make progress and replay handling predictable
- readable current-item names improve debugging and UI progress clarity
- a stable identity key is the foundation for "no duplicate results/alerts
  after reconnect"
- optional `API_STREAM_ALLOWED_HOSTS` can restrict allowed domains further

Current intended runtime limits:

- `API_STREAM_MAX_RECONNECT_ATTEMPTS`
  - maximum reconnect attempts before the failure becomes terminal
- `API_STREAM_RECONNECT_BACKOFF_SEC`
  - backoff between retryable reconnect attempts
- `API_STREAM_FETCH_TIMEOUT_SEC`
  - upper bound for one remote fetch or refresh operation
- `API_STREAM_MAX_FETCH_BYTES`
  - upper bound for one fetched playlist or media chunk payload
- `API_STREAM_TEMP_MAX_BYTES`
  - upper bound for temp media materialized by live loading

Implementation note:

- host validation intentionally does not perform DNS resolution during input
  validation
- this keeps validation deterministic and avoids turning validation itself into
  a network probe

## API Stream Flow Example v1

Purpose:

- show the intended end-to-end live flow without introducing a second
  monitoring architecture

Current planned flow:

1. frontend starts an `api_stream` session with a validated remote URL
2. session runner creates the session and initial pending progress
3. loader connects to the live source and yields normalized `AnalysisSlice`
   values
4. processor runs detectors on each slice
5. alert rules evaluate detector output
6. results, alerts, and progress are persisted in the same snapshot model as
   local sources
7. frontend polls the same session snapshot contract used by local modes

Why this matters:

- `api_stream` stays a new source mode, not a second architecture
- detectors, rules, persistence, and frontend snapshot reading keep the same
  meaning across local and remote inputs

## Electron Bridge Contract v1

Purpose:

- define the frontend-facing operations exposed through `window.electionBridge`
- keep Electron/CLI transport details separate from the meaning of the bridge API
- make later transport replacement easier without changing frontend behavior

Transport envelope shape:

```json
{
  "ok": true,
  "data": {}
}
```

or

```json
{
  "ok": false,
  "error": {
    "code": "SESSION_READ_FAILED",
    "message": "Session read request failed",
    "details": "No such session"
  }
}
```

Current bridge error codes:

- `DETECTOR_CATALOG_FAILED`
- `SESSION_START_FAILED`
- `SESSION_READ_FAILED`
- `SESSION_CANCEL_FAILED`
- `PLAYBACK_SOURCE_RESOLUTION_FAILED`
- `INVALID_BRIDGE_RESPONSE`

Current operations:

### `listDetectors`

Request:

```json
{
  "mode": "video_segments"
}
```

Response:

```json
[
  {
    "id": "video_blur",
    "display_name": "Blur Check",
    "description": "Flags blurry video using rolling frame samples and normalized blur scoring.",
    "category": "quality",
    "origin": "built_in",
    "status": "optional",
    "default_rule_id": "video_blur.default_rule",
    "default_selected": false,
    "produces_alerts": true,
    "supported_modes": ["video_segments", "video_files", "api_stream"],
    "supported_suffixes": [".ts", ".mp4"]
  }
]
```

Current bridge normalization:

- malformed detector entries are filtered out
- invalid detector lists normalize to `[]`
- explicit transport failures are raised as typed bridge errors

### `startSession`

Request:

```json
{
  "source": {
    "kind": "video_segments",
    "path": "/data/streams/segments",
    "access": "local_path"
  },
  "selectedDetectors": ["video_blur"]
}
```

Response:

```json
{
  "session_id": "session-20260402-abc123",
  "mode": "video_segments",
  "input_path": "/data/streams/segments",
  "selected_detectors": ["video_blur"],
  "status": "running"
}
```

Current bridge normalization:

- malformed responses are rejected as bridge errors
- hooks no longer validate `startSession` payloads themselves
- explicit transport failures are raised with `SESSION_START_FAILED`

### `readSession`

Request:

```json
{
  "sessionId": "session-20260402-abc123"
}
```

Response:

```json
{
  "session": {
    "session_id": "session-20260402-abc123",
    "mode": "video_segments",
    "input_path": "/data/streams/segments",
    "selected_detectors": ["video_blur"],
    "status": "running"
  },
  "progress": {
    "session_id": "session-20260402-abc123",
    "status": "running",
    "processed_count": 12,
    "total_count": 42,
    "current_item": "segment_0012.ts",
    "latest_result_detector": "video_blur",
    "latest_result_detectors": ["video_metrics", "video_blur"],
    "alert_count": 2,
    "last_updated_utc": "2026-04-02 12:34:56"
  },
  "alerts": [],
  "results": [],
  "latest_result": null
}
```

Current bridge normalization:

- invalid `session` or `progress` payloads become `null`
- missing or malformed `alerts` / `results` become `[]`
- malformed top-level payloads become the stable empty snapshot shape
- explicit transport failures are raised with `SESSION_READ_FAILED`

### `cancelSession`

Request:

```json
{
  "sessionId": "session-20260402-abc123"
}
```

Response:

```json
{
  "session_id": "session-20260402-abc123",
  "mode": "video_segments",
  "input_path": "/data/streams/segments",
  "selected_detectors": ["video_blur"],
  "status": "cancelling"
}
```

Current bridge normalization:

- `null` remains a valid `cancelSession` result
- malformed non-null responses are rejected as bridge errors
- explicit transport failures are raised with `SESSION_CANCEL_FAILED`

### `resolvePlaybackSource`

Request:

```json
{
  "source": {
    "kind": "api_stream",
    "path": "https://example.com/live/playlist.m3u8",
    "access": "api_stream"
  },
  "currentItem": null
}
```

Response:

```json
"https://example.com/live/playlist.m3u8"
```

Current bridge normalization:

- non-string values normalize to `null`
- blank strings normalize to `null`
- non-empty strings are trimmed before reaching the hooks
- explicit transport failures are raised with `PLAYBACK_SOURCE_RESOLUTION_FAILED`

## Current contract boundaries

These contracts are currently enforced by a mix of:

- Python dataclasses and typed dicts
- TypeScript interfaces
- bridge wiring
- integration and App-level tests

They are not yet full API schemas, and that is acceptable at the current stage.

## Logging Redaction Policy v1

Purpose:

- keep structured logs useful for debugging
- avoid leaking full source locations or future payload metadata unnecessarily

Current redaction rules:

- full source URLs should not be logged in structured context
  - keep only scheme + host + optional port
- full local paths should not be logged in structured context
  - keep only the basename
- payload-like detector or rule objects should be redacted in structured
  context if they are logged in the future

Why this matters:

- reduces accidental leakage of signed URLs, private filesystem locations, or
  future detector payload metadata
- preserves the debugging value of session id, source kind, detector id, and
  current item

## Expected next evolution

Most likely next steps:

- add explicit `api_stream` contract cases
- document reconnect and failure-state semantics
- keep these same contracts when introducing a future HTTP/FastAPI layer

That way the transport can change later without redefining the meaning of the
data.
