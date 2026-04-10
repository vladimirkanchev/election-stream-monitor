# Media fixtures

These files are permanent media fixtures for detector checks, end-to-end session tests,
and manual debugging.

Sources used:
- `data/streams/local/polling_station_233900044.mp4`
- `data/streams/segments/index.m3u8`

Included fixtures:
- `video_files/blur_trigger.mp4`
  - short blurred clip derived from the local mp4
  - useful for `video_blur`
- `video_files/black_trigger.mp4`
  - short clip with black frames added at the end
  - useful for `video_metrics`
- `video_segments/blur_trigger/index.m3u8`
  - short blurred HLS stream derived from the segment input
  - useful for `video_blur`
- `video_segments/black_trigger/index.m3u8`
  - short HLS stream with black frames added near the end
  - useful for `video_metrics`
- `video_segments/black_trigger_3_alerts/index.m3u8`
  - stronger HLS black-screen fixture
  - designed to produce 3 black detections and 3 alerts with the current rule
  - expected alerting segments are `segment_0002.ts`, `segment_0003.ts`, and `segment_0004.ts`

Longer real-source fixtures:
- `video_files/*_long.mp4`
  - around `9.8 sec`, extracted from different positions in
    `data/streams/local/polling_station_233900044.mp4`
  - include baseline, black-tail, blur-middle, mixed, and recovery/re-alert cases
- `video_segments/*_long/index.m3u8`
  - `10` real `.ts` segments copied from different positions in
    `data/streams/segments/`
  - some cases keep the copied segments as-is, others selectively replace a few
    segments with black or blurred versions to model fixed-rule scenarios
- malformed longer fixtures
  - `video_files/truncated_long.mp4`
  - `video_segments/missing_segment_long/index.m3u8`
  - these are meant for future failure-path and malformed-input tests

Catalog:
- `fixture_catalog.json`
  - lists the intent, expected content ranges, and source offsets/ranges for the
    longer fixtures
- `api_stream_expectations.json`
  - defines the current local `api_stream` validation set
  - records expected chunk count, alert count, and final status for the
    repeatable pre-real-stream checks
  - pairs with `scripts/api_stream_local_validation.py`

These fixtures are intentionally simple. They are meant to trigger detectors, not to be realistic long recordings.
