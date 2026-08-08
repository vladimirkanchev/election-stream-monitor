---
name: incident-analysis
description: Use for Election Stream Monitor timeline reconstruction when order is unclear or evidence-backed root-cause hypotheses. Excludes first-pass CI triage and generic summaries.
---

# Incident Analysis

Use one investigation mode. Do not produce a long timeline and a root-cause
analysis unless both are necessary to resolve the uncertainty.

## Default approach

Collect the shortest evidence that changes the diagnosis:

1. error text, logs, or CI status
2. session artifacts such as `session.json`, `progress.json`, `alerts.jsonl`,
   `results.jsonl`, and `worker.log`
3. nearest route, service, runner, bridge, or workflow code

Choose one mode:

- **Timeline mode**: use when event order, ownership transitions, or the first
  visible symptom are unclear.
- **Hypothesis mode**: use when the evidence can support one likely cause and
  one cheap validation step.

Keep observed facts separate from inference. Name the owning boundary when the
incident crosses frontend, bridge, API, worker, persistence, loader, or GitHub
policy.

## Output shape

For timeline mode, use:

1. `Observed facts`
2. `Reconstructed sequence`
3. `Trigger`
4. `First visible symptom`
5. `Backend events`
6. `Frontend events`
7. `Persistence/session-file events`
8. `Terminal state`
9. `Unknowns still left`

For hypothesis mode, use:

1. `Most likely root cause`
2. `Confidence`
3. `Evidence for it`
4. `Evidence against it`
5. `Cheapest next validation`

If a second hypothesis is genuinely competitive, keep it shorter than the
first. Do not call a visible symptom a root cause.

## Project-specific rules

- Distinguish start accepted, worker started, first session snapshot persisted,
  and frontend read behavior when session startup is involved.
- State when a transient 404, cache state, or GitHub policy/state evaluation is
  likely by design rather than a product failure.
- Prefer one strong cause over a list of weak guesses.
- Use a focused existing command or status check as the cheapest validation;
  do not default to a full-suite rerun.

## Skill boundaries

- Use `ci-failure-triage` first when a failing CI check needs classification or
  a smallest local reproduction.
- Use this skill when the CI, runtime, or UI incident still needs sequence
  reconstruction or an evidence-backed cause.
- Use `summarization` for a generic repository or change summary rather than
  incident investigation.
- Use `test-strategy-review` after the cause is understood and the remaining
  question is missing confidence.

## Good fit examples

- session starts but UI falls back to idle
- session start succeeded but the first read returned 404
- PR is green but merge remains blocked
- branch protection or CI merge state has conflicting signals

## Avoid

- mixing likely statements into factual timeline entries
- producing both modes by default
- listing many low-confidence causes
- turning an incident investigation into a generic change summary
