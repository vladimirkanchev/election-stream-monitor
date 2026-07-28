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
| Processor/runtime integration | `test_processor_context_alerts.py`, `test_processor_failures.py`, `test_processor_routing.py` | none | temporary inputs, synthetic registrations, in-memory stores | fast synthetic; `just test-processor` | low |
| Detector-lab experiments | `test_detector_lab_runner.py`, `test_detector_lab_metrics.py`, `test_detector_lab_practical_blur.py`, `test_detector_lab_practical_motion.py` | none | synthetic slices, temporary CSVs, checked-in fixture metadata; optional local baselines | `just test-detector-lab`; fast synthetic | low |
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

## Production Detector Boundaries

The category and inventory tables above are the ownership source of truth. The
following rules keep production confidence focused:

- `test_detectors.py` owns controlled detector facts and degradation behavior.
- `test_alert_rules*.py` owns rule entry, suppression, recovery, and re-entry.
- `test_processor_routing.py`, `test_processor_context_alerts.py`, and
  `test_processor_failures.py` own registration selection, normalized-row
  handoff, store routing, and failure isolation.
- `test_detectors_integration.py` owns a small weekly decoded-media proof for
  black and blur detection; it does not calibrate rules or session behavior.

Processor tests usually replace rule evaluation so they test only processor
handoff. One compact vertical case uses the real black-screen rule to verify a
detector result reaches its store and produces a bundle alert. Keep detailed
rule thresholds and state transitions in `test_alert_rules*.py`.

`just test-processor` runs the three processor owners and collects 19 cases.
The legacy processor suite was consolidated into them; the current eight-file
production boundary set collects 93 cases.

## Synthetic Detector-Lab Baseline

Before the split, revision `8801e5d8f5f2ab6731075121bd428a7bfc2c706b` kept
the synthetic suite in `tests/test_detector_lab.py`: 3,300 lines, 77 named
test functions, and 81 collected cases. The current four-file suite retains
81 cases; compare test-name suffixes and parameter IDs rather than file
prefixes when reviewing the historical baseline.

The deleted baseline file is available through that revision when historical
node IDs are needed. Current validation uses `just test-detector-lab`.

The split preserves these synthetic behavior groups:

- runner, CLI, fixture-set, batch, CSV/export, and ground-truth reporting
- blur blends, optical-flow exports, motion-coherence metrics, and fail-closed
  metric behavior
- practical black and blur policy, including dark and black-neighbor boundaries
- practical motion policy, including transition guardrails, coherence,
  softness, persistence, final thresholds, and operator-facing evaluation rows

No real-media, representative-media, production detector, or runtime test is
part of this structural baseline. Those owners remain separate confidence
layers.

## Synthetic Detector-Lab Test Ownership

The synthetic suite is split by the behavior under review, not by source
import or by the order tests happened to accumulate. These four files remain
the complete synthetic detector-lab owner set and continue to run through the
focused `test-detector-lab` lane.

| Target file | Primary responsibility | Includes | Excludes |
| --- | --- | --- | --- |
| `tests/test_detector_lab_runner.py` | Runner and reporting contracts. | CLI parsing, fixture-set selection, batch and split-batch execution, CSV profiles, ground-truth lookup, and output-row formatting. | Experimental metric calculations and practical detection decisions. |
| `tests/test_detector_lab_metrics.py` | Experimental metric facts. | Blur blends, optical-flow trace/export behavior, motion-coherence metrics, score monotonicity, and fail-closed metric inputs. | Practical alert thresholds, guardrails, and reporting/CLI behavior. |
| `tests/test_detector_lab_practical_blur.py` | Black and blur practical-policy decisions. | Shared practical fact caching, black dominance, dark-frame and neighbor suppression, blur v2/v3 thresholds, structure escapes, and blur-to-motion handoff. | Motion-blur scoring, persistence, coherence, and final motion policy thresholds. |
| `tests/test_detector_lab_practical_motion.py` | Practical motion-blur policy decisions. | Black-transition guardrails, softness, persistence, coherence, mixed-boundary behavior, final thresholds, and motion-specific evaluation context. | Blur v2/v3 decision policy and runner/export behavior. |

`evaluate_practical_alerts()` output-shape and operator-message checks belong in
the runner/reporting file. They protect the exported alert representation, not
whether a blur or motion policy decided to alert.

`tests/detector_lab_test_support.py` owns only neutral data constructors used
across these files: `black_metrics_row`, `fake_slice`, `fake_blur_context`,
and `fresh_practical_evaluation_context`. Runner-only ground-truth patches,
policy patches, threshold tables, and inline fakes remain with their policy
owner. The support module must not contain tests, assertions, file discovery,
or CSV expectations.

The split intentionally changes test file prefixes. Test names and readable
parameter IDs should remain stable unless a later approved parameterization
change replaces repeated setup without removing a boundary case.

`just test-detector-lab` explicitly runs the four owners above, so moved tests
remain in the focused synthetic lane.

## Primary Assignments

Each row covers every test in the named file unless a marker-qualified subset
is specified. Secondary seams explain useful cross-layer coverage; they do not
make a test a duplicate of its primary owner.

| Files or subset | Primary owner | Secondary seams |
| --- | --- | --- |
| `test_detectors.py` | Production detector facts | detector registration and supported-mode exposure |
| `test_detectors_integration.py` | Production detector facts | checked-in media confidence |
| `test_alert_rules.py`, `test_alert_rules_black.py`, `test_alert_rules_blur.py` | Production alert rules | detector-fact inputs |
| `test_processor_context_alerts.py`, `test_processor_failures.py`, `test_processor_routing.py` | Processor/runtime integration | detector registration, result storage, alert-bundle assembly |
| `test_detector_lab_runner.py`, `test_detector_lab_metrics.py`, `test_detector_lab_practical_blur.py`, `test_detector_lab_practical_motion.py` | Detector-lab experiments | fixture metadata and export contracts |
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

The same media may support several confidence layers without making those
layers interchangeable. Use these terms consistently:

| Term | Meaning | Owner | Must not be read as |
| --- | --- | --- | --- |
| Fixture identity | What media exists and how it relates to a source, artifact, or transport export. | Fixture corpus or `representative/manifest.json`. | A detector-quality claim. |
| Broad intent | A condition is `expected`, `not_expected`, `threshold_dependent`, or `borderline_or_metric_only` for a representative case. | `representative/expected_results.json`. | Exact alert counts, positions, or a universal detector guarantee. |
| Calibration evidence | Score shape, threshold, false-positive, or diagnostic behavior used to tune or review a detector. | Detector-lab representative tests. | A reviewed runtime contract. |
| Exact truth | Stable status, result, and alert output for one deliberately reviewed runtime subset. | `ground_truth.json`. | A claim about the whole source fixture or every transport. |
| Soak confidence | Long-run completion, repeatability, recovery, or baseline behavior. | Soak/manual tests. | Detector truth or routine CI confidence. |

`expected` and `not_expected` remain broad intent values. Only a linked,
reviewed `ground_truth.json` case makes a subset exact.

`representative/manifest.json` is the canonical identity catalog for
representative media: MP4 fixture IDs and paths, source relationships,
artifact metadata, and MP4-to-HLS derivation. Source fixtures intentionally
carry baseline metadata while derived fixtures carry artifact metadata;
consumers must use the shared catalog lookup rather than flattening those
shapes into one synthetic schema. Intent and truth catalogs may repeat stable
references for integrity checks, but do not own fixture identity.

HLS expectation rows contain only detector intent, review tier, selected
detectors, notes, and truth linkage. Their `_hls` case IDs resolve to the
canonical HLS fixture ID by removing that suffix; transport paths, playlist
details, segment counts, and artifact timelines remain manifest-only.

Promoted MP4 and HLS truth descriptors use nonblank canonical fixture IDs and
subset names with nonnegative, unique, ascending indices. HLS indices select
playlist segments; MP4 indices select detector windows. They can be compared
through the manifest source relationship, but their numeric boundaries are not
interchangeable.

| Fixture source | Identity owner | Expectation or truth owner | Consumers and distinct proof |
| --- | --- | --- | --- |
| Generated inputs, temporary files, synthetic analyzer rows | individual test setup and `media_factory` | inline test assertions only | detector, rule, processor, detector-lab synthetic, and small E2E smoke tests prove deterministic contracts without making media-quality claims |
| Checked-in core media: `tests/fixtures/media/video_files/` and `video_segments/` | repository fixture corpus | `video_file_second_labels.json` supplies per-second detector-lab context; selected session cases in `ground_truth.json` supply exact truth | detector integration proves production detector behavior; detector-lab real-media proves experiment behavior; curated E2E proves runtime processing; local ground-truth tests prove selected exact session output |
| Representative media paths and HLS exports: `representative/manifest.json` | representative manifest and local asset paths | none by itself | catalog guards prove reference integrity; runtime, transport, calibration, and soak tests select reviewed MP4/HLS subsets from the same identities |
| Representative intent: `representative/expected_results.json` | representative manifest identifies the source | expectation catalog owns broad positive, negative, and borderline intent | detector-lab representative tests prove score/false-positive calibration; representative E2E and capped MP4 tests prove broad runtime behavior without asserting exact counts |
| Promoted exact truth: `tests/fixtures/media/ground_truth.json` | fixture metadata identifies generated, checked-in, or representative inputs | ground-truth cases own exact status, result, and alert expectations for reviewed subsets only | synthetic `api_stream`, local real-media, representative HLS, and representative MP4 exact-truth tests prove stable session outputs; catalog guards prove promoted references resolve |

## Fixture Baseline

This snapshot is the starting point for fixture and truth normalization. It
records catalog structure, not detector-quality results.

| Surface | Current baseline | Availability | Primary consumers |
| --- | --- | --- | --- |
| Generated inputs | Test-local `media_factory` outputs; no persisted catalog count. | Deterministic during the owning test. | Synthetic detector, rule, processor, and small E2E tests. |
| Checked-in MP4 media | 9 files in `video_files/`. | Required repository fixtures. | Detector integration, detector-lab real-media, and local exact-truth tests. |
| Checked-in HLS media | 10 fixture directories with 89 `.ts` segments in `video_segments/`. | Required repository fixtures. | Segment, `api_stream`, and local runtime confidence. |
| Representative MP4 catalog | 54 entries in `representative/manifest.json`. | Local optional corpus; not required in clones or CI. | Calibration, representative runtime, exact-truth, and soak tests. |
| Representative HLS catalog | 8 exports in `representative/manifest.json`. | Local optional corpus; not required in clones or CI. | Transport, representative runtime, and exact-truth tests. |
| Representative intent | 62 cases in `representative/expected_results.json`. | Versioned metadata. | Calibration and broad runtime-intent tests. |
| Promoted representative exact truth | 13 cases in `ground_truth.json`: 8 HLS and 5 MP4 subsets. Ten are catalog-linked through `exact_ground_truth_case_id`; three MP4 detector-specific cases remain direct runtime truth because one fixture can support more than one reviewed detector contract. | Versioned metadata; runtime execution also needs local assets. | Representative exact-truth tests and catalog guards. |
| Focused catalog/calibration/truth collection | 59 cases across catalog guards, representative calibration, and representative MP4/HLS exact-truth modules. | Collection is deterministic; local-media execution skips when assets are absent. | Fixture/truth normalization validation. |

Missing local representative MP4 or HLS assets are an expected skipped-test
condition. Missing checked-in media, invalid catalog references, or unresolved
promoted truth are repository defects.

Routine catalog guards validate IDs, safe relative paths, source relationships,
allowed intent values, summary counts, truth references, and subset ordering.
They do not open representative media or run detectors.

Every catalog `exact_ground_truth_case_id` must resolve to one completed
runtime case with the same fixture, transport, reviewed subset length, and
compatible detector selection. The representative MP4 exact-truth matrix also
contains three direct cases without that catalog pointer; its parameterized
runtime test remains their evidence owner. Do not promote a calibration or
environment-sensitive result merely because it currently passes.

## Exact-Truth Promotion And Demotion

Promote a representative subset to exact truth only when all of the following
are reviewed in the same change:

- the media is cataloged and its MP4/HLS fixture identity and source relation
  are unambiguous;
- the subset has deterministic, ordered boundaries in the transport's native
  unit: HLS segments or MP4 detector windows;
- repeated runs on the reviewed local environment produce the same selected
  public fields, with any decoder or fixture variation investigated first;
- the truth records only stable session/status, progress, result, and alert
  fields needed by the contract, not diagnostic scores or incidental payloads;
- a parameterized exact-runtime test owns the case in the appropriate local
  HLS or MP4 validation lane, and catalog links are added when the current
  single-reference metadata can express the relationship.

Promotion evidence belongs in the change review and the owning runtime test;
the catalog guards protect the recorded reference shape afterward. A passing
calibration test, a broad intent value, or one successful local run is not
enough to create exact truth.

Demote a case to calibration when repeated runs are unstable, a detector or
runtime contract intentionally changes, or the asserted output depends on an
uncontrolled decoder, timing, or environment condition. First investigate a
single unexpected failure; do not demote merely to hide a regression. A
demotion removes the exact assertions and catalog link as needed, but keeps
the fixture and its broad intent or calibration evidence with a short reason.
It is a narrower claim, not deletion of useful detector evidence.

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
| `test_processor_context_alerts.py` | Typed detector rows and contextual facts reach persistence and alert evaluation with the required shared context. | Typed-row boundary, context propagation, or alert-assembly regression. | low | deterministic |
| `test_processor_failures.py` | Expected analyzer and input failures remain isolated and observable without corrupting the session path. | Failure-isolation or error-contract regression. | low | deterministic |
| `test_processor_routing.py` | Supported-mode, shipped-registry, and analyzer routing stay explicit and deterministic. | Registry-selection or mode-routing regression. | low | deterministic |
| `test_detector_lab_runner.py` | Detector-lab accepts intended inputs, reuses safe cached context, resolves fixture sets, and exports readable comparison data. | Experiment-harness, fixture-resolution, cache, CLI, or export-contract regression. | low | deterministic; optional local baseline discovery |
| `test_detector_lab_metrics.py` | Experimental blur and motion score variants remain monotonic or fail closed under controlled synthetic facts. | Experimental scoring, trace aggregation, or fail-closed guardrail drift. | low | deterministic |
| `test_detector_lab_practical_blur.py` | Practical black and blur policies retain dominance, neighbor, structure, and exact-threshold decisions. | Practical blur-policy threshold or precedence drift. | low | deterministic |
| `test_detector_lab_practical_motion.py` | Motion policy retains black-transition, softness, coherence, persistence, and exact-threshold decisions. | Practical motion-policy threshold or precedence drift. | low | deterministic |
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
items, not changes applied by this review.

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

- the practical blur neighbor cases are in
  `tests/test_detector_lab_practical_blur.py`;
- the low-resolution standalone and source-family cases are in
  `tests/test_detector_lab_representative_media.py`;
- capped and full-file MP4 cases are in
  `tests/test_e2e_local_session_representative_mp4_soak.py`, with module-level
  `e2e` and `slow` markers and additional `soak` markers on long runs;
- checked-in real-media ownership is listed in
  `.github/ci_test_targets.json` under `weekly_slow_media`;
- `just test-detector-lab` owns synthetic detector-lab checks and
  `just test-real-media` owns checked-in detector-lab media checks.

The remaining approved follow-up is limited to conditionally merging the
low-resolution strong-end case into the named
   source-family survivor after a focused local-media validation run.

The practical-blur neighbor parameterization is implemented in
`tests/test_detector_lab_practical_blur.py`. Its five IDs retain the strong
transition, exact boundary, just-below boundary, score-demotion, and
strong-score escape outcomes as separate synthetic cases.

No test deletion, marker change, fixture change, CI expansion, detector change,
or truth promotion is approved by this matrix review. Validation for
this documentation pass is `just docs-check` and `git diff --check`.

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
