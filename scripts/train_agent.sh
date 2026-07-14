#!/usr/bin/env bash
# Formal staged training entrypoint. Requirements: REQ-PIDS-001..005,
# REQ-SFT-001..004, REQ-LABEL-001..004, REQ-REPRO-001..003.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN_ROOT="${APT_AGENT_RUN_ROOT:-/root/autodl-tmp/apt-agent/experiments/runs}"
RUN_ID=""
STAGE="all"
PYTHON_BIN="${APT_AGENT_PYTHON:-python}"

STAGES=(
  validate_environment validate_data prepare_pids_artifacts train_pids
  calibrate_thresholds build_approved_config_catalog build_trajectory_dataset
  train_sft validate_sft build_static_ltm freeze_deployment_bundle
)

usage() {
  echo "usage: $0 --run-id ID [--run-root PATH] [--stage all|STAGE]" >&2
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --run-id) RUN_ID="$2"; shift 2 ;;
    --run-root) RUN_ROOT="$2"; shift 2 ;;
    --stage) STAGE="$2"; shift 2 ;;
    *) usage; exit 2 ;;
  esac
done
[[ "$RUN_ID" =~ ^[A-Za-z0-9][A-Za-z0-9_.-]*$ ]] || { usage; exit 2; }
[[ "$STAGE" == "all" || " ${STAGES[*]} " == *" $STAGE "* ]] || { usage; exit 2; }
mkdir -p "$RUN_ROOT"
RUN_DIR="$RUN_ROOT/$RUN_ID"
[[ ! -e "$RUN_DIR" ]] || { echo "run already exists: $RUN_DIR" >&2; exit 2; }
mkdir "$RUN_DIR"

printf '%q ' "$0" --run-id "$RUN_ID" --run-root "$RUN_ROOT" --stage "$STAGE" >"$RUN_DIR/command.txt"
printf '\n' >>"$RUN_DIR/command.txt"
git -C "$ROOT" rev-parse HEAD >"$RUN_DIR/git_commit.txt"
git -C "$ROOT" diff --binary >"$RUN_DIR/git_diff.patch"
git -C "$ROOT/PIDSMaker" rev-parse HEAD >"$RUN_DIR/pidsmaker_commit.txt"
cp "$ROOT/configs/resource_profiles/autodl.yaml" "$RUN_DIR/resource_profile.yaml"
printf '{"entrypoint":"train_agent","requested_stage":"%s"}\n' "$STAGE" >"$RUN_DIR/config_resolved.yaml"
printf '{"status":"inventory_only","source":"docs/dataset_inventory.md"}\n' >"$RUN_DIR/data_manifest.json"
touch "$RUN_DIR/stdout.log" "$RUN_DIR/stderr.log" "$RUN_DIR/tool_calls.jsonl" "$RUN_DIR/trajectory.jsonl" "$RUN_DIR/predictions.jsonl"
printf '{}\n' >"$RUN_DIR/metrics.json"
"$PYTHON_BIN" -c 'import json,platform,sys; print(json.dumps({"python":sys.version.split()[0],"platform":platform.platform()},sort_keys=True))' >"$RUN_DIR/environment.json"

blocked=0
record() {
  local name="$1" status="$2" reason="$3"
  printf '{"stage":"%s","status":"%s","reason":"%s"}\n' "$name" "$status" "$reason" >>"$RUN_DIR/stages.jsonl"
}

execute_stage() {
  local name="$1"
  case "$name" in
    validate_environment)
      PYTHONPATH="$ROOT/src" "$PYTHON_BIN" "$ROOT/scripts/check_governance.py" >>"$RUN_DIR/stdout.log" 2>>"$RUN_DIR/stderr.log"
      record "$name" succeeded "governance, dependency, resource, and pinned-SHA checks passed" ;;
    validate_data)
      [[ -f "$ROOT/docs/dataset_inventory.md" ]]
      record "$name" succeeded "versioned dataset inventory exists; no split was inferred" ;;
    prepare_pids_artifacts)
      PYTHONPATH="$ROOT/src" "$PYTHON_BIN" -c 'from pathlib import Path; from apt_detection_agent.pidsmaker import PIDSMakerDiscovery; d=PIDSMakerDiscovery(Path("'"$ROOT"'")); assert len(d.capabilities())==10' >>"$RUN_DIR/stdout.log" 2>>"$RUN_DIR/stderr.log"
      record "$name" succeeded "complete registry retained; unavailable checkpoints were not fabricated" ;;
    train_pids|calibrate_thresholds|build_approved_config_catalog)
      blocked=1; record "$name" blocked "BLOCKED_BY_PHASE8_CAUSAL_CHECKPOINT_AND_DB_ROLE" ;;
    build_trajectory_dataset|train_sft|validate_sft)
      blocked=1; record "$name" blocked "BLOCKED_BY_SFT_DATASET" ;;
    build_static_ltm)
      blocked=1; record "$name" blocked "BLOCKED_BY_APPROVED_TRAINING_TRAJECTORIES" ;;
    freeze_deployment_bundle)
      blocked=1; record "$name" blocked "BLOCKED_BY_UPSTREAM_ARTIFACT_AND_SFT_GATES" ;;
  esac
}

if [[ "$STAGE" == "all" ]]; then
  for item in "${STAGES[@]}"; do execute_stage "$item"; done
else
  execute_stage "$STAGE"
fi

if (( blocked )); then
  printf '# Training stage summary\n\nOne or more explicit research gates remain blocked. See `stages.jsonl`.\n' >"$RUN_DIR/summary.md"
  "$PYTHON_BIN" "$ROOT/scripts/finalize_stage_run.py" --run-dir "$RUN_DIR" --status blocked --reason "one or more explicit research gates remain" --evidence-class training_stage_validation
  echo "BLOCKED: see $RUN_DIR/stages.jsonl"
  exit 3
fi
printf '# Training stage summary\n\nAll requested validation stages succeeded.\n' >"$RUN_DIR/summary.md"
"$PYTHON_BIN" "$ROOT/scripts/finalize_stage_run.py" --run-dir "$RUN_DIR" --status succeeded --evidence-class training_stage_validation
echo "$RUN_DIR"
