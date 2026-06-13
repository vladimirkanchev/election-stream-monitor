Failing checks:
- `backend-tests`
- `feature-gate`

Most likely failure class:
- `stale test or expectation`

Owning boundary:
- production detector/rule runtime lane
- specifically the focused backend pytest slice behind `just test-fast`

Evidence for it:
- the first failing leaf check is `backend-tests`, while `feature-gate` is only summarizing it
- the error message shows an assertion mismatch rather than an import, syntax, or missing-tool failure
- the repo already has focused detector/rule test lanes, so the cheapest reproduction should stay narrow

Evidence against it:
- if the log also shows `No such file or directory` for `.venv/bin/pytest`, this would be an environment issue instead
- if the failure comes from `check_ci_target_drift.py`, the class would move toward CI or policy drift

Smallest local reproduction:
- `just test-fast`
- if the failure text names one production seam more narrowly, use `just test-detectors` or `just test-alert-rules`

Best next fix:
- reproduce the failing assertion locally in the focused lane
- decide whether the intended runtime behavior changed or the test expectation drifted
- update the nearby test or fixture only if the new behavior is intentional
