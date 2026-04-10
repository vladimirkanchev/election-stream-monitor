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
- detector-to-rule mapping
- small session-local rolling state
- logging and failure context around rule evaluation

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

Good for:

- video segments
- stream-like behavior
- future API stream chunks

## Basic rule shape

Current rule style is:

- one small `AlertRule`
- one readable predicate
- one readable message builder
- optional helper functions for rolling state
- explicit rule id metadata when the rule is part of the built-in catalog

Try to keep rules:

- cheap
- readable
- easy to tune
- easy to test

## How to add one

### Step 1: decide what detector output you need

Before writing a rule, make sure the detector already returns the right fields.

Examples:

- `black_detected`
- `longest_black_sec`
- `black_ratio`
- `blur_score`
- `threshold_used`

If the detector output is not good enough, fix the detector first.

### Step 2: decide whether the rule is stateless or rolling

Use stateless if possible.

Use rolling state only when the alert really depends on recent history and not just one file or segment.

### Step 3: add the rule

In [`src/alert_rules.py`](../src/alert_rules.py):

- create the rule
- add it to the detector-to-rule mapping
- keep the message clear for the frontend user

### Step 4: if it uses rolling state, keep that state local

If a rule needs memory:

- keep it inside the rule layer
- key it by session id
- reset it at session boundaries
- do not make the processor responsible for rule-specific state

That reset currently happens from [`src/session_runner.py`](../src/session_runner.py).

### Step 5: test it

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
