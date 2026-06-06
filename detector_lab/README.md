# Detector Lab

`detector_lab` is a local evaluation workspace for comparing detector metrics
and alert-rule behavior on real election clips before promoting changes into
the main runtime.

## Status And Scope

`detector_lab` is an experiment workspace, not the supported production runtime
detector catalog.

Use this package for:

- algorithm comparison
- detector scoring experiments
- practical lab-only alert policies
- promotion-candidate evaluation against checked-in fixtures

Do not read this package as proof that a detector or alert is part of the
default runtime or UI model.

Current status labels:

- runtime-backed baseline
  - production detector or rule reused here for comparison
- experimental detector variant
  - detector-lab-only algorithm not registered in the main runtime
- practical lab-only alert policy
  - readable policy experiment used for comparison, not a runtime alert rule

The package stays intentionally close to production:

- it reuses production slice discovery
- it reuses production detector baselines where possible
- it can reuse production alert rules when an algorithm declares a compatible
  detector id

That keeps experiment output comparable with runtime behavior while still
leaving room for blur-specific scoring variants.

## How To Read This Package

Use these boundaries when navigating the code:

- `blur_experiments.py`
  - shared blur-analysis context plus experiment families
  - best place to compare detector-side scoring variants
- `practical_alerts.py`
  - lab-only policy experiments built on top of stable facts
  - best place to compare readable alerting ideas before runtime promotion
- `contracts.py`
  - stable lab-facing types, especially `ExperimentWindowFacts`
- `algorithms.py`
  - explicit algorithm catalog and maturity labeling

The practical-alert path now follows a consistent shape:

1. build `ExperimentWindowFacts`
2. compute a policy score
3. apply guardrails
4. export one flat comparison row

The experiment-detector path follows a similar shared structure:

1. prepare shared blur-analysis context
2. compute one family-specific score series
3. finalize one detector-style export row

The matching high-signal tests are concentrated in
[`tests/test_detector_lab.py`](../tests/test_detector_lab.py). That file is
organized around the current detector-lab responsibilities:

- runner and CLI wiring
- fixture-set and export contracts
- blur experiment families
- optical-flow and motion-coherence helpers
- practical lab-only alert policies

## Package Map

- `cli.py`
  - command-line entrypoint
- `runner.py`
  - orchestration for one evaluation run
- `algorithms.py`
  - explicit registry of production and experimental algorithm ids
- `blur_experiments.py`
  - shared blur measurements and experiment scoring formulas
- `reporting.py`
  - flat CSV export shaping and ground-truth lookup caching
- `contracts.py`
  - package-level types and export contracts
- `tests/fixtures/media/video_file_second_labels.json`
  - fixture-owned per-second label map for checked-in MP4 test videos
  - compact numeric scheme:
    - `0` normal
    - `1` black
    - `2` blur
    - `3` motion blur
    - `9` unknown / malformed

## What It Evaluates

Algorithms are registered explicitly in `detector_lab/algorithms.py`.
Current baselines:

- `production.video_blur.motion_guard_v1`
  - production `video_blur`
  - outputs blur metrics such as `blur_score`, `sharpness_p10`,
    `sharpness_p90`, `motion_mean`, and `motion_p90`
  - evaluates the production blur alert rule
- `production.video_metrics.black_screen_v1`
  - production `video_metrics`
  - outputs black-screen metrics such as `black_ratio`, `total_black_sec`,
    and `longest_black_sec`
  - evaluates the production black-screen alert rule

Current blur experiments:

- `experimental.video_blur.weighted_soft_v1`
  - `0.65 * absolute_blur + 0.35 * dynamic_blur`
  - softer than `max(...)`, but still biased toward global softness
- `experimental.video_blur.rms_soft_v1`
  - root-mean-square blend of absolute and dynamic blur
  - smoother than `max(...)`, but still tends to stay fairly high when one
    signal is high
- `experimental.video_blur.agreement_soft_v1`
  - weighted blend with a disagreement penalty
  - best suited to suppress globally soft but internally stable moving-camera
    footage
- `experimental.video_blur.compression_robust_v1`
  - agreement-style blur blend plus a broad-structure relief term
  - emits `edge_density`, `mean_edge_strength`, and `texture_energy`
  - designed to test whether compressed but still structurally healthy footage
    should score lower than the current detector
- `experimental.video_blur.generalized_geom_v1`
  - geometric-mean blur core plus a broad-structure relief term
  - meant to be the lowest-tuning, most cross-source-friendly blur-core
    candidate in the lab
- `experimental.video_blur.generalized_consensus_v1`
  - mean-based blur core with a modest disagreement penalty plus a
    broad-structure relief term
  - meant to be a readable middle ground between a strict geometric core and
    more hand-tuned soft blends
- `experimental.video_blur.multiscale_structure_v1`
  - agreement-style blur blend plus multi-scale structure persistence relief
  - emits coarse-scale edge and texture metrics after repeated downsampling
  - designed to reward larger contours and object structure that survive blur-
    resistant downsampling better than fine compression noise
- `experimental.video_blur.motion_coherent_v1`
  - blur candidate using multi-scale motion coherence summaries
  - emits motion-energy, persistence, and coherence fields in addition to the
    base blur metrics
  - designed to distinguish blur-like softness from coherent scene motion
- `experimental.video_blur.sparse_lk_motion_v1`
  - motion-blur candidate using sparse Lucas-Kanade optical flow support
  - emits normalized optical-flow magnitude and coherence summaries
  - designed to require both softness and coherent tracked motion before score
    inflation
- `experimental.video_blur.dense_farneback_motion_v1`
  - motion-blur candidate using dense Farneback optical flow support
  - emits normalized dense-flow magnitude and coherence summaries
  - designed to compare dense motion evidence against the same blur base used
    by simpler blends

Current practical lab-only alert policies:

- `practical.black_frame_alert_v1`
  - simple lab-side black alert policy
- `practical.blur_alert_v1`
  - initial practical blur policy experiment
- `practical.blur_alert_v2`
  - calibrated practical blur policy experiment
- `practical.blur_alert_v3`
  - calibrated practical blur policy with black/dark transition guardrails
- `practical.motion_blur_alert_v1`
  - motion-blur policy experiment

All of the practical policies above are detector-lab-only comparison logic.
They are not part of the supported production detector catalog, runtime alert
catalog, or default UI alert model unless they are promoted explicitly.

The full experiment export is one row per algorithm per analyzed window.

The compact production fixture export used by `--fixture-set test_video_files`
is different on purpose:

- it merges the current production `video_blur` and `video_metrics` rows into
  one row per analyzed second/window
- it adds `row_index` for quick scanning
- it keeps one namespaced `blur_*` group and one `black_*` group so the file
  is still readable even when more experiment metrics are present

Ground-truth summaries are cached separately in
`detector_lab/output/ground_truth_stream_cache.json`, keyed by serialized input
path. Repeated runs can then reload the same fixture summary instead of
rebuilding it for every exported row.

For checked-in MP4 fixtures, the summary now also carries a compact
`per_second_labels` string sourced from
`tests/fixtures/media/video_file_second_labels.json`. That keeps per-second
fixture intent out of the detector code while making the CSV easy to compare
against expected black and blur intervals.

Important full-profile CSV columns:

- `algorithm_id`
- `detector_id`
- `rule_detector_id`
- `ground_truth_summary`
- `source_name`
- `window_start_sec`
- `window_duration_sec`
- `blur_score`
- `motion_mean`
- `motion_p90`
- `absolute_blur`
- `dynamic_blur`
- `edge_density`
- `mean_edge_strength`
- `texture_energy`
- `structure_strength`
- `medium_scale_edge_density`
- `coarse_scale_edge_density`
- `medium_scale_texture_energy`
- `coarse_scale_texture_energy`
- `edge_persistence`
- `texture_retention`
- `multiscale_structure_strength`
- `motion_blur_method`
- `optical_flow_mean`
- `optical_flow_p90`
- `optical_flow_coherence`
- `fine_scale_motion_energy`
- `medium_scale_motion_energy`
- `coarse_scale_motion_energy`
- `motion_persistence`
- `motion_coherence`
- `motion_incoherence_penalty`
- `blur_blend_id`
- `black_ratio`
- `alert_count`
- `alert_titles`
- `alert_messages`
- `processing_sec`

Important compact production-fixture columns:

- `row_index`
- `input_path`
- `ground_truth_summary`
- `source_name`
- `window_index`
- `window_start_sec`
- `window_duration_sec`
- `blur_algorithm_id`
- `blur_sample_count`
- `blur_sharpness_p10`
- `blur_sharpness_p90`
- `blur_motion_mean`
- `blur_motion_p90`
- `blur_absolute_blur`
- `blur_dynamic_blur`
- `blur_edge_density`
- `blur_mean_edge_strength`
- `blur_texture_energy`
- `blur_structure_strength`
- `blur_medium_scale_edge_density`
- `blur_coarse_scale_edge_density`
- `blur_medium_scale_texture_energy`
- `blur_coarse_scale_texture_energy`
- `blur_edge_persistence`
- `blur_texture_retention`
- `blur_multiscale_structure_strength`
- `blur_motion_blur_method`
- `blur_optical_flow_mean`
- `blur_optical_flow_p90`
- `blur_optical_flow_coherence`
- `blur_fine_scale_motion_energy`
- `blur_medium_scale_motion_energy`
- `blur_coarse_scale_motion_energy`
- `blur_motion_persistence`
- `blur_motion_coherence`
- `blur_motion_incoherence_penalty`
- `blur_blend_id`
- `blur_score`
- `blur_detected`
- `blur_alert_count`
- `black_algorithm_id`
- `black_detected`
- `black_segment_count`
- `black_total_sec`
- `black_longest_sec`
- `black_ratio`
- `black_alert_count`

## Run Examples

Run both blur and black-screen detectors on the first 10 one-second windows of
one local MP4:

```bash
PYTHONPATH=src:. python -m detector_lab.cli \
  --mode video_files \
  --input tests/fixtures/media/election_clips/normal_baseline/010300111_20260419_202346_0000-0030.mp4 \
  --max-windows 10 \
  --output detector_lab/output/normal_baseline_eval.csv
```

Run the current production detectors and alert rules across all checked-in MP4
test fixtures:

```bash
PYTHONPATH=src:. python -m detector_lab.cli \
  --fixture-set test_video_files \
  --output detector_lab/output/test_video_files_eval.csv
```

Run all registered detector-lab algorithms across the same fixture set:

```bash
PYTHONPATH=src:. python -m detector_lab.cli \
  --fixture-set test_video_files \
  --all-algorithms \
  --output detector_lab/output/test_video_files_all_algorithms.csv
```

When multiple algorithms target the same detector id, the fixture-set runner
automatically switches to the full export profile so compared rows do not
overwrite one another during compact merging.

That fixture-set export intentionally uses a slimmer CSV profile than the
full experiment runs. It keeps the detector metrics, but still drops some
repeated per-detector metadata, such as:

- one merged row per analyzed second instead of separate blur and black rows
- `row_index` for quick visual scanning
- no `rule_detector_id`
- no `source_group`
- no `alert_messages`

That default fixture set also stays focused on valid detector-quality fixtures.
It resolves inputs from the fixture catalog entries marked `valid`, plus the
short checked-in trigger clips. Intentionally malformed MP4 fixtures stay in a
separate failure-path lane and should be run explicitly when you want decoder or
probe resilience coverage.

Run the two checked-in normal-baseline election clips and write one compact CSV
per clip:

```bash
PYTHONPATH=src:. python3 -m detector_lab.cli \
  --fixture-set normal_baseline_video_files \
  --split-output \
  --output detector_lab/output/normal_baseline_eval.csv
```

That command writes a directory named
`detector_lab/output/normal_baseline_eval_normal_baseline_video_files/`
containing one file per input clip.

Run only blur on a clip:

```bash
PYTHONPATH=src:. python -m detector_lab.cli \
  --mode video_files \
  --input tests/fixtures/media/election_clips/normal_baseline/010300111_20260419_202346_024430-024500.mp4 \
  --detectors video_blur \
  --max-windows 10 \
  --output detector_lab/output/blur_only_eval.csv
```

Run one explicit algorithm id:

```bash
PYTHONPATH=src:. python -m detector_lab.cli \
  --mode video_files \
  --input tests/fixtures/media/election_clips/normal_baseline/010300111_20260419_202346_0000-0030.mp4 \
  --algorithms production.video_blur.motion_guard_v1 \
  --max-windows 10 \
  --output detector_lab/output/blur_motion_guard_v1.csv
```

Compare production and softer blur variants on one clip:

```bash
PYTHONPATH=src:. python -m detector_lab.cli \
  --mode video_files \
  --input tests/fixtures/media/election_clips/normal_baseline/010300111_20260419_202346_0000-0030.mp4 \
  --algorithms \
    production.video_blur.motion_guard_v1 \
    experimental.video_blur.weighted_soft_v1 \
    experimental.video_blur.rms_soft_v1 \
    experimental.video_blur.agreement_soft_v1 \
  --max-windows 10 \
  --output detector_lab/output/blur_variant_compare.csv
```

Run the compression-robust experiment on one clip:

```bash
PYTHONPATH=src:. python -m detector_lab.cli \
  --mode video_files \
  --input tests/fixtures/media/election_clips/normal_baseline/010300111_20260419_202346_024430-024500.mp4 \
  --algorithms experimental.video_blur.compression_robust_v1 \
  --max-windows 10 \
  --output detector_lab/output/compression_robust_eval.csv
```

Run the generalized blur-core variants on one clip:

```bash
PYTHONPATH=src:. python -m detector_lab.cli \
  --mode video_files \
  --input tests/fixtures/media/election_clips/normal_baseline/010300111_20260419_202346_024430-024500.mp4 \
  --algorithms \
    experimental.video_blur.generalized_geom_v1 \
    experimental.video_blur.generalized_consensus_v1 \
  --max-windows 10 \
  --output detector_lab/output/generalized_blur_core_eval.csv
```

Run the multi-scale structure experiment on one clip:

```bash
PYTHONPATH=src:. python -m detector_lab.cli \
  --mode video_files \
  --input tests/fixtures/media/election_clips/normal_baseline/010300111_20260419_202346_024430-024500.mp4 \
  --algorithms experimental.video_blur.multiscale_structure_v1 \
  --start-window 5 \
  --max-windows 10 \
  --output detector_lab/output/multiscale_structure_eval.csv
```

Run the optical-flow motion-blur experiments on one clip:

```bash
PYTHONPATH=src:. python -m detector_lab.cli \
  --mode video_files \
  --input tests/fixtures/media/video_files/blur_middle_long.mp4 \
  --algorithms \
    experimental.video_blur.sparse_lk_motion_v1 \
    experimental.video_blur.dense_farneback_motion_v1 \
  --max-windows 10 \
  --output detector_lab/output/optical_flow_motion_eval.csv
```

Run on a local `.ts` segment folder:

```bash
PYTHONPATH=src:. python -m detector_lab.cli \
  --mode video_segments \
  --input tests/fixtures/media/video_segments/mixed_black_blur_long \
  --output detector_lab/output/segments_eval.csv
```

## How To Read The CSV

For blur experiments, sort or filter by:

- `algorithm_id`
- `alert_count`
- `blur_score`
- `motion_mean`
- `motion_p90`
- `absolute_blur`
- `dynamic_blur`
- `edge_density`
- `mean_edge_strength`
- `texture_energy`
- `structure_strength`
- `medium_scale_edge_density`
- `coarse_scale_edge_density`
- `medium_scale_texture_energy`
- `coarse_scale_texture_energy`
- `edge_persistence`
- `texture_retention`
- `multiscale_structure_strength`
- `blur_blend_id`
- `source_name`

Useful comparisons:

- clean moving-camera clips should have high motion and low or zero blur alerts
- stable true-blur clips should have high blur and enough alert evidence
- clean baseline clips from the target media family should produce no blur
  alerts
- if `absolute_blur` stays high while `dynamic_blur` stays moderate, softer
  blends should fall below the production `max(...)` score
- if edge-based sharpness looks weak but `edge_density`, `mean_edge_strength`,
  and `texture_energy` stay comparatively healthy, the compression-robust
  variant should score lower than the plain blur blends
- if coarse-scale structure remains healthy after downsampling, `edge_persistence`,
  `texture_retention`, and `multiscale_structure_strength` should stay higher
  than in truly blurry or contour-poor footage
- if `ground_truth_summary` is populated for a checked-in fixture, compare the
  algorithm row directly against the expected detector counts and alert family
- motion-blur variants should score low on stable blurred content with little
  coherent motion and higher on windows where softness and directional motion
  coincide

## Multi-Scale Metrics

The multi-scale experiment uses three solid families of metrics:

- `medium_scale_edge_density` and `coarse_scale_edge_density`
  - edge density after one and two 2x downsampling steps
  - larger contours survive; tiny noise and compression junk usually do not
- `medium_scale_texture_energy` and `coarse_scale_texture_energy`
  - texture energy after the same downsampling steps
  - helps track whether coarse structure still carries meaningful contrast
- `edge_persistence` and `texture_retention`
  - cross-scale survival ratios from fine to coarse structure
  - stronger values suggest that contours belong to larger objects rather than
    only fine high-frequency detail

The experiment combines those fields into `multiscale_structure_strength` and
uses that as a relief signal against the base blur score.

## Optical Flow Notes

The two optical-flow variants require OpenCV and NumPy. Install the extra with:

```bash
pip install -e .[detectorlab]
```

The sparse Lucas-Kanade path follows tracked corner features. The dense
Farneback path estimates flow everywhere in the frame. Both variants emit
normalized magnitude and coherence summaries, then use those as motion support
for the base blur score rather than as a standalone detector truth.

For black-screen experiments, sort or filter by:

- `algorithm_id`
- `black_detected`
- `black_ratio`
- `longest_black_sec`
- `alert_count`

## Adding Experiments

Add detector experiments in `detector_lab/algorithms.py` as a
`LabAlgorithmSpec`.

Keep the lab seams aligned with the main backend:

- `detector_lab/contracts.py`
  - shared algorithm and flat export-row contracts
- `detector_lab/runner.py`
  - production-compatible slice discovery plus alert-rule execution
- `detector_lab/reporting.py`
  - CSV/export shaping only
- `detector_lab/blur_experiments.py`
  - blur metric experiments and shared measurement helpers

Good experiment shape:

- one stable `algorithm_id`, such as `experimental.video_blur.motion_guard_v2`
- one flat metric row that looks like production detector output
- `rule_detector_id="video_blur"` only when the row is compatible with that
  production alert rule
- `alert_rule_runner=...` for comparing a custom proof-of-concept alert rule
  against the same detector metrics
- `rule_detector_id=None` for early proof-of-concept metrics that should not
  create alerts yet

The runner isolates rolling alert-rule state per algorithm id, so two detector
or alert-rule variants can be evaluated in the same CSV without sharing warm-up
or recovery state.

## Pros

- fast local comparison on the same election clips used in manual testing
- CSV output works in spreadsheets and scripts
- production detector and alert contracts stay visible
- algorithm ids make A/B comparisons explicit
- experimental algorithms can be added without changing the app, session runner,
  or UI
- custom rule variants can be tested without moving rule experiments into
  production code too early
- repeated false positives can be turned into clear metrics before changing
  production behavior

## Cons

- it is not a replacement for end-to-end session testing
- it can drift if experimental algorithms stop matching production contracts
- large media files can make runs slow, so use `--max-windows` while iterating
- CSV rows show detector and alert decisions, but not frontend playback behavior
- it intentionally avoids dynamic plugin loading, so adding a new experiment is
  a small code edit rather than a runtime configuration change

## Extension Rule

Add experimental algorithms here only when they can produce flat rows that are
easy to compare with production detector output. Keep detector facts separate
from alert rules. Once an algorithm proves useful, promote the small proven part
into `src/detectors.py`, `src/alert_rules.py`, or a dedicated production
detector module.
