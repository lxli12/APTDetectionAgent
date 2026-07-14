#!/usr/bin/env bash
# Provision non-login process identities and filesystem roots; never changes data content.
# Requirements: REQ-LABEL-001, REQ-DB-001..002, REQ-ENV-002, REQ-REPRO-001.
set -euo pipefail
[[ $EUID -eq 0 ]] || { echo "must run as root" >&2; exit 2; }
[[ $# -eq 1 ]] || { echo "usage: $0 ROOT_ONLY_COMBINED_SECRET_FILE" >&2; exit 2; }
COMBINED_SECRET="$1"
[[ -f "$COMBINED_SECRET" && ! -L "$COMBINED_SECRET" ]] || exit 2
[[ "$(stat -c '%a' "$COMBINED_SECRET")" == "600" || "$(stat -c '%a' "$COMBINED_SECRET")" == "400" ]] || exit 2

ensure_user() {
  name="$1"
  if ! getent passwd "$name" >/dev/null; then
    useradd --system --user-group --home-dir /nonexistent --shell /usr/sbin/nologin "$name"
  fi
}
ensure_user apt_agent_controller
ensure_user apt_pids_worker
ensure_user apt_hidden_evaluator
if ! getent group apt_eval_exchange >/dev/null; then groupadd --system apt_eval_exchange; fi
usermod -a -G apt_eval_exchange apt_agent_controller
usermod -a -G apt_eval_exchange apt_hidden_evaluator

BASE=/root/autodl-tmp/apt-agent
mkdir -p "$BASE/runtime/controller" "$BASE/runtime/pids" "$BASE/evaluator-private" \
  "$BASE/feedback-exchange" "$BASE/secrets"
chown root:root "$BASE/secrets"
chmod 711 "$BASE/secrets"
chown apt_agent_controller:apt_agent_controller "$BASE/runtime/controller"
chmod 750 "$BASE/runtime/controller"
chown apt_pids_worker:apt_pids_worker "$BASE/runtime/pids"
chmod 750 "$BASE/runtime/pids"
chown -R apt_hidden_evaluator:apt_hidden_evaluator "$BASE/evaluator-private"
find "$BASE/evaluator-private" -type d -exec chmod 700 {} +
find "$BASE/evaluator-private" -type f -exec chmod 600 {} +
chown apt_agent_controller:apt_eval_exchange "$BASE/feedback-exchange"
chmod 2770 "$BASE/feedback-exchange"

PIDS_SECRET="$BASE/secrets/pids_worker.env"
EVALUATOR_SECRET="$BASE/secrets/hidden_evaluator.env"
if [[ -e "$PIDS_SECRET" || -e "$EVALUATOR_SECRET" ]]; then
  [[ -f "$PIDS_SECRET" && -f "$EVALUATOR_SECRET" ]] || {
    echo "partial split secret state; refusing overwrite" >&2
    exit 3
  }
  [[ "$(stat -c '%a:%U:%G' "$PIDS_SECRET")" == "640:root:apt_pids_worker" ]] || exit 3
  [[ "$(stat -c '%a:%U:%G' "$EVALUATOR_SECRET")" == "640:root:apt_hidden_evaluator" ]] || exit 3
  echo "os_isolation=already-provisioned"
  exit 0
fi
PIDS_WORKER_PASSWORD=""
HIDDEN_EVALUATOR_PASSWORD=""
while IFS='=' read -r key value; do
  case "$key" in
    PIDS_WORKER_PASSWORD) PIDS_WORKER_PASSWORD="$value" ;;
    HIDDEN_EVALUATOR_PASSWORD) HIDDEN_EVALUATOR_PASSWORD="$value" ;;
    "") ;;
    *) echo "unknown combined secret key" >&2; exit 2 ;;
  esac
done <"$COMBINED_SECRET"
[[ "$PIDS_WORKER_PASSWORD" =~ ^[a-f0-9]{64}$ ]] || exit 3
[[ "$HIDDEN_EVALUATOR_PASSWORD" =~ ^[a-f0-9]{64}$ ]] || exit 3
printf 'PIDS_WORKER_PASSWORD=%s\n' "$PIDS_WORKER_PASSWORD" >"$PIDS_SECRET"
printf 'HIDDEN_EVALUATOR_PASSWORD=%s\n' "$HIDDEN_EVALUATOR_PASSWORD" >"$EVALUATOR_SECRET"
chown root:apt_pids_worker "$PIDS_SECRET"
chmod 640 "$PIDS_SECRET"
chown root:apt_hidden_evaluator "$EVALUATOR_SECRET"
chmod 640 "$EVALUATOR_SECRET"

echo "os_isolation=provisioned"
