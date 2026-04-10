# Data Models

This document gives a compact view of the most important data shapes in the
project.

It is mainly here to help contributors and coding agents avoid guessing.

## Best use of this doc

Use this document as a compact field guide when you are:

- adding a detector
- extending an alert rule
- updating frontend rendering for results or alerts
- checking whether a field belongs to detector output, session progress, or
  playback-only state

## Analyzer result

Defined from the shared contract in:

- [`src/analyzer_contract.py`](../src/analyzer_contract.py)

Base fields every analyzer result should have:

- `analyzer`
- `source_type`
- `source_group`
- `source_name`
- `window_index`
- `window_start_sec`
- `window_duration_sec`
- `timestamp_utc`
- `processing_sec`

Then each detector adds its own fields.

Examples:

- black-screen video result
  - `black_detected`
  - `total_black_sec`
  - `longest_black_sec`
  - `black_ratio`
- blur result
  - `sample_count`
  - `blur_score`
  - `blur_detected`
  - `threshold_used`

## Detector catalog entry

This is what the frontend uses to show available detectors.

Important fields:

- `id`
- `display_name`
- `description`
- `category`
- `origin`
- `status`
- `default_rule_id`
- `default_selected`
- `produces_alerts`
- `supported_modes`
- `supported_suffixes`

## Session metadata

Defined in:

- [`src/session_models.py`](../src/session_models.py)

Fields:

- `session_id`
- `mode`
- `input_path`
- `selected_detectors`
- `status`

## Session progress

Fields:

- `session_id`
- `status`
- `processed_count`
- `total_count`
- `current_item`
- `latest_result_detector`
- `latest_result_detectors`
- `alert_count`
- `last_updated_utc`

Important note:

- `api_stream` uses the same progress shape as local modes
- `processed_count` is accepted-slice count, not raw upstream segment count
- `current_item` is the latest analyzed chunk/item label, not necessarily the
  currently visible playback item

## Result event

Fields:

- `session_id`
- `detector_id`
- `payload`

This is how one detector result is persisted for the frontend/session layer.

## Alert event

Fields:

- `session_id`
- `timestamp_utc`
- `detector_id`
- `title`
- `message`
- `severity`
- `source_name`
- `window_index`
- `window_start_sec`

This is what the frontend alert feed shows.

## Session snapshot

Frontend/backend snapshot shape:

- `session`
- `progress`
- `alerts`
- `results`
- `latest_result`

This is the main payload the frontend reads repeatedly while a run is active.

The snapshot is intentionally monitoring-focused:

- playback state does not live here
- playback alignment uses alert/result metadata plus frontend playback state

## Frontend setup/session/playback state

Useful frontend types live in:

- [`frontend/src/types.ts`](../frontend/src/types.ts)

Main groups:

- setup state
  - `MonitorSource`
  - selected detectors
- session state
  - `MonitoringSessionState`
  - `SessionSummary`
  - `SessionSnapshot`
- playback state
  - `PlaybackStatus`
  - resolved playback source

Important distinction:

- `MonitorSource`
  - what the user selected
- resolved playback source
  - what the renderer actually loads after bridge resolution/proxying
- session snapshot
  - what the backend knows about monitoring progress

## Plugin manifest preparation

The backend also now defines a lightweight plugin-manifest contract for future
loading and validation.

Important fields:

- `plugin_id`
- `display_name`
- `origin`
- `detector_ids`
- `rule_ids`
- `enabled_by_default`

## Why this matters

If you add a detector or alert rule, these are the shapes most likely to matter.

Good rule of thumb:

- detector result shape should stay flat
- alert shape should stay small and user-facing
- session shape should stay stable for the frontend
- plugin metadata should stay explicit about ownership and id boundaries

## Notes For Agents

- Prefer adding new fields to detector payloads over overloading existing ones.
- Do not mix playback-only concerns into persisted session models.
- If a new field is needed in the frontend, decide whether it belongs in:
  - detector result payload
  - alert event
  - session progress
  - or frontend-only playback state
