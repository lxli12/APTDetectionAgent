#!/usr/bin/env bash
# Start only an APTDetectionAgent-owned long run. Requirements: REQ-GIT-001..003,
# REQ-RESOURCE-001..003, REQ-REPRO-001..003.
set -euo pipefail
[[ $# -ge 2 ]] || { echo "usage: $0 RUN_ID train|test|pids-smoke [entrypoint args...]" >&2; exit 2; }
RUN_ID="$1"; KIND="$2"; shift 2
[[ "$RUN_ID" =~ ^[A-Za-z0-9][A-Za-z0-9_.-]*$ ]] || exit 2
command -v tmux >/dev/null || { echo "BLOCKED_BY_MISSING_TMUX: installation requires approval" >&2; exit 3; }
ROOT="${APT_AGENT_PROJECT_ROOT:-/root/APTDetectionAgent}"
RUN_ROOT="${APT_AGENT_RUN_ROOT:-/root/autodl-tmp/apt-agent/experiments/runs}"
CONTROL_ROOT="${APT_AGENT_CONTROL_ROOT:-/root/autodl-tmp/apt-agent/experiments/control}"
SESSION="apt-agent-$RUN_ID"
[[ "$KIND" == "train" || "$KIND" == "test" || "$KIND" == "pids-smoke" ]] || exit 2
[[ ! -e "$RUN_ROOT/$RUN_ID" && ! -e "$CONTROL_ROOT/$RUN_ID" ]] || { echo "run exists" >&2; exit 2; }
mkdir -p "$CONTROL_ROOT/$RUN_ID"
printf '%s\n' "$SESSION" >"$CONTROL_ROOT/$RUN_ID/owned_session.txt"
printf '%s\n' "$(git -C "$ROOT" rev-parse HEAD)" >"$CONTROL_ROOT/$RUN_ID/git_commit.txt"
if [[ "$KIND" == "pids-smoke" ]]; then
  ENTRYPOINT="$ROOT/scripts/run_pidsmaker_smoke.sh"
else
  ENTRYPOINT="$ROOT/scripts/${KIND}_agent.sh"
fi
printf '%q ' "$ENTRYPOINT" --run-id "$RUN_ID" --run-root "$RUN_ROOT" "$@" >"$CONTROL_ROOT/$RUN_ID/command.txt"
printf '\n' >>"$CONTROL_ROOT/$RUN_ID/command.txt"
tmux new-session -d -s "$SESSION" -- "$ENTRYPOINT" --run-id "$RUN_ID" --run-root "$RUN_ROOT" "$@"
tmux has-session -t "$SESSION"
echo "session=$SESSION run_id=$RUN_ID status=$ROOT/scripts/remote/status_run.sh\ $RUN_ID"
