# Detector Validation Ownership

This is the detailed supporting record for the authoritative
[detector-validation ownership table](./testing-and-validation.md#detector-validation-ownership).
It records current tests, their primary behavior owner, fixture role, overlap
review, and cleanup rules.

Sharing a fixture does not make tests duplicates. A detector-lab calibration
check, a runtime session test, and an exact-truth test can each protect a
different boundary.

## Ownership Categories

These categories describe the one primary behavior a test protects. They do
not prevent a test from exercising supporting layers; they prevent that
incidental coverage from becoming its reason to exist.

| Category | Owns | Excludes |
| --- | --- | --- |
| Production detector facts | Stable built-in detector output for controlled inputs, supported modes, and detector registration contracts. | Alert creation, session persistence, experimental scoring, and real-runtime lifecycle claims. |
| Production alert rules | Rule entry, suppression, recovery, severity, and emitted alert semantics from detector facts. | Whether a detector calculated the fact correctly or whether a session persisted it. |
| Processor/runtime integration | Analyzer selection, slice propagation, result routing, failure isolation, and alert-bundle assembly. | Exact media calibration, long-running session behavior, and detector-lab experiments. |
| Detector-lab experiments | Experimental algorithm, practical-policy, CSV/export, and comparison behavior outside the supported runtime catalog. | A production-promotion claim, exact session truth, or default UI behavior. |
| Representative-media calibration | Broad score/shape, false-positive, and promotion-boundary evidence on reviewed representative subsets. | Exact counts, positions, or a claim that a calibration result is production truth. |
| Exact ground truth | Reviewed stable session outputs for a deliberately small fixture subset. | Borderline or diagnostic cases, broad calibration, and unreviewed fixture expectations. |
| End-to-end runtime confidence | The real session boundary: discovery/loading, detector and rule execution, persistence, and readable session output. | Fine-grained detector threshold tuning or exhaustive fixture coverage. |
| Soak/manual validation | Long-run completion, repeatability, interruption/recovery, or environment-dependent confidence unsuitable for routine validation. | A fast deterministic regression guarantee or evidence that all environments behave identically. |
| Fixture/catalog integrity | Fixture identity, expected-intent metadata, promoted-truth references, and local-asset availability rules. | Detector quality, alert semantics, or runtime behavior. |

Use `Fixture/catalog integrity` for support tests rather than misclassifying
them as exact truth. It protects whether other evidence is valid, not the
behavior those other tests assert.

## Inventory Baseline

| Test surface | Files | Markers | Fixture class | Current lane | Cost |
| --- | --- | --- | --- | --- | --- |
| Production detector facts | `test_detectors.py` | none | synthetic rows and small inputs | `just test-detectors`; fast synthetic | low |
| Detector/media integration | `test_detectors_integration.py` | `slow` | checked-in media | weekly slow media | medium |
| Production alert rules | `test_alert_rules.py`, `test_alert_rules_black.py`, `test_alert_rules_blur.py` | none | synthetic detector rows and alert state | `just test-alert-rules`; fast synthetic | low |
| Processor/runtime integration | `test_processor.py`, `test_processor_context_alerts.py`, `test_processor_failures.py`, `test_processor_routing.py` | none | temporary inputs, synthetic registrations, in-memory stores | fast synthetic; `just test-processor` runs the core file | low |
| Detector-lab experiments | `test_detector_lab.py` | none | synthetic slices, temporary CSVs, checked-in fixture metadata; optional local baselines | `just test-detector-lab`; fast synthetic | low |
| Detector-lab real-media confidence | `test_detector_lab_real_media.py` | `slow` | checked-in MP4 fixtures | `just test-real-media`; weekly slow media | medium |
| Detector-lab representative calibration | `test_detector_lab_representative_media.py` | `slow` | reviewed local representative MP4 subsets and catalog metadata | local/manual slow confidence | medium-high |
| Representative fixture/catalog guards | `test_representative_hls_test_support.py` | none | manifest, expected-results, ground-truth catalogs; optional local HLS exports | fast catalog checks with local skips where assets are absent | low |
| Local-session runtime smoke | `test_e2e_local_session.py` | `e2e` | generated tiny segments and synthetic analyzer bundle | explicit E2E smoke | low |
| Curated real-media runtime | `test_e2e_local_session_real_media.py` | `e2e`, `slow` | checked-in MP4 and segment fixtures | weekly slow media | medium |
| Representative HLS intent | `test_e2e_local_session_representative_hls.py` | `e2e`, `slow` | reviewed local HLS/MP4 subsets | local/manual slow confidence | medium-high |
| Representative HLS exact truth | `test_e2e_local_session_representative_hls_ground_truth.py` | `e2e`, `slow` | reviewed local HLS subsets and `ground_truth.json` | local/manual slow confidence | medium-high |
| Representative MP4 exact truth | `test_e2e_local_session_representative_mp4_ground_truth.py` | `e2e`, `slow` | reviewed local MP4 subsets and `ground_truth.json` | local/manual slow confidence | medium-high |
| Representative MP4 capped/soak confidence | `test_e2e_local_session_representative_mp4_soak.py` | `e2e`, `slow`; selected `soak` cases | reviewed local MP4 subsets | capped checks in slow confidence; full-file cases weekly/manual soak | high |
| Synthetic `api_stream` exact truth | `test_e2e_session_ground_truth_api_stream.py` | `e2e` | synthetic stream events and checked-in truth cases | explicit E2E contract confidence | low |
| Local real-media exact truth | `test_e2e_session_ground_truth_local.py` | `e2e`, `slow` | checked-in real media and `ground_truth.json` | weekly slow media | medium-high |
| Representative `api_stream` transport | `test_e2e_api_stream_representative_hls.py` | `e2e`, `slow` | reviewed local HLS subsets | local/manual slow confidence | medium-high |

## Primary Assignments

Each row covers every test in the named file unless a marker-qualified subset
is specified. Secondary seams explain useful cross-layer coverage; they do not
make a test a duplicate of its primary owner.

| Files or subset | Primary owner | Secondary seams |
| --- | --- | --- |
| `test_detectors.py` | Production detector facts | detector registration and supported-mode exposure |
| `test_detectors_integration.py` | Production detector facts | checked-in media confidence |
| `test_alert_rules.py`, `test_alert_rules_black.py`, `test_alert_rules_blur.py` | Production alert rules | detector-fact inputs |
| `test_processor.py`, `test_processor_context_alerts.py`, `test_processor_failures.py`, `test_processor_routing.py` | Processor/runtime integration | detector registration, result storage, alert-bundle assembly |
| `test_detector_lab.py` | Detector-lab experiments | fixture metadata and export contracts |
| `test_detector_lab_real_media.py` | Detector-lab experiments | checked-in real-media confidence |
| `test_detector_lab_representative_media.py` | Representative-media calibration | detector-lab experiments and promotion-boundary evidence |
| `test_representative_hls_test_support.py` | Fixture/catalog integrity | representative calibration and exact-truth reference validity |
| `test_e2e_local_session.py` | End-to-end runtime confidence | session snapshot contract |
| `test_e2e_local_session_real_media.py` | End-to-end runtime confidence | checked-in real-media detector/rule confidence |
| `test_e2e_local_session_representative_hls.py` | End-to-end runtime confidence | representative-media intent and MP4/HLS agreement |
| `test_e2e_local_session_representative_hls_ground_truth.py` | Exact ground truth | end-to-end runtime confidence |
| `test_e2e_local_session_representative_mp4_ground_truth.py` | Exact ground truth | end-to-end runtime confidence |
| `test_e2e_local_session_representative_mp4_soak.py` without `@pytest.mark.soak` | End-to-end runtime confidence | representative-media confidence and long-window output shape |
| `test_e2e_local_session_representative_mp4_soak.py` with `@pytest.mark.soak` | Soak/manual validation | end-to-end runtime confidence and recovery behavior |
| `test_e2e_session_ground_truth_api_stream.py` | Exact ground truth | synthetic `api_stream` end-to-end contract |
| `test_e2e_session_ground_truth_local.py` | Exact ground truth | checked-in real-media end-to-end confidence |
| `test_e2e_api_stream_representative_hls.py` | End-to-end runtime confidence | representative-media intent and `api_stream` transport |

All inventoried detector-related tests now have a primary owner. The two
marker-qualified soak groups are deliberately separate because they protect
different operating conditions.

## Fixture Roles And Consumers

Fixture identity answers what is being run. Calibration intent describes broad
expected behavior. Exact truth is reserved for reviewed stable session output.
The same media may appear in several rows without collapsing those roles.

| Fixture source | Identity owner | Expectation or truth owner | Consumers and distinct proof |
| --- | --- | --- | --- |
| Generated inputs, temporary files, synthetic analyzer rows | individual test setup and `media_factory` | inline test assertions only | detector, rule, processor, detector-lab synthetic, and small E2E smoke tests prove deterministic contracts without making media-quality claims |
| Checked-in core media: `tests/fixtures/media/video_files/` and `video_segments/` | repository fixture corpus | `video_file_second_labels.json` supplies per-second detector-lab context; selected session cases in `ground_truth.json` supply exact truth | detector integration proves production detector behavior; detector-lab real-media proves experiment behavior; curated E2E proves runtime processing; local ground-truth tests prove selected exact session output |
| Representative media paths and HLS exports: `representative/manifest.json` | representative manifest and local asset paths | none by itself | catalog guards prove reference integrity; runtime, transport, calibration, and soak tests select reviewed MP4/HLS subsets from the same identities |
| Representative intent: `representative/expected_results.json` | representative manifest identifies the source | expectation catalog owns broad positive, negative, and borderline intent | detector-lab representative tests prove score/false-positive calibration; representative E2E and capped MP4 tests prove broad runtime behavior without asserting exact counts |
| Promoted exact truth: `tests/fixtures/media/ground_truth.json` | fixture metadata identifies generated, checked-in, or representative inputs | ground-truth cases own exact status, result, and alert expectations for reviewed subsets only | synthetic `api_stream`, local real-media, representative HLS, and representative MP4 exact-truth tests prove stable session outputs; catalog guards prove promoted references resolve |

Consequences for future cleanup:

- `expected_results.json` is not exact detector or alert truth; it must not be
  used to justify exact-count assertions.
- `ground_truth.json` is not a general calibration catalog; unpromoted,
  borderline, and compression-heavy cases remain intentionally outside it.
- A test that shares a representative fixture with a calibration or exact-truth
  test remains necessary when it owns a different runtime, transport, or
  long-run behavior.

## Lane Detail

The [testing guide's ownership table](./testing-and-validation.md#detector-validation-ownership)
is authoritative for category-to-lane selection. The inventory above records
the file-level lane and fixture class behind each category. Slow, local, and
soak tests are confidence layers, not lower-value duplicates of fast tests.

## Overlap Review

The following groups share assertions or fixtures closely enough to review.
They are not deletion instructions: a cleanup must preserve every distinct
behavior claim and stay in the current test owner and lane.

| Comparable tests | Boundary and shared claim | Classification | Current decision |
| --- | --- | --- | --- |
| `test_practical_blur_alert_v3_applies_hard_neighbor_penalty_at_exact_boundary`, `...skips_hard_neighbor_penalty_just_below_boundary`, `...penalty_can_demote_otherwise_alerting_score`, and `...skips_hard_neighbor_penalty_above_max_blur_score` | One synthetic practical-blur evaluator and adjacent neighbor-black thresholds. | Parameterization candidate | Keep all four behavior cases, but a later detector-lab-only refactor may use one parameterized threshold matrix or shared setup helper. It must retain the exact-boundary, demotion, and strong-score escape claims. |
| `test_representative_lowres_strong_end_stays_black_negative` and the `stable-docs-strong-end` row in `test_representative_lowres_source_family_matrix_stays_black_negative` | The same representative fixture, start window, black-frame detector, and black-negative result. | Consolidation candidate | The matrix adds source-family and quality-degradation context; fold the standalone assertion into that row only if its dedicated failure message remains clear. Do not change fixture coverage in this task. |
| `test_representative_lowres_moderate_start_stays_black_negative` and `test_representative_lowres_windows_stay_black_negative_but_score_as_motion_heavy` | The same startup fixture remains black-negative. | Intentional reinforcement | The first protects the black-frame detector alone; the second protects combined black-negative and quality-score calibration. Keep both. |
| Practical motion-blur black-transition suppression unit tests and `test_detector_lab_real_media.py` black-recovery checks | Both reject black-transition motion, but one controls synthetic guardrails and the other observes decoded checked-in media. | Intentional reinforcement | Keep both: they protect algorithm policy and media-decoding confidence at different boundaries. |
| Representative detector-lab calibration, representative HLS/MP4 runtime, and `api_stream` transport tests | They reuse reviewed representative cases and broad alert expectations. | Intentional reinforcement | Keep the layers separate: calibration owns score and promotion evidence; local sessions own persisted runtime behavior; `api_stream` owns transport and temporary-file cleanup. |
| Capped representative MP4 tests and `@pytest.mark.soak` full-file tests | The same local media family reaches session output. | Intentional reinforcement | Keep capped tests as practical runtime confidence and soak tests for completion, repeatability, and interruption/recovery. |

No probable deletion candidate is recorded yet. Similar test names, shared
fixtures, or matching boolean assertions are insufficient evidence when the
tests exercise different layers, fixture classes, or validation lanes.

## Deletion And Promotion Rules

### Delete Or Consolidate Only With Equivalent Coverage

A test may be deleted or folded into a parameterized case only when the review
names the surviving test and shows that it preserves all of the following:

- the same public behavior claim at the same primary boundary;
- the same fixture role and intent: synthetic contract, calibration, exact
  truth, runtime confidence, or soak/manual behavior;
- the relevant input variation, including a threshold edge or transport mode
  when that is what made the test distinct; and
- the same validation lane and a comparably clear failure signal.

The cleanup change must state the replacement test, focused validation command,
and why the removed assertion adds no remaining confidence. Sharing a fixture,
being slow, or having a similar boolean assertion is never enough. Prefer
parameterization or a small shared helper when it removes setup repetition
without hiding distinct behavior cases.

### Promote Representative Behavior Only After Review

`expected_results.json` records broad intent. Add a representative subset to
`ground_truth.json` only when all of the following are true:

- the manifest identifies the exact source, subset, mode, and detector set;
- the proposed status, result, and alert expectations have been reviewed from
  repeatable runs on the relevant production runtime path;
- the case is stable enough for exact assertions, not merely useful for score
  calibration, a false-positive guard, or a threshold investigation;
- an exact-truth test and catalog guard cover the promoted subset in its
  intended local/manual or checked-in lane; and
- the corresponding calibration or intent entry remains explicit when it
  still documents broader, non-exact behavior.

Leave compression-heavy, borderline, environment-sensitive, or transport-
divergent cases in calibration or broad runtime confidence until those
conditions are met. Promotion adds a reviewed truth claim; it does not by
itself make a detector or detector-lab algorithm production-ready.

## Lane Observations

- Protected fast CI excludes `e2e` and `slow` tests. It is not evidence for
  real-media, representative, or end-to-end behavior.
- `weekly_slow_media` runs only `-m slow`. Its manifest names
  `test_e2e_local_session.py` and `test_e2e_session_ground_truth_api_stream.py`,
  but both are `e2e`-only and are therefore deselected by that command. This is
  a lane-ownership observation for later review, not a change to their value.
- Local representative HLS/MP4 tests are intentionally distinct from
  checked-in fixture tests. Missing local representative exports should skip
  their checks rather than make routine validation depend on them.

## Inventory Boundaries

This baseline and its cleanup rules do not:

- apply a deletion or consolidation;
- alter markers, CI targets, fixtures, or detector behavior.

The authoritative category-to-lane map and command definitions remain in
[testing-and-validation.md](./testing-and-validation.md#detector-validation-ownership).
Detector-lab experiment intent remains in
[detector-lab-analysis.md](./detector-lab-analysis.md).
