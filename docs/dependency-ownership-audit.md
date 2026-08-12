# Dependency Ownership

Role: **readiness and ownership evidence**. Status: **active**.

This record owns Python dependency-source policy and the current consumer
classification. It distinguishes declared compatibility from an exact resolved
environment; it does not select package upgrades or security tooling. Use
[testing-and-validation.md](./testing-and-validation.md) for installation and
validation commands, and [ci-maintainer-guide.md](./ci-maintainer-guide.md)
for CI enforcement.

## Ownership Policy

| Owner | Responsibility | Must not own |
| --- | --- | --- |
| `[project.dependencies]` | Direct packages needed by installed production code. | Test, lint, type-check, or contributor-only tools. |
| `[project.optional-dependencies]` | Named feature and engineering extras retained for editable `pip` compatibility. | A second lock resolution. |
| `uv.lock` | Exact package resolution for contributor and CI environments. | Compatible-version policy or manually maintained package lists. |
| Requirements-format export | Absent by default; generated from a frozen lock only when a deployment consumer requires it. | An editable project reference or an independently maintained dependency graph. |
| Host tools such as FFmpeg/FFprobe | Documented operating-system prerequisites. | Python package metadata or lock resolution. |

The `dev` extra is a contributor-convenience aggregate, not an independent
version owner. It composes the focused extras and owns only `pre-commit`.

## Current Sources

| Source | Current role | Finding |
| --- | --- | --- |
| `pyproject.toml` | Declares direct package and optional-extra requirements. | Base dependencies exclude the reviewed test and lint tools. |
| `uv.lock` | Resolves the complete editable project and extras graph. | Tracks the current `pyproject.toml` metadata; regenerate only after intentional metadata changes. |
| Former `requirements.txt` | Historical complete environment snapshot. | Removed because no supported workflow consumed it and it pinned an old editable Git checkout. |

## Base Dependency Audit

| Declared package | Observed consumer | Current classification | Follow-up |
| --- | --- | --- | --- |
| `fastapi`, `uvicorn`, `pydantic` | FastAPI app, routers, schemas, and CLI startup. | Runtime. | Retain. |
| `pandas`, `m3u8` | Stores and playlist collection/loading. | Runtime. | Retain. |
| `mcp` | Local `esm-mcp` server. | Runtime. | Retain. |
| `pytest` | `tests/` only. | Test extra. | Removed from base dependencies. |
| `bandit` | Security workflow only. | Security extra. | Removed from base dependencies. |
| `cffi` | Resolved through `PyNaCl` and MCP's crypto extra; no direct repository import. | Unverified direct declaration. | Retain until its explicit declaration is tested separately. |
| `pynacl`, `python-ffmpeg` | Direct-only declarations with no repository import. | Unverified direct requirement. | Retain until clean-install and packaging removal checks exist. |

`setuptools` and `wheel` are build-system requirements, not application runtime
requirements.

## Optional-Extra Audit

| Extra | Consumers | Current classification | Finding |
| --- | --- | --- | --- |
| `detectorlab` | Detector-lab metrics, OpenCV decode, weekly media diagnostics. | Optional feature/tooling. | Appropriate focused extra. |
| `test` | Pytest, HTTP clients, YAML workflow fixtures. | Test tooling. | Appropriate focused extra. |
| `lint` | Ruff and Black. | Engineering tooling. | Appropriate focused extra. |
| `security` | Bandit and `pip-audit`. | Security tooling. | Appropriate focused extra. |
| `typecheck` | mypy and Pyright. | Engineering tooling. | Appropriate focused extra. |
| `dev` | Aggregate contributor environment. | Contributor convenience. | Composes focused extras and adds only `pre-commit`. |

## Installation And CI Consumers

| Consumer | Current installation path | Implication |
| --- | --- | --- |
| Runtime and packaging smoke | `pip install -e .` | Receives only the declared base package set. |
| Focused backend CI | `pip install -e .[test,detectorlab]` | Uses focused test and detector-lab extras. |
| Lint and type CI | `pip install -e .[lint]` or `.[typecheck]` | Uses focused engineering extras. |
| Security audit | `uv sync --locked --extra security` | Uses the focused scanner extra and locked resolution. |
| Weekly slow media | `uv sync --locked --extra test --extra detectorlab` | Uses the committed resolution and focused extras. |
| Full contributor environment | `uv sync --locked --extra dev` or `pip install -e .[dev]` | Composes the focused extras plus `pre-commit`. |

## Requirements-Format Policy

Current setup, CI, and validation paths use `pyproject.toml` and, where exact
resolution matters, `uv.lock`. A later deployment target may require a
requirements-format export. If so, add a documented frozen generation command
and keep the generated file free of editable project references.

## Boundaries

This policy does not upgrade packages, select a vulnerability scanner, or
redesign frontend dependency management. The current runtime/tool split and
`dev` aggregate are implemented and validated; the remaining unverified
runtime declarations require separate packaging evidence before removal.
