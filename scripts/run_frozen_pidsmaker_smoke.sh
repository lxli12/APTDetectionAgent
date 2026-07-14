#!/usr/bin/env bash
# New-window VELOX inference with a frozen validation bundle; no fitting or labels.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN_ROOT="${APT_AGENT_RUN_ROOT:-/root/autodl-tmp/apt-agent/experiments/runs}"
BUNDLE_ROOT="${APT_PRE_SFT_BUNDLE_ROOT:-/root/autodl-tmp/apt-agent/pre-sft-bundles}"
SECRET_FILE="${APT_PIDS_DB_SECRET_FILE:-/root/autodl-tmp/apt-agent/secrets/postgres_roles.env}"
PYTHON_BIN="${APT_PIDS_PYTHON:-/root/miniconda3/envs/pids/bin/python}"
RUN_ID=""
PIDSMaker_ROOT=""
BUNDLE=""

usage() { echo "usage: $0 --run-id ID --run-root PATH --pidsmaker-root PATH --bundle PATH" >&2; }
while [[ $# -gt 0 ]]; do
  case "$1" in
    --run-id) RUN_ID="$2"; shift 2 ;;
    --run-root) RUN_ROOT="$2"; shift 2 ;;
    --pidsmaker-root) PIDSMaker_ROOT="$2"; shift 2 ;;
    --bundle) BUNDLE="$2"; shift 2 ;;
    *) usage; exit 2 ;;
  esac
done
[[ "$RUN_ID" =~ ^[A-Za-z0-9][A-Za-z0-9_.-]*$ ]] || { usage; exit 2; }
[[ -x "$PYTHON_BIN" && -d "$PIDSMaker_ROOT/pidsmaker" ]] || { usage; exit 2; }
[[ "$(dirname "$(realpath "$BUNDLE")")" == "$(realpath "$BUNDLE_ROOT")" ]] || {
  echo "bundle escaped approved root" >&2; exit 2;
}
[[ -f "$SECRET_FILE" && ! -L "$SECRET_FILE" ]] || { echo "invalid secret file" >&2; exit 2; }
[[ "$(stat -c '%a' "$SECRET_FILE")" == "600" || "$(stat -c '%a' "$SECRET_FILE")" == "400" ]] || {
  echo "secret file permissions are not root-only" >&2; exit 2;
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
    "$PYTHON_BIN" "$ROOT/scripts/finalize_stage_run.py" --run-dir "$RUN_DIR" \
      --status failed --reason "frozen new-window smoke exited with code $code" \
      --evidence-class frozen_new_window_pids_smoke
  fi
}
trap on_exit EXIT
trap 'exit 143' HUP INT TERM

printf '%q ' "$0" --run-id "$RUN_ID" --run-root "$RUN_ROOT" \
  --pidsmaker-root "$PIDSMaker_ROOT" --bundle "$BUNDLE" >"$RUN_DIR/command.txt"
printf '\n' >>"$RUN_DIR/command.txt"
git -C "$ROOT" rev-parse HEAD >"$RUN_DIR/git_commit.txt"
git -C "$ROOT" diff --binary >"$RUN_DIR/git_diff.patch"
git -C "$ROOT/PIDSMaker" rev-parse HEAD >"$RUN_DIR/pidsmaker_commit.txt"
cp "$ROOT/configs/resource_profiles/autodl.yaml" "$RUN_DIR/resource_profile.yaml"
touch "$RUN_DIR/tool_calls.jsonl" "$RUN_DIR/trajectory.jsonl"
lscpu >"$RUN_DIR/lscpu.txt"
free -h >"$RUN_DIR/free.txt"
nvidia-smi >"$RUN_DIR/nvidia-smi.txt"

export WANDB_MODE=disabled WANDB_SILENT=true CUDA_VISIBLE_DEVICES=1
export APT_PIDS_CPU_THREADS=16 OMP_NUM_THREADS=16 MKL_NUM_THREADS=16
export OPENBLAS_NUM_THREADS=16 NUMEXPR_NUM_THREADS=16 VECLIB_MAXIMUM_THREADS=16
export PIDS_DB_HOST=127.0.0.1 PIDS_DB_USER=pids_worker PIDS_DB_PORT=5432
export APT_PRE_SFT_BUNDLE_ROOT="$BUNDLE_ROOT"
PIDS_DB_PASSWORD=""
while IFS='=' read -r key value; do
  if [[ "$key" == "PIDS_WORKER_PASSWORD" ]]; then PIDS_DB_PASSWORD="$value"; fi
done <"$SECRET_FILE"
[[ "$PIDS_DB_PASSWORD" =~ ^[a-f0-9]{64}$ ]] || { echo "invalid pids worker secret" >&2; exit 2; }
export PIDS_DB_PASSWORD

"$PYTHON_BIN" -c 'import importlib.metadata,json,os,platform,sys; print(json.dumps({"conda_environment":"pids","cuda_visible_devices":os.environ["CUDA_VISIBLE_DEVICES"],"pids_cpu_threads":int(os.environ["APT_PIDS_CPU_THREADS"]),"platform":platform.platform(),"python":sys.version.split()[0],"pytorch":importlib.metadata.version("torch")},sort_keys=True))' >"$RUN_DIR/environment.json"

ARTIFACT_ROOT="$RUN_DIR/pids_artifacts"
ARTIFACT_DIR="$ARTIFACT_ROOT/pipeline"
mkdir "$ARTIFACT_ROOT"
export APT_PIDS_ARTIFACT_ROOT="$ARTIFACT_ROOT"
COMMON_ARGS=(
  velox CADETS_E3 --pidsmaker-root "$PIDSMaker_ROOT" --artifact-dir "$ARTIFACT_DIR"
  --frozen-bundle "$BUNDLE" --window-size-seconds 900
  --train-date 2018-04-02 --train-window-start-ns 1522706400000000000 --train-window-end-ns 1522707300000000000
  --val-date 2018-04-03 --val-window-start-ns 1522809000000000000 --val-window-end-ns 1522809900000000000
  --test-date 2018-04-06 --test-window-start-ns 1523037600000000000 --test-window-end-ns 1523038500000000000
  --override featurization.epochs=1 --override featurization.emb_dim=16
  --override training.num_epochs=1 --override training.node_hid_dim=16 --override training.node_out_dim=16
)

printf '{"tool":"pidsmaker_frozen_prefix","status":"started"}\n' >>"$RUN_DIR/tool_calls.jsonl"
"$PYTHON_BIN" "$ROOT/scripts/pidsmaker_stage_runner.py" "${COMMON_ARGS[@]}" --stop-after feat_inference
printf '{"tool":"pidsmaker_frozen_prefix","status":"succeeded"}\n' >>"$RUN_DIR/tool_calls.jsonl"
CHECKPOINT_HASH="$($PYTHON_BIN -c 'import json,sys; print(json.load(open(sys.argv[1]))["checkpoint_hash"])' "$BUNDLE/bundle_manifest.json")"
printf '{"tool":"pidsmaker_frozen_inference","status":"started"}\n' >>"$RUN_DIR/tool_calls.jsonl"
"$PYTHON_BIN" "$ROOT/scripts/pidsmaker_causal_runner.py" infer "${COMMON_ARGS[@]}" --checkpoint-hash "$CHECKPOINT_HASH"
printf '{"tool":"pidsmaker_frozen_inference","status":"succeeded"}\n' >>"$RUN_DIR/tool_calls.jsonl"

"$PYTHON_BIN" "$ROOT/scripts/finalize_frozen_window_smoke.py" --run-dir "$RUN_DIR" --bundle "$BUNDLE"
"$PYTHON_BIN" "$ROOT/scripts/finalize_stage_run.py" --run-dir "$RUN_DIR" \
  --status succeeded --evidence-class frozen_new_window_pids_smoke
finished=1
echo "FROZEN_NEW_WINDOW_SMOKE=SUCCEEDED run_id=$RUN_ID"
