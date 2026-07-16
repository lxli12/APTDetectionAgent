#!/usr/bin/env bash
set -uo pipefail

REPO_ROOT="${REPO_ROOT:-/root/APTDetectionAgent}"
OUTPUT_ROOT="${OUTPUT_ROOT:-/root/autodl-tmp/apt-detection-agent/pidsmaker-output}"
RUN_ID="${RUN_ID:-$(date -u +%Y%m%dT%H%M%SZ)}"
LOG_ROOT="${LOG_ROOT:-/root/autodl-tmp/apt-detection-agent/experiments-result/CLEARSCOPE_E3/checkpoint-preparation/${RUN_ID}}"
CONDA_ENV="${CONDA_ENV:-pids}"
RUNTIME_ENV="${RUNTIME_ENV:-/root/autodl-tmp/apt-detection-agent/.runtime/db.env}"

find_conda() {
  local candidate
  for candidate in \
    /root/miniconda3/etc/profile.d/conda.sh \
    /root/miniforge3/etc/profile.d/conda.sh \
    /opt/conda/etc/profile.d/conda.sh
  do
    if [[ -f "${candidate}" ]]; then
      # shellcheck disable=SC1090
      source "${candidate}"
      return 0
    fi
  done
  echo "Unable to locate conda.sh" >&2
  return 1
}

find_conda
conda activate "${CONDA_ENV}"
cd "${REPO_ROOT}"

python -c 'import nltk; nltk.data.find("tokenizers/punkt")'

if [[ -f "${RUNTIME_ENV}" ]]; then
  # shellcheck disable=SC1090
  source "${RUNTIME_ENV}"
fi

if ! pg_isready -h "${PIDS_DB_HOST:-localhost}" -p "${PIDS_DB_PORT:-5432}" >/dev/null 2>&1; then
  pg_ctlcluster 17 main start
  for _ in {1..15}; do
    pg_isready -h "${PIDS_DB_HOST:-localhost}" -p "${PIDS_DB_PORT:-5432}" >/dev/null 2>&1 && break
    sleep 1
  done
fi
pg_isready -h "${PIDS_DB_HOST:-localhost}" -p "${PIDS_DB_PORT:-5432}" >/dev/null

if [[ -z "${PIDS_DB_PASSWORD:-}" ]]; then
  echo "PIDS_DB_PASSWORD must be exported; credentials are never read from CLI arguments." >&2
  exit 2
fi

mkdir -p "${OUTPUT_ROOT}" "${LOG_ROOT}"
python -m pidsmaker_adapter.main list-configs --plain > "${LOG_ROOT}/configurations.txt"
cp pidsmaker_adapter/config/configuration_space_v1.yaml \
  "${LOG_ROOT}/configuration_space_v1.yaml"
mapfile -t CONFIGS < "${LOG_ROOT}/configurations.txt"
if [[ "${#CONFIGS[@]}" -eq 0 ]]; then
  echo "No legal configurations found" >&2
  exit 2
fi

run_worker() {
  local gpu="$1"
  local offset="$2"
  local failures=0
  local index config log_file
  for ((index=offset; index<${#CONFIGS[@]}; index+=2)); do
    config="${CONFIGS[index]}"
    log_file="${LOG_ROOT}/${config}.log"
    if ! CUDA_VISIBLE_DEVICES="${gpu}" PYTHONUNBUFFERED=1 \
      python -m pidsmaker_adapter.main prepare \
      --config "${config}" \
      --output-root "${OUTPUT_ROOT}" \
      >"${log_file}" 2>&1
    then
      failures=$((failures + 1))
      echo "FAILED gpu=${gpu} config=${config} log=${log_file}" >&2
    else
      echo "COMPLETE gpu=${gpu} config=${config}"
    fi
  done
  return "${failures}"
}

run_worker 0 0 &
PID_GPU0=$!
run_worker 1 1 &
PID_GPU1=$!

STATUS=0
wait "${PID_GPU0}" || STATUS=1
wait "${PID_GPU1}" || STATUS=1
exit "${STATUS}"
