# Detector Validation Ownership

This document is the authoritative detailed record for detector-validation
ownership and test-value decisions. The compact category-to-lane
[summary table](./testing-and-validation.md#detector-validation-ownership)
points here for test cases, evidence, overlap decisions, and cleanup rules.

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

## Test-Value Matrix

The matrix records one row for each reviewed test or distinct parameterized
behavior case. It is a cleanup decision record, not a ranking of tests by
speed or fixture reuse.

| Field | Record | Objective rule |
| --- | --- | --- |
| Test case | Node id or a stable parameterized behavior label. | Name one runnable test or one input case with a distinct assertion. |
| Primary owner and protected behavior | The ownership category and observable contract. | Describe the behavior that would regress, not implementation mechanics. |
| Layer and boundary | Detector, rule, processor, detector-lab, runtime, transport, catalog, or soak/manual boundary. | Use the earliest boundary whose failure the test is intended to diagnose. |
| Fixture role | Synthetic contract, checked-in media, representative calibration, exact truth, local-only confidence, or soak/manual input. | Fixture identity alone is not a role. Record what the fixture is evidence for. |
| Expected failure signal | The likely regression class: detector fact, rule decision, threshold guardrail, decoding/media drift, transport, runtime persistence, catalog integrity, or environment availability. | A case is comparable only when a failure gives a similarly actionable signal. |
| Runtime cost | Low, medium, or high. | Base this on the current lane and observed work: synthetic, checked-in media, local representative media, or full-file/soak work. |
| Environment sensitivity | Deterministic, checked-in fixture, local asset/tool, or remote/timing dependent. | Record sensitivity separately from cost; a slow checked-in test can still be deterministic. |
| Proposed action | `keep`, `merge`, `parameterize`, `move`, or `remove`. | `merge` and `remove` require a named surviving case; `move` requires a named destination owner and lane. |
| Decision evidence | The comparable case, replacement command, and reason confidence remains intact. | Do not approve an action from similar setup, fixture names, or assertion syntax alone. |

Action meanings:

- `keep`: preserves distinct confidence or a clearer failure signal.
- `merge`: combines truly equivalent behavior into one readable test while
  retaining its current owner and lane.
- `parameterize`: keeps distinct inputs and expected outcomes in one test
  structure because they share the same boundary and diagnostic meaning.
- `move`: retains the behavior but relocates it to its correct owner or
  validation lane.
- `remove`: retires a case only after an equivalent named case demonstrably
  preserves its behavior, fixture intent, lane, and failure signal.

The behavior registry below records the current reviewed test families. A
proposed action is not approved until its decision evidence satisfies the
equivalence gate.

## Behavior And Failure-Signal Registry

The current 247 detector-related test functions are represented below at the
narrowest maintainable behavior-family level. A later cleanup decision must
name the exact node id or parameterized case it affects; this registry does
not authorize a file-wide action. A test family may exercise supporting seams,
but its failure signal records the earliest boundary it is meant to diagnose.

| Test scope | Observable behavior protected | Primary failure meaning | Cost | Environment sensitivity |
| --- | --- | --- | --- | --- |
| `test_detectors.py` | Built-in detector facts, supported modes, input handling, and registry exposure remain stable for controlled inputs. | Detector implementation or registration regression. | low | deterministic |
| `test_detectors_integration.py` | Production detectors retain their intended behavior on decoded checked-in media. | Decoder/media interpretation drift or detector regression outside synthetic inputs. | medium | checked-in-media dependent |
| `test_alert_rules.py` | Shared alert-rule entry, recovery, severity, and emitted alert shape follow detector facts. | Rule transition or alert-contract regression. | low | deterministic |
| `test_alert_rules_black.py` | Black-frame rule thresholds, suppression, recovery, and state handling remain stable. | Black-alert threshold or state-machine drift. | low | deterministic |
| `test_alert_rules_blur.py` | Blur-rule thresholds, guardrails, suppression, and recovery remain stable. | Blur-alert threshold or state-machine drift. | low | deterministic |
| `test_processor.py` | Core analyzer execution, slice/result propagation, and alert-bundle assembly remain coherent. | Processor integration or result-routing regression. | low | deterministic |
| `test_processor_context_alerts.py` | Contextual detector facts reach alert evaluation with the required shared context. | Context propagation or alert-assembly regression. | low | deterministic |
| `test_processor_failures.py` | Expected analyzer and input failures remain isolated and observable without corrupting the session path. | Failure-isolation or error-contract regression. | low | deterministic |
| `test_processor_routing.py` | Supported-mode and analyzer routing stay explicit and deterministic. | Analyzer-selection or mode-routing regression. | low | deterministic |
| `test_detector_lab.py` harness, fixture-set, cache, CSV, and CLI cases | Detector-lab accepts intended inputs, reuses safe cached context, resolves fixture sets, and exports readable comparison data. | Experiment-harness, fixture-resolution, cache, CLI, or export-contract regression. | low | deterministic; optional local baseline discovery |
| `test_detector_lab.py` experimental score and optical-flow cases | Experimental blur and motion score variants remain monotonic or fail closed under controlled synthetic facts. | Experimental scoring, trace aggregation, or fail-closed guardrail drift. | low | deterministic |
| `test_detector_lab.py` practical black/blur/motion guardrail cases | Practical policies retain black dominance, neighbor, structure, softness, coherence, and exact-threshold decisions. | Practical-policy threshold or precedence drift. | low | deterministic |
| `test_detector_lab.py` practical output and operator-message cases | Practical rows preserve optional metadata and expose stable operator-facing fields. | Experimental output-shape or diagnostic-message regression. | low | deterministic |
| `test_detector_lab_real_media.py` | Decoded checked-in fixtures preserve practical positive, suppression, precedence, sequence, flow-signal, and CSV behavior. | Media-decoding confidence or practical-policy drift on real frames. | medium | checked-in-media dependent |
| `test_detector_lab_representative_media.py` | Local representative compression and low-resolution cases remain broad calibration evidence without accidental promotion to exact truth. | Calibration, fixture-metadata, or promotion-boundary drift. | medium | local-asset and decoder-tool dependent |
| `test_representative_hls_test_support.py` | Representative catalogs, fixture resolution, HLS route maps, and promoted-truth references remain internally valid. | Fixture/catalog integrity or unavailable-local-asset handling regression. | low | deterministic; local assets skipped when absent |
| `test_e2e_local_session.py` | A minimal generated session reaches readable runtime output through the real local session boundary. | Core end-to-end session lifecycle regression. | low | deterministic |
| `test_e2e_local_session_real_media.py` | Checked-in media reaches the real session boundary with the intended runtime output and alert behavior. | Checked-in media runtime, persistence, or rule-integration regression. | medium | checked-in-media dependent |
| `test_e2e_local_session_representative_hls.py` | Reviewed local HLS baselines and artifacts preserve broad session behavior, MP4 agreement, and processing consistency. | Local HLS runtime, conversion, or representative-confidence drift. | medium-high | local-asset and decoder-tool dependent |
| Representative HLS and MP4 ground-truth suites | Reviewed representative subsets retain exact status, result, and alert expectations on their intended runtime seam. | Promoted exact-truth or session-output regression. | medium-high | local-asset and decoder-tool dependent |
| `test_e2e_local_session_representative_mp4_soak.py` capped cases | Capped representative MP4 runs preserve output shape and focused positive or false-positive guards. | Longer local runtime or representative-alert behavior regression. | medium-high | local-asset and decoder-tool dependent |
| `test_e2e_local_session_representative_mp4_soak.py` `@pytest.mark.soak` cases | Full-file sessions preserve completion, repeatability, interruption recovery, and long-baseline false-positive posture. | Long-run lifecycle, recovery, or environment-sensitive confidence regression. | high | local-asset and decoder-tool dependent |
| `test_e2e_session_ground_truth_api_stream.py` | Synthetic `api_stream` sessions retain reviewed exact end-to-end output. | `api_stream` runtime-contract regression independent of local media assets. | low | deterministic |
| `test_e2e_session_ground_truth_local.py` | Reviewed checked-in local-media sessions retain exact end-to-end output. | Exact checked-in media runtime or persistence regression. | medium-high | checked-in-media and decoder-tool dependent |
| `test_e2e_api_stream_representative_hls.py` | Reviewed local HLS inputs retain `api_stream` completion, ordering, cleanup, alignment, and bounded broad-alert behavior. | `api_stream` transport, temporary-file cleanup, or representative-runtime regression. | medium-high | local-asset, decoder-tool, and local-HTTP dependent |

This registry separates likely detector or rule regressions from fixture,
transport, runtime, and environment failures. Similar assertions become
cleanup candidates only when their behavior and primary failure meaning match
as well as their owner, fixture role, and validation lane.

Cost and sensitivity are routing evidence, not value scores. Checked-in media
belongs in its weekly lane; local representative, decoder-tool, and local-HTTP
dependencies belong in explicit local/manual confidence lanes. No inventoried
detector test currently depends on a remote live stream or remote timing.

## Comparable Test Groups

The following groups have enough behavioral similarity for cleanup review. A
shared fixture, setup helper, or boolean assertion does not make a group a
duplicate. Each group records the earliest boundary and failure signal that a
later consolidation decision must preserve.

| Group | Comparable behavior | Boundary and failure signal | Current classification | Next review unit |
| --- | --- | --- | --- | --- |
| Practical blur neighbor thresholds | `test_practical_blur_alert_v3_*neighbor_penalty*` cases at, below, and above the black-neighbor boundary, including score demotion. | Synthetic practical-policy evaluator; a failure means threshold, demotion, or strong-score escape drift. | Parameterization candidate. | Keep each input/outcome; assess one parameterized table or shared setup only. |
| Representative low-resolution black negatives | The standalone `test_representative_lowres_strong_end_stays_black_negative` assertion and the matching `stable-docs-strong-end` source-family matrix row. Moderate-start negative and motion-heavy calibration cases remain distinct. | Representative calibration; a failure means black-negative calibration or source-family coverage drift. | One consolidation candidate; otherwise intentional reinforcement. | Decide whether the source-family row can retain the standalone case's clear diagnostic message. |
| Capped and full-file MP4 runtime | Capped output-shape and alert guards versus full-file completion, repeatability, interruption/recovery, and baseline false-positive cases. | Runtime session behavior; capped failures diagnose practical output or alert regressions, while soak failures diagnose long-run lifecycle and recovery. | Intentional reinforcement. | Keep separate; compare only tests with the same runtime contract, selected detectors, and duration. |
| Calibration and exact truth | Representative detector-lab calibration expectations versus promoted HLS/MP4 and `api_stream` exact-truth suites. | Calibration versus reviewed runtime truth; failures mean score/promotion-boundary drift or exact session-output drift. | Intentional reinforcement. | Keep separate unless a reviewed exact-truth case replaces the same calibration claim without losing broad calibration evidence. |
| Synthetic and decoded black-transition guardrails | Practical motion-blur synthetic suppression tests and checked-in `test_detector_lab_real_media.py` black-recovery checks. | Synthetic policy versus decoded-media confidence; failures mean guardrail logic drift or decoder/media-boundary drift. | Intentional reinforcement. | Keep separate; no same-boundary candidate exists. |

No probable deletion candidate is recorded. The low-resolution strong-end case
is the sole candidate for later consolidation, subject to the equivalence rules
below. All other groups intentionally preserve different boundaries, fixture
roles, validation lanes, or failure signals.

## Equivalence Gate

Tests are removable or mergeable only when every gate passes: the same public
behavior, primary boundary, fixture intent, input variation, validation lane,
and comparably useful failure signal. A shared fixture or boolean result alone
does not pass any gate.

| Group | Gate result | Allowed next action |
| --- | --- | --- |
| Practical blur neighbor thresholds | Fails equivalent-input-variation: each case owns an edge, demotion, or escape outcome. | Parameterize shared setup only; retain every named case. |
| Low-resolution strong-end negative | Provisionally passes: both cases use the same fixture, start window, detector, calibration boundary, lane, and negative assertion. | Consolidate only after the source-family matrix keeps an equally clear strong-end failure signal and focused local validation passes. |
| Capped and full-file MP4 runtime | Fails public behavior, fixture intent, input duration, lane, and failure signal. | Keep separate. |
| Calibration and exact truth | Fails primary boundary, fixture intent, lane, and failure signal. | Keep separate. |
| Synthetic and decoded black-transition guardrails | Fails primary boundary, fixture intent, and validation lane. | Keep separate. |

A cleanup change must name the surviving test, explain how every gate remains
covered, and run the focused validation lane. Prefer parameterization or a
small shared helper when it removes setup repetition without erasing a distinct
input or diagnostic signal. The provisional low-resolution result is an
investigation target, not approval to modify a test in this documentation pass.

## Cleanup Action Queue

Each reviewed group has exactly one next action. These are bounded follow-up
items, not changes applied by this documentation task.

| Candidate | Action | Rationale and survivor | Focused validation |
| --- | --- | --- | --- |
| Practical blur neighbor thresholds | `parameterize` | The cases share one synthetic evaluator and setup shape, but each threshold, demotion, or escape outcome remains a distinct named input. Preserve case-specific IDs and assertion messages. | `just test-detector-lab` |
| Low-resolution strong-end negative | `merge` | Fold `test_representative_lowres_strong_end_stays_black_negative` into the `stable-docs-strong-end` case of `test_representative_lowres_source_family_matrix_stays_black_negative` only after preserving its dedicated diagnostic context. The source-family matrix is the named survivor. | Focused local representative-media test slice with the required assets and decoder tool. |
| Capped and full-file MP4 runtime | `keep` | Capped cases prove practical output and alert posture; soak cases prove completion, repeatability, interruption recovery, and long-baseline behavior. | Existing capped and soak lanes; local representative assets required. |
| Calibration and exact truth | `keep` | Calibration remains broad evidence, while exact truth is a reviewed runtime contract. Neither replaces the other. | Existing calibration and promoted-truth lanes. |
| Synthetic and decoded black-transition guardrails | `keep` | Synthetic tests isolate policy logic; decoded checked-in media tests prove the policy survives the media boundary. | `just test-detector-lab` and `just test-real-media` when real-media confidence is needed. |

No reviewed candidate has a `move` or `remove` action. A future cleanup PR
should implement at most the parameterization and conditional merge above, then
re-run this queue before considering any broader test reduction.

## Expected Cleanup Benefit And Risk

The non-`keep` actions are small maintenance improvements, not a material test
suite reduction. Ratings are qualitative and assume the named behavior cases,
markers, and validation lanes remain unchanged.

| Candidate | Maintenance reduction | Runtime reduction | Readability improvement | Confidence-loss risk | Priority |
| --- | --- | --- | --- | --- | --- |
| Practical blur neighbor thresholds (`parameterize`) | Moderate: centralizes repeated synthetic setup. | None: every input/outcome still runs. | Moderate: one behavior matrix makes threshold coverage easier to scan. | Low if parameter IDs and case-specific assertions remain readable; medium if a generic table hides the demotion or escape reason. | Medium. |
| Low-resolution strong-end negative (`merge`) | Low: removes one local representative invocation and duplicate setup. | Low: the surviving source-family case still decodes the same case. | Low to moderate: source-family coverage becomes the single owner. | Medium: a broad matrix failure can be less immediately diagnostic than the standalone test. | Low; perform only with local assets and a clear failing case ID. |

Neither action justifies changing routine CI, markers, fixtures, detector
thresholds, or the distinction between calibration and exact truth. Defer an
action when its readable failure signal cannot be retained; keeping a small,
clear test is preferable to a compact but opaque matrix.

## Validation And Frozen Follow-Ups

The queue was checked against the current repository evidence:

- the practical blur neighbor cases are in `tests/test_detector_lab.py`;
- the low-resolution standalone and source-family cases are in
  `tests/test_detector_lab_representative_media.py`;
- capped and full-file MP4 cases are in
  `tests/test_e2e_local_session_representative_mp4_soak.py`, with module-level
  `e2e` and `slow` markers and additional `soak` markers on long runs;
- checked-in real-media ownership is listed in
  `.github/ci_test_targets.json` under `weekly_slow_media`;
- `just test-detector-lab` owns synthetic detector-lab checks and
  `just test-real-media` owns checked-in detector-lab media checks.

The approved follow-ups for the next implementation change are limited to:

1. parameterize the practical blur neighbor setup while retaining every case
   ID and failure meaning;
2. conditionally merge the low-resolution strong-end case into the named
   source-family survivor after a focused local-media validation run.

No test deletion, marker change, fixture change, CI expansion, detector change,
or truth promotion is approved by this matrix review. Validation for
this documentation pass is `just docs-check` and `git diff --check`.

## Promotion Rules

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
