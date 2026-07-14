#!/usr/bin/env bash
# Requirements: REQ-REPRO-002..003.
set -euo pipefail
[[ $# -eq 1 ]] || exit 2
RUN_ID="$1"; [[ "$RUN_ID" =~ ^[A-Za-z0-9][A-Za-z0-9_.-]*$ ]] || exit 2
RUN_ROOT="${APT_AGENT_RUN_ROOT:-/root/autodl-tmp/apt-agent/experiments/runs}"
SESSION="apt-agent-$RUN_ID"
if command -v tmux >/dev/null && tmux has-session -t "$SESSION" 2>/dev/null; then echo "tmux=running"; else echo "tmux=not-running"; fi
if [[ -f "$RUN_ROOT/$RUN_ID/run_status.json" ]]; then cat "$RUN_ROOT/$RUN_ID/run_status.json"; else echo "run_status=pending-or-missing"; fi
