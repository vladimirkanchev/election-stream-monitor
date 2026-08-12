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

## Current Confidence Boundaries

Fast production covers synthetic detector facts, rule transitions, and
processor routing. Detector-lab experiments remain a separate synthetic lane.
Checked-in media supplies decoded detector and detector-lab proof; runtime E2E,
representative local media, soak, and external-stream confidence remain deeper
or manual layers. Use [testing-and-validation.md](./testing-and-validation.md)
to choose and run the corresponding lane.

## Validation Lane Vocabulary

Choose a lane by the boundary it protects, not only by whether it reads media.
For example, a checked-in MP4 can prove a decoded detector fact, a detector-lab
experiment, or a runtime session contract; those are separate confidence
claims.

| Lane | Meaning | Current command or owner | Excludes |
| --- | --- | --- | --- |
| Fast production | Synthetic detector facts, alert-rule transitions, and processor routing/persistence behavior. | `just test-detectors`, `just test-alert-rules`, and `just test-processor`; `just test-fast` is the wider application checkpoint. | Decoding, detector-lab policy, and session E2E behavior. |
| Fast experiments | Synthetic detector-lab runner, metrics, and practical-policy behavior. | `just test-detector-lab`. | Production-promotion and runtime session claims. |
| Checked-in real media | Decoded production-detector and detector-lab confidence against repository media, without session E2E. | `test_detectors_integration.py` and `just test-real-media`; both are `slow` and weekly-owned today. | Session lifecycle, persistence, and representative local assets. |
| Runtime E2E | Session discovery/loading, detector and rule execution, persistence, alerts, snapshots, and supported transport integration. | `test_e2e_*` owners; checked-in media is weekly and representative media is local/manual. | Fine-grained detector tuning. |
| Soak/manual | Long-running, repeatability, recovery, or environment-shaped confidence. | Selected `@pytest.mark.soak` cases and manual representative-media checks. | Fast deterministic regression guarantees. |
| External streams | Confidence against a live provider or stream outside repository control. | Manual confidence unless a deterministic fixture represents the relevant transport behavior. | A claim that synthetic or local HLS tests prove arbitrary providers. |

`just test-real-media` is the focused checked-in real-media lane. It runs the
decoded production-detector and detector-lab suites, while session E2E and
representative local media keep their separate owners.

### External-Stream Policy

Automated `api_stream` confidence uses synthetic events, generated playlists,
or checked-in HLS served through controlled local HTTP. It proves the runner
and transport contracts, not compatibility with an arbitrary external provider.
Test a real provider manually after the deterministic local checks; do not add
provider URLs, credentials, or timing-dependent expectations to routine CI.

## Production Detector Boundaries

Production detector tests own controlled facts and degradation behavior;
alert-rule tests own stateful transitions; processor tests own selection,
routing, persistence, and failure isolation; and checked-in decoded-media
tests provide a small production proof. One compact vertical processor case
may cross into rule evaluation to protect that seam, but it does not replace
rule-policy coverage.

Detector-lab separates runner/reporting, metric facts, practical blur policy,
and practical motion policy. Neutral constructors may be shared, but policy
fixtures, thresholds, and assertions stay with the owning behavior. Real-media
and representative calibration remain separate from synthetic experiments and
from production detector truth.

Each detector-related test has one primary category from the table above.
Secondary seams are useful evidence, not a second ownership claim. Use the
[testing guide](./testing-and-validation.md) for the current commands and
focused-suite membership.

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

## Fixture Availability

Checked-in media and versioned catalogs are required repository evidence;
missing files or unresolved promoted truth are defects. Representative MP4/HLS
binaries are local optional assets, so their absence is an expected skip while
catalog integrity remains deterministic. The catalog guards, not this document,
are the current source for changing counts and references.

## Real-Media Assertion Stability Matrix

This matrix classifies assertion families by the public behavior they protect.
It is the decision record for later stabilization work; a decoder-sensitive
row is not permission to weaken unrelated session, payload, or alert contracts.

| Owner and assertion family | Classification | Stability policy |
| --- | --- | --- |
| `test_detector_lab_real_media.py`: short blur-trigger windows and named guardrail reasons | Exact truth | Keep strict while the reviewed window boundary remains stable; inspect exported CSV diagnostics before changing a window or reason. |
| `test_detector_lab_real_media.py`: black-transition suppression and recovery | Presence/absence behavior plus bounded numeric invariant | Keep the reviewed black core strict; require bounded early suppression and later recovery while accepting either reviewed black-suppression reason around decoder-sensitive transition boundaries. |
| `test_detector_lab_real_media.py`: black-versus-blur precedence and later recovery | Ordered behavior with an exact reviewed blur core | Keep the blur-core precedence and recovery sequence strict; do not depend on one transient black-transition window unless that window is the contract. |
| `test_detector_lab_real_media.py`: optical-flow fields and score distinction | Payload-shape contract plus diagnostic-only calibration | Keep required fields, method names, and positive/distinct signals; do not promote raw score values to exact truth. |
| `test_detector_lab_real_media.py`: full CSV export | Payload-shape contract with an exact reviewed row | Keep schema, configured threshold, and normalized alert projection strict; classify any changed detector outcome through its row-specific real-media assertion before changing the export test. |
| `test_detectors_integration.py`: black and blur detection on checked-in MP4/TS media | Presence/absence behavior plus bounded numeric invariant | Keep detection decisions strict and use lower bounds for duration, ratio, samples, and streaks rather than decoder-specific exact measurements. |
| `test_e2e_local_session_real_media.py`: completed session, source coverage, detector set, and result counts | Ordered behavior and payload-shape contract | Keep playlist ordering, source names, selected-detector set, and results-per-input strict; these are runtime transport contracts. |
| `test_e2e_local_session_real_media.py`: real black media produces alerts | Presence/absence behavior | Require readable completed output, black detection, and at least one alert; alert multiplicity is not the owner of detector calibration. |
| `test_e2e_session_ground_truth_local.py`: generated and TS ground-truth cases | Exact truth | Keep status, progress, counts, ordered alerts, and selected key payload fields exact. |
| `test_e2e_session_ground_truth_local.py`: checked-in MP4 ground truth | Exact truth with one bounded numeric exception | Keep status, progress, result count, key payloads, and expected alerts strict. A case with positive `video_metrics` truth may add, but never lose, one `video_metrics` count and alert; blur-only and black-negative cases remain exact. |
| Representative calibration and soak suites | Diagnostic-only calibration or soak confidence | Keep their broad intent, score-shape, and long-run behavior separate from checked-in exact truth; they do not authorize changes to this matrix. |

Use the narrowest class that expresses the real contract. Decoder variation may
justify a named guardrail set or a small count range, never a wildcard result
count, unconstrained alert list, or broad exception handler. Inspect the
detector-lab CSV or focused failure diagnostic before changing an assertion.

### Exact And Behavioral Assertion Rules

1. Use exact windows only for reviewed, stable core windows or promoted exact
   truth with fixed fixture, mode, detector selection, and native subset
   boundaries.
2. Express a transition region through at least one stable anchor and one
   behavioral invariant: suppression presence, ordering, precedence, a minimum
   or maximum count, or a later recovery window.
3. A tolerance must name its fixture class, detector, affected field, numeric
   bound, and decoder cause. It may not apply to an entire test module or to
   unrelated detector output.
4. The only current exact-truth tolerance is checked-in MP4 black-detection
   variance: cases with a positive expected `video_metrics` count may add at
   most one `video_metrics` count and alert. Expected counts and alerts stay
   required and ordered; blur-only and black-negative cases have no tolerance.
5. A changed outcome first requires fixture availability and dependency checks,
   then the detector-lab CSV or focused diagnostics. Broaden a rule only after
   repeated evidence identifies a harmless decoder boundary shift.

## Real-Media Availability Matrix

The required fixture and dependency contract is per suite. Checked-in MP4 and
LFS-managed HLS media are shared test inputs; representative MP4/HLS binaries
are intentionally local-only while their manifest and truth metadata remain
versioned. See [fixture-environment-policy.md](./fixture-environment-policy.md)
for the repository-wide definitions.

| Suite | Media and generated inputs | Required environment | Missing prerequisite outcome |
| --- | --- | --- | --- |
| `test_detector_lab_real_media.py` | Checked-in MP4 fixtures. | Python detector-lab dependencies and OpenCV decode support; the flow case explicitly requires `cv2`. | Missing checked-in media is a defect. The flow case skips without `cv2`; a missing weekly decoder dependency is an environment failure. |
| `test_detectors_integration.py` | Checked-in MP4 and LFS-managed TS fixtures. | `ffmpeg`, `ffprobe`, and the installed detector stack. | The fixture skips locally when FFmpeg tools are absent. In weekly CI, missing tools are setup failure because the workflow installs a pinned package. |
| `test_e2e_local_session_real_media.py` | Checked-in MP4 and LFS-managed segment directories. | Installed runtime detector stack and decoder support. | Missing core media, LFS objects, or decoder support is a failure, not optional-media absence. |
| `test_e2e_session_ground_truth_local.py` | Checked-in MP4/TS cases plus generated media from `media_factory`. | `ffmpeg`/`ffprobe` for generated fixtures and the installed runtime stack. | Local runs skip through `media_factory` without FFmpeg; weekly absence is an environment failure. Missing checked-in inputs or truth references is a repository defect. |
| `test_detector_lab_representative_media.py` and representative MP4 exact/soak suites | Optional local representative MP4 corpus. | OpenCV/decode support; runtime suites also require FFmpeg tools. | Missing local MP4 assets skip through `require_representative_local_files()`. A present asset that cannot decode is a local-environment failure to investigate. |
| Representative HLS intent and exact-truth suites | Optional local HLS exports; some comparison cases also require their source MP4. | Decoder support and FFmpeg where the test declares `ffmpeg_available`. | Missing local assets skip through the representative helpers; catalog/reference failures remain defects. |
| `test_e2e_api_stream_representative_hls.py` | Optional local HLS exports copied into a temporary playlist subset. | FFmpeg tools and a bindable loopback TCP port. | Missing HLS assets skip; restricted loopback environments skip through `_serve_local_hls()`. Do not treat either as a detector regression. |

`actions/checkout` uses `lfs: true` in the weekly workflow, and the current
checkout passes `git lfs fsck --pointers`. A local clone that has media-pointer
files rather than hydrated LFS segments must fetch LFS before running a
checked-in HLS lane.

When triaging a real-media failure, classify it in this order: fixture/catalog
defect, missing required weekly dependency, expected local-only skip,
loopback restriction, decoder-version variation, then detector/runtime
regression. This order avoids changing detector assertions to accommodate a
missing asset or tool.

Ground-truth failures print safe case and environment facts plus bounded result
data. `ESM_GROUND_TRUTH_ARTIFACT_DIR` additionally writes one sanitized JSON
report per case; the weekly job uploads these alongside detector-lab CSVs.
Full snapshots, raw paths, raw environment variables, and driver output are
excluded.

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

## Test Change Gates

The [testing guide's ownership table](./testing-and-validation.md#detector-validation-ownership)
owns lane selection. Add a test only when no existing test protects the same
observable behavior, primary boundary, fixture intent, and lane. Remove, merge,
or parameterize a test only when those dimensions and its useful failure signal
remain covered by a named survivor. Shared setup or fixtures alone are not
evidence of duplication.

Prefer parameterization or a small helper when it removes repeated setup while
keeping each distinct boundary outcome readable. Checked-in media belongs in a
deeper lane; representative, decoder-tool, local-HTTP, and external-stream
confidence remain explicit local/manual concerns rather than low-value copies
of fast tests.

## Production Detector Coverage Matrix

This matrix records the current evidence for the two shipped detectors. A
`candidate` identifies a question for focused follow-up, not approval to add a
test. Rule and runtime rows deliberately name their own boundaries: they do
not substitute for direct detector-fact coverage.

| Behavior | `video_metrics` | `video_blur` | Owner and decision |
| --- | --- | --- | --- |
| Synthetic positive | Covered by `test_analyze_video_metrics_returns_expected_schema`. | Covered by `test_analyze_video_blur_exports_summary_window_fields`. | Direct detector facts; fast synthetic lane. |
| Synthetic clean negative | Covered by `test_analyze_video_metrics_returns_clean_negative_for_valid_media_output`. | Covered by `test_analyze_video_blur_returns_expected_schema` with sharp sampled frames. | Direct detector facts; fast synthetic lane. |
| Decoded-media positive | Covered by checked-in MP4 and TS black-trigger cases. | Covered by the checked-in blurred MP4 case. | `test_detectors_integration.py`; weekly slow-media lane. |
| Decoded-media clean negative | Covered by direct `blur_trigger.mp4` analysis with no black intervals. | No reviewed clean negative exists: the checked-in clean baseline is currently blur-positive by truth. | `test_detectors_integration.py` owns the direct black-negative fact. Do not invent a blur-negative claim. |
| Malformed media-tool response | Covered for invalid FFprobe output, malformed `blackdetect` lines, and timeout. | Covered for malformed FFprobe dimensions and stream containers, FFmpeg timeout, and non-zero exit. | Direct detector facts; fast synthetic lane. |
| Suppression and transitions | Covered by black-rule entry, recovery, and malformed-row tests. | Covered by blur-rule warm-up, motion guard, suppression, and recovery tests. | `test_alert_rules*.py` owns stateful policy; do not duplicate it in detector facts. |
| Runtime propagation | Checked-in real sessions cover `video_files` and `video_segments`; representative local HLS runs the shipped detector through `api_stream`. | Same runtime evidence. | `test_e2e_local_session_real_media.py` owns checked-in decoded sessions, `test_e2e_api_stream_representative_hls.py` owns optional local HTTP/HLS execution, and synthetic `api_stream` truth isolates deterministic runtime behavior. |

Do not add a detector-by-mode cross-product: registry support is shared, while
processor and session tests own selection and propagation. Checked-in
`video_files` and `video_segments` sessions are the routine decoded proof;
the local `api_stream` suite is optional real-transport confidence, and its
synthetic companion owns deterministic transport behavior. Alert-rule state
belongs in `test_alert_rules_black.py` and `test_alert_rules_blur.py`;
`test_detector_lab_real_media.py` owns practical experimental transitions.

### Deferred Local Blur-Negative Candidate

Historical calibration observation (2026-07-29): the local
`stable_docs__source_baseline` case remains calibration evidence, not
production truth. Three detector-lab runs of windows `0..7`
produced no `practical.blur_alert_v3` detections (scores `0.910..0.945` versus
that policy's `0.955` threshold), but three direct production
`analyze_video_blur()` runs over the canonical `stable_docs` source slice
(`0..8s`) returned `blur_detected=True` at `0.914` against `0.880`.

The source MP4 is local-only and practical detector-lab policy is not
production detector truth. Keep it as a known false-positive calibration
candidate; do not add a passing or deliberately failing CI assertion. Promote
only a short, reviewed, versioned subset after production runs stay negative
with a documented threshold margin across relevant decoder environments.

## Evidence Limits

Fast CI is not evidence for decoded media, representative assets, or end-to-end
behavior. Checked-in slow media is scheduled confidence; representative HLS/MP4
and live external streams remain local/manual where their dependencies are not
deterministic. Missing local representative assets should skip rather than
weaken detector assertions.

This document records current confidence policy, not a cleanup queue or test
count target. Use [testing-and-validation.md](./testing-and-validation.md) for
commands and [detector-lab-analysis.md](./detector-lab-analysis.md) for
experimental-analysis intent.
