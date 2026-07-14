#!/usr/bin/env bash
# Causal real-data PIDSMaker smoke: exact windows, validation checkpoint, frozen inference.
# Requirements: REQ-PIDS-004..005, REQ-CAUSAL-001..004, REQ-LABEL-001..004,
# REQ-WANDB-001, REQ-RESOURCE-001..003, REQ-REPRO-001..003.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN_ROOT="${APT_AGENT_RUN_ROOT:-/root/autodl-tmp/apt-agent/experiments/runs}"
SECRET_FILE="${APT_PIDS_DB_SECRET_FILE:-/root/autodl-tmp/apt-agent/secrets/postgres_roles.env}"
PYTHON_BIN="${APT_PIDS_PYTHON:-/root/miniconda3/envs/pids/bin/python}"
RUN_ID=""
PIDSMaker_ROOT=""

usage() {
  echo "usage: $0 --run-id ID --run-root PATH --pidsmaker-root PATH" >&2
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --run-id) RUN_ID="$2"; shift 2 ;;
    --run-root) RUN_ROOT="$2"; shift 2 ;;
    --pidsmaker-root) PIDSMaker_ROOT="$2"; shift 2 ;;
    *) usage; exit 2 ;;
  esac
done
[[ "$RUN_ID" =~ ^[A-Za-z0-9][A-Za-z0-9_.-]*$ ]] || { usage; exit 2; }
[[ -x "$PYTHON_BIN" && -d "$PIDSMaker_ROOT/pidsmaker" ]] || { usage; exit 2; }
[[ -f "$SECRET_FILE" && ! -L "$SECRET_FILE" ]] || { echo "invalid secret file" >&2; exit 2; }
[[ "$(stat -c '%a' "$SECRET_FILE")" == "600" || "$(stat -c '%a' "$SECRET_FILE")" == "400" ]] || {
  echo "secret file permissions are not root-only" >&2
  exit 2
}

mkdir -p "$RUN_ROOT"
RUN_DIR="$RUN_ROOT/$RUN_ID"
[[ ! -e "$RUN_DIR" ]] || { echo "run already exists: $RUN_DIR" >&2; exit 2; }
mkdir "$RUN_DIR"
exec >"$RUN_DIR/stdout.log" 2>"$RUN_DIR/stderr.log"

finished=0
on_exit() {
  code=$?
  if (( finished == 0 )) && [[ ! -e "$RUN_DIR/run_status.json" ]]; then
    set +e
    "$PYTHON_BIN" "$ROOT/scripts/finalize_stage_run.py" \
      --run-dir "$RUN_DIR" --status failed --reason "pidsmaker smoke exited with code $code" \
      --evidence-class real_causal_pids_smoke
  fi
}
trap on_exit EXIT

printf '%q ' "$0" --run-id "$RUN_ID" --run-root "$RUN_ROOT" \
  --pidsmaker-root "$PIDSMaker_ROOT" >"$RUN_DIR/command.txt"
printf '\n' >>"$RUN_DIR/command.txt"
git -C "$ROOT" rev-parse HEAD >"$RUN_DIR/git_commit.txt"
git -C "$ROOT" diff --binary >"$RUN_DIR/git_diff.patch"
git -C "$ROOT/PIDSMaker" rev-parse HEAD >"$RUN_DIR/pidsmaker_commit.txt"
cp "$ROOT/configs/resource_profiles/autodl.yaml" "$RUN_DIR/resource_profile.yaml"
touch "$RUN_DIR/tool_calls.jsonl" "$RUN_DIR/trajectory.jsonl"
lscpu >"$RUN_DIR/lscpu.txt"
free -h >"$RUN_DIR/free.txt"
nvidia-smi >"$RUN_DIR/nvidia-smi.txt"

export WANDB_MODE=disabled
export WANDB_SILENT=true
export APT_PIDS_CPU_THREADS=16
export OMP_NUM_THREADS=16
export MKL_NUM_THREADS=16
export OPENBLAS_NUM_THREADS=16
export NUMEXPR_NUM_THREADS=16
export VECLIB_MAXIMUM_THREADS=16
export CUDA_VISIBLE_DEVICES=1
export PIDS_DB_HOST=127.0.0.1
export PIDS_DB_USER=pids_worker
export PIDS_DB_PORT=5432
PIDS_DB_PASSWORD=""
while IFS='=' read -r key value; do
  if [[ "$key" == "PIDS_WORKER_PASSWORD" ]]; then PIDS_DB_PASSWORD="$value"; fi
done <"$SECRET_FILE"
[[ "$PIDS_DB_PASSWORD" =~ ^[a-f0-9]{64}$ ]] || { echo "invalid pids worker secret" >&2; exit 2; }
export PIDS_DB_PASSWORD

"$PYTHON_BIN" -c 'import importlib.metadata,json,os,platform,sys; print(json.dumps({"conda_environment":"pids","cuda_visible_devices":os.environ["CUDA_VISIBLE_DEVICES"],"pids_cpu_threads":int(os.environ["APT_PIDS_CPU_THREADS"]),"platform":platform.platform(),"python":sys.version.split()[0],"pytorch":importlib.metadata.version("torch")},sort_keys=True))' >"$RUN_DIR/environment.json"
PYTHONPATH="$PIDSMaker_ROOT" "$PYTHON_BIN" -c 'import sys; import pidsmaker.factory; from pidsmaker.detection.training_methods import training_loop; assert "wandb" not in sys.modules; print("WANDB_IMPORT_GATE=PASS")'

ARTIFACT_ROOT="$RUN_DIR/pids_artifacts"
ARTIFACT_DIR="$ARTIFACT_ROOT/pipeline"
mkdir "$ARTIFACT_ROOT"
export APT_PIDS_ARTIFACT_ROOT="$ARTIFACT_ROOT"

COMMON_ARGS=(
  velox CADETS_E3
  --pidsmaker-root "$PIDSMaker_ROOT"
  --artifact-dir "$ARTIFACT_DIR"
  --window-size-seconds 900
  --train-date 2018-04-02
  --train-window-start-ns 1522706400000000000
  --train-window-end-ns 1522707300000000000
  --val-date 2018-04-03
  --val-window-start-ns 1522809000000000000
  --val-window-end-ns 1522809900000000000
  --test-date 2018-04-06
  --test-window-start-ns 1523030400000000000
  --test-window-end-ns 1523031300000000000
  --override featurization.epochs=1
  --override featurization.emb_dim=16
  --override training.num_epochs=1
  --override training.node_hid_dim=16
  --override training.node_out_dim=16
)

printf '{"tool":"pidsmaker_prefix","status":"started"}\n' >>"$RUN_DIR/tool_calls.jsonl"
"$PYTHON_BIN" "$ROOT/scripts/pidsmaker_stage_runner.py" "${COMMON_ARGS[@]}" \
  --stop-after feat_inference
printf '{"tool":"pidsmaker_prefix","status":"succeeded"}\n' >>"$RUN_DIR/tool_calls.jsonl"

printf '{"tool":"pidsmaker_train","status":"started"}\n' >>"$RUN_DIR/tool_calls.jsonl"
"$PYTHON_BIN" "$ROOT/scripts/pidsmaker_causal_runner.py" train "${COMMON_ARGS[@]}"
printf '{"tool":"pidsmaker_train","status":"succeeded"}\n' >>"$RUN_DIR/tool_calls.jsonl"

CHECKPOINT_HASH="$("$PYTHON_BIN" -c 'import json,sys; print(json.load(open(sys.argv[1]))["checkpoint_hash"])' "$ARTIFACT_DIR/checkpoint_manifest.json")"
[[ "$CHECKPOINT_HASH" =~ ^[a-f0-9]{64}$ ]] || { echo "invalid checkpoint hash" >&2; exit 3; }
printf '{"tool":"pidsmaker_frozen_inference","status":"started"}\n' >>"$RUN_DIR/tool_calls.jsonl"
"$PYTHON_BIN" "$ROOT/scripts/pidsmaker_causal_runner.py" infer "${COMMON_ARGS[@]}" \
  --checkpoint-hash "$CHECKPOINT_HASH"
printf '{"tool":"pidsmaker_frozen_inference","status":"succeeded"}\n' >>"$RUN_DIR/tool_calls.jsonl"

"$PYTHON_BIN" "$ROOT/scripts/finalize_pidsmaker_smoke.py" --run-dir "$RUN_DIR"
echo "PIDSMAKER_SMOKE=SUCCEEDED run_id=$RUN_ID"
"$PYTHON_BIN" "$ROOT/scripts/finalize_stage_run.py" --run-dir "$RUN_DIR" \
  --status succeeded --evidence-class real_causal_pids_smoke
finished=1
