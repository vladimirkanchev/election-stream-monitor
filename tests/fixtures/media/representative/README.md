# Representative Media Fixtures

This folder contains the larger local representative-media corpus for
confidence work around election-stream scenarios. It complements the smaller
checked-in regression fixtures in `tests/fixtures/media/video_files` and
`tests/fixtures/media/video_segments`.

Use it for opt-in local validation, detector tuning, and pre-migration
confidence work. Do not turn the full corpus into default unit-test or
lightweight-CI input.

## Layout

```text
representative/
  README.md
  manifest.json             # fixture catalog for humans, tests, and AI coding agents
  expected_results.json     # intent-level detector expectations
  local_files/
    source/                 # clean source scenarios / negative baselines
    black_screen/           # full-frame black/dropout variants
    blur_low_quality/       # Gaussian blur / defocus variants
    compression_noise/      # compression and macroblocking variants
    low_resolution/         # temporary resolution downgrade variants
  local_hls/                # optional HLS conversions for selected MP4 cases
  external/                 # notes for local-only or non-checked-in sources
```

## Current Dataset

The current set has 6 source scenarios and 48 derived MP4 files:

- `empty_static`: quiet/static polling-room baseline with very low motion.
- `close_review`: close table/document review with people and papers near camera.
- `crowded_ballot`: crowded table scene with ballot/document handling and frequent motion.
- `wide_observer`: wide room view with persistent foreground observer/partial occlusion.
- `stable_docs`: stable document-handling table scene with normal activity.
- `messy_activity`: messier real-world activity with motion, occlusion, and natural blur.

Each source has controlled derived variants for black frames, Gaussian blur,
compression noise, and low resolution. Strong black-frame and strong blur
clips are useful for current detector confidence. Low-resolution and
compression clips are more useful today as quality-degradation and
false-positive guard cases.

The first local HLS baselines already exist in
`local_hls/stable_docs__source_baseline` and
`local_hls/messy_activity__source_baseline`. Use those first when adding
representative `video_segments` or local HTTP `api_stream` tests.

## Current Test Lanes

Use the representative-media lanes as a ladder, not as one big suite:

- `tests/test_representative_hls_test_support.py`
  - catalog and helper ownership
  - fixture resolution, route maps, and metadata consistency across catalogs
- `tests/test_e2e_local_session_representative_hls.py`
  - reviewed HLS intent checks on short copied subset playlists
- `tests/test_e2e_local_session_representative_hls_ground_truth.py`
  - exact session truth for the few HLS subsets that proved stable enough
- `tests/test_e2e_api_stream_representative_hls.py`
  - those same reviewed HLS subsets served through the real `api_stream` seam
- `tests/test_e2e_local_session_representative_mp4_ground_truth.py`
  - exact truth for reviewed MP4 windows on the real `video_files` seam
- `tests/test_detector_lab_representative_media.py`
  - calibration-oriented score-shape checks for reviewed low-resolution and
    compression windows
- `tests/test_e2e_local_session_representative_mp4_soak.py`
  - capped representative `video_files` confidence in the ordinary slow lane
  - full-file `pytest -m soak` confidence for selected longer MP4 fixtures
  - broad runtime contracts such as repeatability, interruption/recovery, and
    long-baseline false-positive posture

Keep exact truth intentionally small. Promote only reviewed stable subsets into
`tests/fixtures/media/ground_truth.json`. Leave borderline, threshold-sensitive,
or mainly diagnostic cases in the intent or calibration lanes instead of
inventing exact truth.

Read the MP4 side as three layers:

- reviewed-subset exact truth
- capped long-run confidence
- full-file soak confidence

The full-file soak lane is confidence-building only. Run it with `pytest -m
soak` in scheduled or manual-depth validation. It proves long-run completion,
restart/cancel honesty, and readable persisted output, not exact detector
truth.

## Metadata Files

Use `manifest.json` when you need file paths, source roles, artifact type,
strength, placement, media metadata, local HLS playlist details, or notes.

Use `expected_results.json` when you need detector intent: whether
black-screen, blur, or quality-degradation behavior is expected, not expected,
or borderline.

For local HLS entries, both files also record segment duration, segment count,
source MP4 path, playlist path, and an approximate artifact timeline by
segment index. Clean baselines use an explicit `artifact_free_baseline`
timeline instead of leaving the stream timeline implicit.

The expectations are intentionally broader than exact alert-count ground truth.
When a representative case proves stable enough for exact counts or alert
positions, promote only the reviewed subset into `ground_truth.json` instead
of turning the whole representative catalog into fake-precise truth.

## How To Extend

1. Add a clean source MP4 to `local_files/source` or choose an existing source scenario.
2. Put derived MP4s in the matching artifact folder.
3. Name files as `<source_id>__<artifact>_<strength>_<position>_<duration>.mp4`.
4. Add entries to `manifest.json` and `expected_results.json` in the same change.
5. Mark uncertain samples as `threshold_dependent` or `borderline_or_metric_only`; do not invent false certainty.
6. Convert only the most useful cases to `local_hls/` when stream behavior
   needs validation, starting with source baselines before artifact-heavy
   cases.

## Practical Use

Use a focused slice first: one source baseline, one strong positive, and one
borderline case for the changed detector area. Run broader representative
coverage only when the branch actually reaches real-media, transport, or
longer-run runtime risk.
