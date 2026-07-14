#!/usr/bin/env bash
# Requirements: REQ-LABEL-001..004, REQ-REPRO-001..003.
set -euo pipefail
[[ $# -eq 1 ]] || exit 2
RUN_ID="$1"; [[ "$RUN_ID" =~ ^[A-Za-z0-9][A-Za-z0-9_.-]*$ ]] || exit 2
RUN_ROOT="${APT_AGENT_RUN_ROOT:-/root/autodl-tmp/apt-agent/experiments/runs}"
RUN_DIR="$RUN_ROOT/$RUN_ID"
[[ -d "$RUN_DIR" ]] || { echo "run not found" >&2; exit 2; }
echo "run_id=$RUN_ID"
[[ -f "$RUN_DIR/git_commit.txt" ]] && sed -n '1p' "$RUN_DIR/git_commit.txt"
[[ -f "$RUN_DIR/run_status.json" ]] && cat "$RUN_DIR/run_status.json"
[[ -f "$RUN_DIR/summary.md" ]] && cat "$RUN_DIR/summary.md"
