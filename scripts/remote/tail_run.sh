#!/usr/bin/env bash
# Requirements: REQ-REPRO-001..003.
set -euo pipefail
[[ $# -ge 1 && $# -le 2 ]] || exit 2
RUN_ID="$1"; LINES="${2:-80}"
[[ "$RUN_ID" =~ ^[A-Za-z0-9][A-Za-z0-9_.-]*$ && "$LINES" =~ ^[0-9]+$ ]] || exit 2
RUN_ROOT="${APT_AGENT_RUN_ROOT:-/root/autodl-tmp/apt-agent/experiments/runs}"
for name in stdout.log stderr.log; do
  echo "== $name =="
  [[ -f "$RUN_ROOT/$RUN_ID/$name" ]] && tail -n "$LINES" "$RUN_ROOT/$RUN_ID/$name" || echo "not available"
done
