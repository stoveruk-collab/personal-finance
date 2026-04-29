#!/bin/zsh
set -euo pipefail

SOURCE_CONFIG="${HOME}/.config/gcloud"
TARGET_CONFIG="$(mktemp -d "${TMPDIR:-/tmp}/codex-gcloud.XXXXXX")"

# Mirror the user's real gcloud config into a writable location for sandboxed runs.
if [[ -d "${SOURCE_CONFIG}" ]]; then
  cp -R "${SOURCE_CONFIG}/." "${TARGET_CONFIG}/"
fi

export CLOUDSDK_CONFIG="${TARGET_CONFIG}"

exec gcloud "$@"
