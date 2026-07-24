#!/usr/bin/env bash
# Install the pinned frontend toolchain and retry one transient artifact failure.
set -euo pipefail

readonly REQUIRED_NPM_VERSION="11.15.0"

npm install --global "npm@${REQUIRED_NPM_VERSION}"

if [[ "$(npm --version)" != "${REQUIRED_NPM_VERSION}" ]]; then
  echo "Expected npm ${REQUIRED_NPM_VERSION} after toolchain setup." >&2
  exit 1
fi

if ! npm ci; then
  echo "npm ci failed; retrying once for a transient package or Electron artifact error." >&2
  npm ci
fi
