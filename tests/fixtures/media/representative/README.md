# Representative Media Fixtures

This folder contains the large local MP4 confidence corpus for representative election-stream scenarios. It complements the small checked-in regression fixtures in `tests/fixtures/media/video_files` and `tests/fixtures/media/video_segments`.

The corpus is for opt-in local validation, detector tuning, and pre-migration confidence checks. Do not include the full dataset in default unit tests or lightweight CI.

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

Each source has controlled derived variants for black frames, Gaussian blur, compression noise, and low resolution. Strong black-frame and strong blur clips are useful for current detector confidence. Low-resolution and compression clips are mainly future quality-detector fixtures and false-positive checks.

## Metadata Files

Use `manifest.json` when you need file paths, source roles, artifact type, strength, placement, media metadata, or notes.

Use `expected_results.json` when you need detector intent: whether black-screen, blur, or quality-degradation behavior is expected, not expected, or borderline.

The expectations are intentionally not exact alert-count ground truth. Promote a small subset into exact session ground truth only after running the current detector pipeline and reviewing the output.

## How To Extend

1. Add a clean source MP4 to `local_files/source` or choose an existing source scenario.
2. Put derived MP4s in the matching artifact folder.
3. Name files as `<source_id>__<artifact>_<strength>_<position>_<duration>.mp4`.
4. Add entries to `manifest.json` and `expected_results.json` in the same change.
5. Mark uncertain samples as `threshold_dependent` or `borderline_or_metric_only`; do not invent false certainty.
6. Convert only the most useful cases to `local_hls/` when stream behavior needs validation.

## Practical Use

Use a focused slice first: one source baseline, one strong positive, and one borderline case for the changed detector area. Run the full corpus only for confidence passes before larger runtime, detector, or database work.
