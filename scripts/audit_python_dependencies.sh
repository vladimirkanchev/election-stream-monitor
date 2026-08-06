#!/usr/bin/env sh
# Audit the locked production dependency graph without retaining an export.
set -eu

: "${PIP_AUDIT:?Set PIP_AUDIT to the pip-audit executable.}"

audit_input="$(mktemp "${TMPDIR:-/tmp}/esm-python-audit.XXXXXX")"
trap 'rm -f "$audit_input"' EXIT HUP INT TERM

uv export --frozen --no-dev --no-emit-project \
  --format requirements.txt \
  --output-file "$audit_input" >/dev/null
"$PIP_AUDIT" -r "$audit_input"
