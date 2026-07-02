# Adding an Alert Rule

This document explains the safest current way to add a new alert rule in the
project.

It is aimed at contributors and coding agents working with the current
`alert_rules.py` implementation.

Read first if needed:

- [adding-an-analyzer.md](./adding-an-analyzer.md)
- [data-models.md](./data-models.md)
- [contracts.md](./contracts.md)

## Keep this split

In this repo:

- detectors compute facts
- alert rules decide whether those facts should become alerts

Do not mix those two layers unless there is a very strong reason.

## Main file

- [`src/alert_rules.py`](../src/alert_rules.py)

This is where alert logic should live.

It already contains:

- built-in rule metadata with stable ids
- detector-specific evaluator registration on each built-in rule
- small session-local rolling state
- a typed runtime row boundary for rule evaluation
- logging and failure context around rule evaluation

Important boundary:

- [`src/alert_rules.py`](../src/alert_rules.py) is the production runtime
  alert-rule catalog
- [`detector_lab/practical_alerts.py`](../detector_lab/practical_alerts.py)
  contains detector-lab evaluation policies

Those practical detector-lab alerts are useful for experimentation and
comparison, but they are not part of the supported runtime alert catalog
unless they are promoted intentionally.

## Two kinds of rules

### 1. Stateless rules

These are the simplest ones.

Examples:

- `black_detected is True`
- `blur_score >= threshold`
- `missing_audio is True`

Good for:

- image checks
- simple per-file checks
- easy-to-explain thresholds

### 2. Rolling rules

These use a small amount of session-local state.

Current example:

- video black-screen rule
  - immediate condition: long continuous black interval
  - rolling condition: recent black ratio over a short window
- blur rule
  - requires enough total samples before first entry
  - uses detector-side motion summaries to suppress camera-motion softness

Good for:

- video segments
- stream-like behavior
- future API stream chunks

## Basic rule shape

Current rule style is:

- one small `AlertRule`
- one readable rule entry point
- one readable message builder
- typed facts when detector payloads need interpretation
- small helpers for rolling state and row annotation
- explicit rule id metadata when the rule is part of the built-in catalog

Try to keep rules:

- cheap
- readable
- easy to tune
- easy to test
- focused on policy, not on detector-side signal extraction

## How to add one

### Decide what detector output you need

Before writing a rule, make sure the detector already returns the right fields.

Examples:

- `black_detected`
- `longest_black_sec`
- `black_ratio`
- `blur_score`
- `threshold_used`

If the detector output is not good enough, fix the detector first.

### Decide whether the rule is stateless or rolling

Use stateless if possible.

Use rolling state only when the alert really depends on recent history and not just one file or segment.

### Add the rule

In [`src/alert_rules.py`](../src/alert_rules.py):

- create one `AlertRule`
- attach the detector-specific evaluator callable to that rule
- add the rule to the built-in registration tuple
- keep the message clear for the frontend user

The current runtime shape is:

1. detector output is normalized into `RuntimeResultRow`
2. the rule derives typed facts if needed
3. the rule returns a decision and row-facing annotation
4. alert events are built only on fresh entry

Do not treat a practical detector-lab alert as a runtime rule just because the
policy shape looks similar. Promotion into the runtime should be explicit and
should update:

- [`src/alert_rules.py`](../src/alert_rules.py)
- [`src/detectors/registry.py`](../src/detectors/registry.py) if detector
  metadata or rule linkage changes
- runtime docs such as [architecture.md](./architecture.md)

### Keep rolling state local when needed

If a rule needs memory:

- keep it inside the rule layer
- key it by session id
- reset it at session boundaries
- do not make the processor responsible for rule-specific state

That reset currently happens from [`src/session_runner.py`](../src/session_runner.py).

### Test it

At minimum, add:

- one positive rule test
- one negative rule test
- one rolling-state test if needed

## Good rule examples for this repo

### Black screen

Good because it is:

- cheap
- easy to explain
- useful for local files and future streams

Current shape:

- alert on long continuous black interval
- or alert on high recent rolling black ratio

### Blur

Good because it uses:

- normalized score in `0..1`
- rolling windows
- readable threshold
- explicit recovery and re-alert behavior
- detector-side motion summaries only as policy inputs, not as replacements for
  the persisted blur score

## Things to avoid

Avoid:

- putting alert text inside detector code
- using hidden global mutable state outside the rule layer
- using many nested special cases in `processor.py`
- overcomplicating simple rules with framework-style abstraction
- assuming detector and alert-rule packaging means they should become one runtime contract

## Best order

If you are adding a new alert:

1. make sure detector output is good
2. add rule
3. add or update built-in rule metadata if the rule should appear in future catalogs
4. test rule
5. only then adjust frontend wording if needed

## Safe Edit Checklist

When changing an alert rule, review these together:

- the detector result fields the rule depends on
- alert event payload shape
- session snapshot and alert-feed expectations
- rule registration and catalog visibility
- tests for both emit and recover behavior

In practice, this usually means:

1. verify the detector result fields are stable and well named
2. keep rule thresholds and rule-state transitions explicit
3. confirm alert event fields still match frontend expectations
4. test both alert emission and recovery or clear paths
5. update docs if the meaning of the rule changes

This helps keep detector facts, rule interpretation, and frontend presentation
aligned.

Do not treat detector output and alert semantics as the same thing. The detector
measures facts; the alert rule decides when those facts should become an
operator-facing warning.
