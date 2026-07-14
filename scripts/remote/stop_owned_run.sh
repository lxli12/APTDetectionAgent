#!/usr/bin/env bash
# Stop only a session created by start_run.sh. Requirements: REQ-GIT-002,
# REQ-REPRO-003.
set -euo pipefail
[[ $# -eq 1 ]] || exit 2
RUN_ID="$1"; [[ "$RUN_ID" =~ ^[A-Za-z0-9][A-Za-z0-9_.-]*$ ]] || exit 2
CONTROL_ROOT="${APT_AGENT_CONTROL_ROOT:-/root/autodl-tmp/apt-agent/experiments/control}"
SESSION="apt-agent-$RUN_ID"
MARKER="$CONTROL_ROOT/$RUN_ID/owned_session.txt"
[[ -f "$MARKER" && "$(cat "$MARKER")" == "$SESSION" ]] || { echo "not an owned run" >&2; exit 3; }
command -v tmux >/dev/null || { echo "tmux unavailable" >&2; exit 3; }
tmux has-session -t "$SESSION" 2>/dev/null || { echo "owned session is not running"; exit 0; }
pane_pid="$(tmux list-panes -t "$SESSION" -F '#{pane_pid}' | head -1)"
[[ "$pane_pid" =~ ^[0-9]+$ ]] || { echo "cannot identify owned pane process" >&2; exit 3; }
tmux send-keys -t "$SESSION" C-c
for attempt in 1 2 3 4 5; do
  if ! tmux has-session -t "$SESSION" 2>/dev/null; then break; fi
  sleep 1
done
if tmux has-session -t "$SESSION" 2>/dev/null; then
  pgid="$(ps -o pgid= -p "$pane_pid" | tr -d ' ')"
  tmux kill-session -t "$SESSION"
  if [[ "$pgid" =~ ^[0-9]+$ && "$pgid" -gt 1 ]]; then
    kill -TERM -- "-$pgid" 2>/dev/null || true
  fi
fi
echo "stopped owned session $SESSION"
