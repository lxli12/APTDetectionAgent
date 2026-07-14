#!/usr/bin/env bash
# Root-owned orchestrator for a bounded real PIDSMaker → hidden-evaluator E2E.
# Requirements: REQ-LABEL-001..004, REQ-EVAL-001..007, REQ-REPRO-001..003.
set -euo pipefail
[[ $EUID -eq 0 ]] || { echo "real E2E permission orchestration requires root" >&2; exit 2; }
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${APT_AGENT_PYTHON:-/root/miniconda3/envs/pids/bin/python}"
RUN_ROOT="${APT_AGENT_RUN_ROOT:-/root/autodl-tmp/apt-agent/experiments/runs}"
PRIVATE_BASE="${APT_EVALUATOR_PRIVATE_ROOT:-/root/autodl-tmp/apt-agent/evaluator-private}"
EXECUTOR_BASE="${APT_PIDS_EXECUTOR_ROOT:-/root/autodl-tmp/apt-agent/runtime/pids}"
RUN_ID=""
PIDS_RUN=""
RUNTIME_ROOT=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --run-id) RUN_ID="$2"; shift 2 ;;
    --run-root) RUN_ROOT="$2"; shift 2 ;;
    --private-root) PRIVATE_BASE="$2"; shift 2 ;;
    --pids-run) PIDS_RUN="$2"; shift 2 ;;
    --runtime-root) RUNTIME_ROOT="$2"; shift 2 ;;
    *) echo "usage: $0 --run-id ID --pids-run PATH --runtime-root PATH [--run-root PATH] [--private-root PATH]" >&2; exit 2 ;;
  esac
done
[[ "$RUN_ID" =~ ^[A-Za-z0-9][A-Za-z0-9_.-]*$ ]] || exit 2
PIDS_RUN="$(realpath "$PIDS_RUN")"
RUNTIME_ROOT="$(realpath "$RUNTIME_ROOT")"
[[ -f "$PIDS_RUN/run_status.json" && -f "$PIDS_RUN/pids_artifacts/pipeline/checkpoint_manifest.json" ]] || exit 2
[[ -f "$RUNTIME_ROOT/runtime_manifest.json" ]] || exit 2
"$PYTHON_BIN" -c 'import json,sys; p=json.load(open(sys.argv[1])); assert p["status"]=="succeeded" and p["evidence_class"]=="real_causal_pids_smoke"' "$PIDS_RUN/run_status.json"
for identity in apt_agent_controller apt_pids_worker apt_hidden_evaluator; do
  getent passwd "$identity" >/dev/null || { echo "OS isolation is not provisioned" >&2; exit 3; }
done

RUN_DIR="$RUN_ROOT/$RUN_ID"
PRIVATE_ROOT="$PRIVATE_BASE/$RUN_ID"
EXECUTOR_ROOT="$EXECUTOR_BASE/$RUN_ID"
[[ ! -e "$RUN_DIR" && ! -e "$PRIVATE_ROOT" && ! -e "$EXECUTOR_ROOT" ]] || {
  echo "run exists" >&2
  exit 2
}
mkdir "$RUN_DIR" "$PRIVATE_ROOT" "$EXECUTOR_ROOT"
chown apt_agent_controller:apt_eval_exchange "$RUN_DIR"
chmod 2770 "$RUN_DIR"
chown apt_hidden_evaluator:apt_hidden_evaluator "$PRIVATE_ROOT"
chmod 700 "$PRIVATE_ROOT"
chown apt_pids_worker:apt_pids_worker "$EXECUTOR_ROOT"
chmod 700 "$EXECUTOR_ROOT"
chmod 711 "$RUNTIME_ROOT"
chown -R root:apt_agent_controller "$RUNTIME_ROOT/controller"
chown -R root:apt_pids_worker "$RUNTIME_ROOT/pids"
chown -R root:apt_hidden_evaluator "$RUNTIME_ROOT/evaluator"
find "$RUNTIME_ROOT/controller" "$RUNTIME_ROOT/pids" "$RUNTIME_ROOT/evaluator" -type d -exec chmod 750 {} +
find "$RUNTIME_ROOT/controller" "$RUNTIME_ROOT/pids" "$RUNTIME_ROOT/evaluator" -type f -exec chmod 640 {} +
find "$RUNTIME_ROOT/controller/scripts" "$RUNTIME_ROOT/pids/scripts" "$RUNTIME_ROOT/evaluator/scripts" -type f -exec chmod 750 {} +
exec >"$RUN_DIR/stdout.log" 2>"$RUN_DIR/stderr.log"
finished=0
on_exit() {
  code=$?
  if (( finished == 0 )) && [[ ! -e "$RUN_DIR/run_status.json" ]]; then
    set +e
    "$PYTHON_BIN" "$ROOT/scripts/finalize_stage_run.py" --run-dir "$RUN_DIR" \
      --status failed --reason "real E2E exited with code $code" \
      --evidence-class bounded_real_validation_integration
  fi
}
trap on_exit EXIT
trap 'exit 143' HUP INT TERM

chgrp -R apt_pids_worker "$PIDS_RUN"
find "$PIDS_RUN" -type d -exec chmod 750 {} +
find "$PIDS_RUN" -type f -exec chmod 640 {} +
chgrp apt_pids_worker "$ROOT/PIDSMaker"
chmod 750 "$ROOT/PIDSMaker"
chmod 750 "$ROOT"

printf '%q ' "$0" --run-id "$RUN_ID" --pids-run "$PIDS_RUN" --runtime-root "$RUNTIME_ROOT" \
  --run-root "$RUN_ROOT" --private-root "$PRIVATE_BASE" >"$RUN_DIR/command.txt"
printf '\n' >>"$RUN_DIR/command.txt"
git -C "$ROOT" rev-parse HEAD >"$RUN_DIR/git_commit.txt"
git -C "$ROOT/PIDSMaker" rev-parse HEAD >"$RUN_DIR/pidsmaker_commit.txt"
cp "$ROOT/configs/resource_profiles/autodl.yaml" "$RUN_DIR/resource_profile.yaml"
printf '{"stage":"freeze_validation_threshold","status":"started"}\n' >"$RUN_DIR/stages.jsonl"

runuser -u apt_pids_worker -- env PYTHONPATH="$RUNTIME_ROOT/pids/src" \
  "$PYTHON_BIN" "$RUNTIME_ROOT/pids/scripts/standardize_pids_result.py" \
  --pids-run "$PIDS_RUN" --validation-quantile 0.999 \
  --threshold-output "$EXECUTOR_ROOT/threshold.json" \
  --observation-output "$EXECUTOR_ROOT/detection_result.json"
install -o apt_agent_controller -g apt_eval_exchange -m 640 \
  "$EXECUTOR_ROOT/threshold.json" "$RUN_DIR/threshold.json"
install -o apt_agent_controller -g apt_eval_exchange -m 640 \
  "$EXECUTOR_ROOT/detection_result.json" "$RUN_DIR/detection_result.json"
printf '{"stage":"freeze_validation_threshold","status":"succeeded"}\n' >>"$RUN_DIR/stages.jsonl"
printf '{"stage":"standardize_detection_result","status":"succeeded"}\n' >>"$RUN_DIR/stages.jsonl"

GROUND_TRUTH_SOURCE="$ROOT/PIDSMaker/Ground_Truth/orthrus/E3-CADETS/node_Nginx_Backdoor_06.csv"
install -o apt_hidden_evaluator -g apt_hidden_evaluator -m 400 \
  "$GROUND_TRUTH_SOURCE" "$PRIVATE_ROOT/campaign_truth.csv"
runuser -u apt_hidden_evaluator -- env \
  HIDDEN_EVALUATOR_PRIVATE_ROOT="$PRIVATE_ROOT" AGENT_OBSERVATION_ROOT="$RUN_DIR" \
  PYTHONPATH="$RUNTIME_ROOT/evaluator/src" "$PYTHON_BIN" "$RUNTIME_ROOT/evaluator/scripts/build_real_hidden_request.py" \
  --observation "$RUN_DIR/detection_result.json" \
  --ground-truth "$PRIVATE_ROOT/campaign_truth.csv" \
  --private-request "$PRIVATE_ROOT/request.json" \
  --private-campaign-manifest "$PRIVATE_ROOT/campaign_manifest.json"
printf '{"stage":"build_private_campaign_manifest","status":"succeeded"}\n' >>"$RUN_DIR/stages.jsonl"

runuser -u apt_hidden_evaluator -- env \
  HIDDEN_EVALUATOR_PRIVATE_ROOT="$PRIVATE_ROOT" AGENT_FEEDBACK_ROOT="$RUN_DIR" \
  PYTHONPATH="$RUNTIME_ROOT/evaluator/src" "$PYTHON_BIN" "$RUNTIME_ROOT/evaluator/scripts/run_hidden_evaluator.py" \
  --private-input "$PRIVATE_ROOT/request.json" \
  --private-output "$PRIVATE_ROOT/metrics.json" \
  --public-feedback "$RUN_DIR/evaluation_feedback.json"
chown apt_hidden_evaluator:apt_eval_exchange "$RUN_DIR/evaluation_feedback.json"
chmod 640 "$RUN_DIR/evaluation_feedback.json"
printf '{"stage":"run_hidden_evaluator","status":"succeeded"}\n' >>"$RUN_DIR/stages.jsonl"

runuser -u apt_agent_controller -- test ! -r "$PRIVATE_ROOT/request.json"
runuser -u apt_agent_controller -- test ! -r "$PRIVATE_ROOT/metrics.json"
runuser -u apt_agent_controller -- test ! -r "$ROOT/.git/config"
runuser -u apt_agent_controller -- test ! -r "$RUNTIME_ROOT/evaluator/scripts/build_real_hidden_request.py"
RAW_SCORE="$(find "$PIDS_RUN/pids_artifacts/pipeline" -path '*/edge_losses/test/*/*.csv' -type f -print -quit)"
[[ -n "$RAW_SCORE" ]]
runuser -u apt_agent_controller -- test ! -r "$RAW_SCORE"
runuser -u apt_hidden_evaluator -- test ! -w "$RUNTIME_ROOT/evaluator/src"
printf '{"controller_private_read":false,"controller_raw_pids_read":false,"controller_repository_read":false,"controller_evaluator_runtime_read":false,"evaluator_source_write":false}\n' >"$RUN_DIR/permission_check.json"
chown apt_agent_controller:apt_eval_exchange "$RUN_DIR/permission_check.json" "$RUN_DIR/stages.jsonl"
chmod 640 "$RUN_DIR/permission_check.json" "$RUN_DIR/stages.jsonl"

runuser -u apt_agent_controller -- env PYTHONPATH="$RUNTIME_ROOT/controller/src" \
  "$PYTHON_BIN" "$RUNTIME_ROOT/controller/scripts/finalize_real_public_report.py" --run-dir "$RUN_DIR"
echo "REAL_E2E=SUCCEEDED run_id=$RUN_ID"
runuser -u apt_agent_controller -- "$PYTHON_BIN" "$RUNTIME_ROOT/controller/scripts/finalize_stage_run.py" \
  --run-dir "$RUN_DIR" --status succeeded \
  --evidence-class bounded_real_validation_integration
finished=1
