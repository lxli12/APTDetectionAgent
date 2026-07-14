#!/usr/bin/env bash
# Safely fast-forward server code from the GitHub source of truth.
# Requirements: REQ-GIT-001..003.
set -euo pipefail

[[ $# -eq 1 ]] || { echo "usage: $0 REMOTE_REF" >&2; exit 2; }
REMOTE_REF="$1"
[[ "$REMOTE_REF" =~ ^[A-Za-z0-9][A-Za-z0-9_./-]*$ ]] || {
  echo "invalid remote ref" >&2
  exit 2
}

ROOT="${APT_AGENT_PROJECT_ROOT:-/root/APTDetectionAgent}"
EXPECTED_PIDSMaker_SHA="32602734bc9f896be5fc0f03f0a185c967cd6624"
[[ -d "$ROOT/.git" ]] || { echo "project repository not found" >&2; exit 2; }

if [[ -n "$(git -C "$ROOT" status --porcelain --untracked-files=all)" ]]; then
  echo "REMOTE_TREE_DIRTY: refusing pull" >&2
  exit 3
fi
if [[ ! -d "$ROOT/PIDSMaker/.git" && ! -f "$ROOT/PIDSMaker/.git" ]]; then
  echo "PIDSMaker submodule is not initialized" >&2
  exit 3
fi
if [[ -n "$(git -C "$ROOT/PIDSMaker" status --porcelain --untracked-files=all)" ]]; then
  echo "PIDSMaker_DIRTY: refusing pull" >&2
  exit 3
fi

cleanup_proxy() {
  unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY ALL_PROXY all_proxy
}
trap cleanup_proxy EXIT

if [[ "${APT_USE_NETWORK_TURBO:-0}" == "1" ]]; then
  [[ -r /etc/network_turbo ]] || {
    echo "academic network turbo is unavailable" >&2
    exit 3
  }
  # This affects only this short-lived Git transport process.
  source /etc/network_turbo
fi

git -C "$ROOT" pull --ff-only origin "$REMOTE_REF"
cleanup_proxy

[[ -z "$(git -C "$ROOT" status --porcelain --untracked-files=all)" ]] || {
  echo "REMOTE_TREE_DIRTY_AFTER_PULL" >&2
  exit 3
}
actual_sha="$(git -C "$ROOT/PIDSMaker" rev-parse HEAD)"
[[ "$actual_sha" == "$EXPECTED_PIDSMaker_SHA" ]] || {
  echo "PIDSMaker commit mismatch after pull" >&2
  exit 3
}
printf 'commit=%s\npidsmaker_commit=%s\n' \
  "$(git -C "$ROOT" rev-parse HEAD)" "$actual_sha"
