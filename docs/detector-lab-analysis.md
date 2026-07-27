# Detector Lab Analysis Guide

This document explains what `detector_lab` is for, how its current algorithm
families are organized, and how to read its output at the current project
stage.

Use it as a maintainer guide for experimentation, not as a statement that all
detector-lab algorithms are production-ready.

## Purpose

`detector_lab` exists to let us compare detector ideas and alert-policy ideas
against real checked-in media without changing the production runtime first.

Its practical goals are:

- compare algorithms on the same windows
- reuse production-style slice discovery and detector contracts where possible
- keep experiment output flat and easy to inspect
- make promotion into the runtime explicit rather than accidental

## Current Scope

`detector_lab` currently covers three main experiment families:

- runtime-backed baselines
  - current production detectors and rules reused for comparison
- experimental detector variants
  - blur-scoring variants that stay outside the runtime catalog
- practical lab-only alert policies
  - readable policy experiments used to compare blur and motion-blur ideas

Key package entry points:

- [`detector_lab/algorithms.py`](../detector_lab/algorithms.py)
- [`detector_lab/blur_experiments.py`](../detector_lab/blur_experiments.py)
- [`detector_lab/practical_alerts.py`](../detector_lab/practical_alerts.py)
- [`detector_lab/contracts.py`](../detector_lab/contracts.py)
- [`detector_lab/runner.py`](../detector_lab/runner.py)

## Algorithm Families

### Runtime-backed baselines

These keep detector-lab anchored to current production behavior:

- `production.video_blur.motion_guard_v1`
- `production.video_metrics.black_screen_v1`

They are useful for answering:

- does an experiment improve on current production behavior?
- is a new metric mostly duplicating the current detector?

### Experimental blur detector variants

The blur experiment family is centered around:

- shared blur-analysis context
- reusable score-shaping families
- one flat detector-style export row per analyzed window

Current families include:

- soft blends
- agreement/disagreement blends
- structure-relief variants
- multi-scale structure variants
- motion/flow-backed variants

This is intentionally closer to “experiment workbench” code than the production
runtime. That is acceptable as long as algorithm registration and export
contracts stay explicit and readable.

### Practical lab-only alert policies

The practical alert layer exists to test readable policy ideas on top of the
experiment facts.

Current practical policies include:

- black alert
- blur alert variants
- motion-blur alert variant

These are comparison tools, not production alert rules. They are useful for:

- checking whether a detector output is actionable
- testing guardrails around black or dark transitions
- comparing blur and motion-blur lane ownership

## How To Read detector_lab Output

There are two main output styles:

- full experiment export
  - one row per algorithm per analyzed window
- compact production-fixture export
  - one merged row per analyzed window for checked-in production fixtures

When reading output, these fields are usually the most important:

- `algorithm_id`
- `detector_id`
- `rule_detector_id`
- `ground_truth_summary`
- `source_name`
- `window_start_sec`
- `blur_score`
- `motion_mean`
- `motion_p90`
- `alert_count`
- `alert_titles`
- `alert_messages`

For motion/flow-backed variants, also pay attention to:

- `motion_blur_method`
- `optical_flow_mean`
- `optical_flow_p90`
- `optical_flow_coherence`
- `motion_coherence`
- `motion_incoherence_penalty`

## Ground Truth And Labels

Detector-lab currently relies on two kinds of fixture truth:

- session-level checked-in ground truth
- per-second labels for checked-in MP4 fixtures

Important files:

- [`tests/fixtures/media/ground_truth.json`](../tests/fixtures/media/ground_truth.json)
- [`tests/fixtures/media/video_file_second_labels.json`](../tests/fixtures/media/video_file_second_labels.json)

The per-second label map is especially useful for motion-blur and black/blur
comparison work because it keeps fixture intent out of the detector code while
remaining easy to inspect.

## Test Surface

Detector-lab tests are intentionally split into:

- synthetic/controlled experiment and policy coverage
  - [`tests/test_detector_lab_runner.py`](../tests/test_detector_lab_runner.py)
  - [`tests/test_detector_lab_metrics.py`](../tests/test_detector_lab_metrics.py)
  - [`tests/test_detector_lab_practical_blur.py`](../tests/test_detector_lab_practical_blur.py)
  - [`tests/test_detector_lab_practical_motion.py`](../tests/test_detector_lab_practical_motion.py)
- real-media confidence checks
  - [`tests/test_detector_lab_real_media.py`](../tests/test_detector_lab_real_media.py)

That split helps keep:

- fast iteration loops for scoring and policy logic
- slower confidence checks for real fixture media

The [testing guide](./testing-and-validation.md#detector-validation-ownership)
owns category-to-lane selection. Use the
[detailed ownership inventory](./detector-validation-ownership.md) before
consolidating tests or promoting representative calibration into exact truth.

## What detector_lab Is Not

`detector_lab` is not:

- the production detector catalog
- the production alert-rule catalog
- the default UI alert model
- a promise that a motion-blur experiment is ready for runtime promotion

Promotion should happen only when the algorithm, rule semantics, tests, and
documentation are intentionally updated together.
