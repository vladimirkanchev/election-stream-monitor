# Motion Coherence Blur Experiment

This document explains the current detector-lab motion-coherence blur
experiment and how it fits into the project.

It is intentionally a maintainer document, not a product promise. The motion
coherence algorithm is still part of `detector_lab`, not the supported
production runtime detector catalog.

## Status

- algorithm id: `experimental.video_blur.motion_coherent_v1`
- code entry point:
  - [`detector_lab/blur_experiments.py`](../detector_lab/blur_experiments.py)
- registry entry:
  - [`detector_lab/algorithms.py`](../detector_lab/algorithms.py)
- test coverage:
  - [`tests/test_detector_lab_metrics.py`](../tests/test_detector_lab_metrics.py)
  - [`tests/test_detector_lab_practical_motion.py`](../tests/test_detector_lab_practical_motion.py)
  - [`tests/test_detector_lab_real_media.py`](../tests/test_detector_lab_real_media.py)

## Purpose

The experiment tries to distinguish these two situations more cleanly than the
current production blur path:

- coherent scene or camera motion
- softness that looks more like motion blur, jitter, or motion-linked artifact

The design assumption is:

- real motion tends to stay visible across multiple image scales
- incoherent motion tends to fragment as the image is downsampled

So the algorithm augments blur scoring with multi-scale motion summaries rather
than treating all motion as equally suspicious.

## Current Design

The experiment reuses the shared detector-lab blur-analysis context and then
computes motion coherence from the extracted raw frames.

High-level flow:

1. prepare blur-analysis context
2. compute baseline blur measurements
3. compute multi-scale motion coherence metrics
4. reduce the blur score when motion looks incoherent
5. export one detector-style flat row

Public experiment-facing helpers currently used here:

- `prepare_blur_analysis_context(...)`
- `compute_motion_coherence_multiscale(...)`

Those public helpers exist so `detector_lab` code does not have to depend on
private implementation details more than necessary.

## Exported Motion-Coherence Fields

The motion-coherent experiment exports these additional fields:

- `fine_scale_motion_energy`
- `medium_scale_motion_energy`
- `coarse_scale_motion_energy`
- `motion_persistence`
- `motion_coherence`
- `motion_incoherence_penalty`

These fields are part of the detector-lab export contract in
[`detector_lab/contracts.py`](../detector_lab/contracts.py).

## Field Meaning

- `fine_scale_motion_energy`
  - frame-to-frame motion magnitude at the finest analysis scale
- `medium_scale_motion_energy`
  - motion magnitude after one downsampling step
- `coarse_scale_motion_energy`
  - motion magnitude after deeper downsampling
- `motion_persistence`
  - how much motion survives as the image is reduced in scale
- `motion_coherence`
  - how aligned the motion signal remains across scales
- `motion_incoherence_penalty`
  - how fragmented or inconsistent the motion looks across the analyzed
    sequence

These are comparison-oriented experiment metrics. They are not yet part of the
supported production detector payload.

## Why It Lives In detector_lab

This experiment belongs in `detector_lab` at the current project stage because
it is still evaluating:

- whether the motion features improve blur interpretation on real fixtures
- how stable the scoring is across different clip families
- whether the extra motion metrics are understandable enough to promote later

That is a good fit for detector-lab because it allows:

- side-by-side comparison with production blur output
- CSV inspection on checked-in fixture media
- real-media confidence tests without making the runtime detector contract
  larger too early

## Validation Surface

The current validation story is split on purpose:

- synthetic/controlled coverage
  - score composition
  - fail-closed handling
  - exported field mapping
  - monotonicity and incoherence behavior
- real-media confidence coverage
  - labeled fixture windows
  - black-transition suppression
  - full CSV field propagation

Read:

- [`tests/test_detector_lab_metrics.py`](../tests/test_detector_lab_metrics.py)
- [`tests/test_detector_lab_practical_motion.py`](../tests/test_detector_lab_practical_motion.py)
- [`tests/test_detector_lab_real_media.py`](../tests/test_detector_lab_real_media.py)
- [`docs/testing-and-validation.md`](./testing-and-validation.md)

## Promotion Criteria

Before promoting this experiment toward the production runtime, we should be
confident in at least these areas:

- the motion-coherence fields stay useful on real fixture media
- the scoring behavior is stable enough to document as a supported contract
- the production blur rule or a new runtime motion-blur rule can use the
  metrics without creating confusing operator behavior
- the runtime/UI story is clear enough that experimental motion semantics do
  not look more mature than they really are

Until then, this should remain a detector-lab experiment.
