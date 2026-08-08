#!/usr/bin/env bash
# Enforce .nvmrc/packageManager ownership, then retry one transient install failure.
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly SCRIPT_DIR
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
readonly REPO_ROOT

if ! command -v node >/dev/null 2>&1; then
  echo "Node.js is required; select the version declared in .nvmrc." >&2
  exit 1
fi

REQUIRED_NODE_MAJOR="$(tr -d '[:space:]' < "${REPO_ROOT}/.nvmrc")"
readonly REQUIRED_NODE_MAJOR
INSTALLED_NODE_VERSION="$(node --version)"
readonly INSTALLED_NODE_VERSION

if [[ ! "${REQUIRED_NODE_MAJOR}" =~ ^[0-9]+$ ]]; then
  echo ".nvmrc must declare one Node.js major version." >&2
  exit 1
fi

if [[ ! "${INSTALLED_NODE_VERSION}" =~ ^v${REQUIRED_NODE_MAJOR}\.[0-9]+\.[0-9]+$ ]]; then
  echo "Expected Node.js ${REQUIRED_NODE_MAJOR}.x from .nvmrc; found ${INSTALLED_NODE_VERSION}." >&2
  echo "Select the repository Node version before installing frontend dependencies." >&2
  exit 1
fi

REQUIRED_NPM_SPEC="$(
  node -e 'const packageJson = require(process.argv[1]); process.stdout.write(packageJson.packageManager ?? "");' \
    "${REPO_ROOT}/frontend/package.json"
)"
readonly REQUIRED_NPM_SPEC

if [[ ! "${REQUIRED_NPM_SPEC}" =~ ^npm@[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  echo "frontend/package.json must declare an exact npm packageManager version." >&2
  exit 1
fi

readonly REQUIRED_NPM_VERSION="${REQUIRED_NPM_SPEC#npm@}"

if ! command -v npm >/dev/null 2>&1; then
  echo "npm is required to install frontend dependencies." >&2
  exit 1
fi

if [[ "$(npm --version)" != "${REQUIRED_NPM_VERSION}" ]]; then
  npm install --global "npm@${REQUIRED_NPM_VERSION}"
fi

if [[ "$(npm --version)" != "${REQUIRED_NPM_VERSION}" ]]; then
  echo "Expected npm ${REQUIRED_NPM_VERSION} after toolchain setup." >&2
  exit 1
fi

if ! npm ci; then
  echo "npm ci failed; retrying once for a transient package or Electron artifact error." >&2
  npm ci
fi
