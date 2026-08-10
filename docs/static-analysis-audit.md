# Static Analysis Ownership

Role: **readiness and ownership evidence**. Status: **active**.

This record owns current static-analysis scope, enforcement, and named gaps.
Use [testing-and-validation.md](./testing-and-validation.md) for local
commands and [ci-maintainer-guide.md](./ci-maintainer-guide.md) for protected
versus advisory CI policy. It does not select new rules or apply
repository-wide formatting.

## Current Ownership

| Tool | Current target and command | CI status | Baseline |
| --- | --- | --- | --- |
| Ruff lint | `src`, `scripts`, and `tests` (262 Python files); `just lint-backend` | Protected through `backend-ruff`. | No findings with `E4`, `E7`, `E9`, `F`, `I`, `UP`, and `B`. |
| Ruff formatter | Same Python tree; `just format-check`. | Not enforced. | Would reformat 158 files; 104 already match Ruff formatting. |
| Black | Installed in the `lint` extra. | Not invoked. | Outside the selected formatter contract. |
| Mypy | Curated 40-file backend contract list; `just typecheck-backend`. | Protected through `backend-typecheck`. | No issues. |
| Pyright | The same curated backend list in basic mode; `just typecheck-advisory`. | Advisory through `backend-pyright`. | No errors, warnings, or informational findings. |
| ESLint | Renderer TypeScript plus Electron `.mjs`; `just lint`. | Renderer lint is protected through `contract-checks`; combined frontend lint is advisory. | Clean. |
| TypeScript | Frontend project references; `npm --prefix frontend run typecheck`. | Protected through `frontend-typecheck`. | No findings. |

Electron `.mjs` production and test files use Node globals under a separate
ESLint scope. TypeScript does not substitute for JavaScript linting at that
process, IPC, filesystem, and local-network boundary.

## Frozen Ownership Policy

| Concern | Owner | Enforcement |
| --- | --- | --- |
| Python lint and import quality | Ruff | Protected. |
| Python formatting | Ruff formatter | Deferred until the mechanical baseline is clean. |
| Primary Python typing | Mypy | Protected. |
| Secondary/editor Python typing | Pyright | Advisory. |
| Renderer and Electron JavaScript quality | ESLint | Renderer lint is protected; Electron lint is advisory. |
| Frontend typing | TypeScript | Protected. |
| Security scanning | Bandit and dependency audits | Separate security lane. |

Ruff is the selected Python formatter as well as the linter. Black remains an
installed but unused transition dependency until the dedicated formatting pass
is complete.

## Formatter Contract

Ruff format uses the shared `pyproject.toml` Python 3.12 target and 88-column
line length. `just format-check` checks `src`, `scripts`, and `tests` without
changing files. `just format` applies the same formatter and is reserved for a
dedicated mechanical commit, not a behavior change.

`tests/test_ci_workflow.py` protects the current lint/type ownership: Ruff and
Mypy remain protected, while Pyright and combined frontend lint remain
advisory. The formatter recipe is covered as a local contract; CI enforcement
is deferred until the mechanical baseline is clean.

The measured baseline is 158 files requiring reformatting and 104 already
formatted files. The baseline must be applied as one separately reviewable
change before the formatter check becomes protected in CI.

## Current Ruff Rule Policy

`I`, `UP`, and `B` are clean without unsafe fixes or broad rule exclusions.
The only suppressions are five line-level `B008` exceptions for FastAPI
`Depends` or `Query` declarations; those framework defaults define request
binding rather than normal function-default behavior.

Local aggregate commands are contributor quality signals, not GitHub
protection declarations. `just typecheck` currently runs protected Mypy and
TypeScript checks plus advisory Pyright, so a local failure requires review but
does not promote Pyright to a merge blocker. Use the explicit protected or
advisory recipe when those outcomes need to stay separate.

## Current Gaps

1. Formatter enforcement is deferred pending the dedicated Ruff baseline.
2. Ruff now checks import order, Python 3.12 modernization, and selected
   correctness patterns. Complexity, simplification, annotations,
   documentation, and Ruff-specific style rules remain deliberately deferred.
3. Mypy and Pyright protect a reviewed backend subset, not all Python modules.
   `.github/backend_typecheck_targets.txt` owns the shared 40-file target set.
   The first expansion covers API policy support plus the analyzer/detector
   boundary. The remaining full-source Mypy findings are limited to playlist
   parsing and collection, the legacy entrypoint, and CLI payload conversion;
   each is a separate reviewed family. Pyright is advisory in CI, but its
   failure currently makes the local `just typecheck` aggregate fail.
4. Electron JavaScript now has Node-aware ESLint coverage in the advisory
   frontend lint job. Keep the scope clean before considering promotion to the
   protected PR lane.

## Follow-Up Boundary

Complete the dedicated Ruff formatting baseline before enforcing it or removing
Black. Expand Ruff rules and the reviewed typecheck set in small groups, and
promote Electron lint only after it remains clean in advisory CI. Keep
dependency upgrades, security-scanner expansion, and feature work separate.
