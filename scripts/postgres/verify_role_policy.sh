#!/usr/bin/env bash
# Verify live PostgreSQL role separation without reading private data.
# Requirements: REQ-DB-001..003, REQ-LABEL-001, REQ-REPRO-001.
set -euo pipefail

[[ $EUID -eq 0 ]] || exit 2
[[ $# -ge 2 ]] || exit 2
SECRET_FILE="$1"
shift
[[ -f "$SECRET_FILE" && ! -L "$SECRET_FILE" ]] || exit 2

PIDS_WORKER_PASSWORD=""
HIDDEN_EVALUATOR_PASSWORD=""
while IFS='=' read -r key value; do
  case "$key" in
    PIDS_WORKER_PASSWORD) PIDS_WORKER_PASSWORD="$value" ;;
    HIDDEN_EVALUATOR_PASSWORD) HIDDEN_EVALUATOR_PASSWORD="$value" ;;
    "") ;;
    *) exit 2 ;;
  esac
done <"$SECRET_FILE"
[[ "$PIDS_WORKER_PASSWORD" =~ ^[a-f0-9]{64}$ ]] || exit 2
[[ "$HIDDEN_EVALUATOR_PASSWORD" =~ ^[a-f0-9]{64}$ ]] || exit 2

role_state="$(runuser -u postgres -- psql -X -Atqc "
SELECT rolname || ':' || rolcanlogin || ':' || rolsuper || ':' || rolcreatedb || ':' || rolcreaterole
FROM pg_roles
WHERE rolname IN ('db_admin','pids_worker','hidden_evaluator','agent_controller')
ORDER BY rolname" postgres)"
expected_role_state="agent_controller:false:false:false:false
db_admin:false:false:false:false
hidden_evaluator:true:false:false:false
pids_worker:true:false:false:false"
[[ "$role_state" == "$expected_role_state" ]] || {
  echo "role attributes violate policy" >&2
  exit 3
}

for database in "$@"; do
  [[ "$database" =~ ^[a-z][a-z0-9_]{0,62}$ ]] || exit 2
  privilege_state="$(runuser -u postgres -- psql -X -Atqc "
SELECT
  has_database_privilege('pids_worker', current_database(), 'CONNECT') || ':' ||
  has_database_privilege('hidden_evaluator', current_database(), 'CONNECT') || ':' ||
  has_database_privilege('agent_controller', current_database(), 'CONNECT') || ':' ||
  bool_and(has_table_privilege('pids_worker', quote_ident(schemaname)||'.'||quote_ident(tablename), 'SELECT')) || ':' ||
  bool_or(
    has_table_privilege('pids_worker', quote_ident(schemaname)||'.'||quote_ident(tablename), 'INSERT') OR
    has_table_privilege('pids_worker', quote_ident(schemaname)||'.'||quote_ident(tablename), 'UPDATE') OR
    has_table_privilege('pids_worker', quote_ident(schemaname)||'.'||quote_ident(tablename), 'DELETE') OR
    has_table_privilege('pids_worker', quote_ident(schemaname)||'.'||quote_ident(tablename), 'TRUNCATE') OR
    has_table_privilege('pids_worker', quote_ident(schemaname)||'.'||quote_ident(tablename), 'REFERENCES') OR
    has_table_privilege('pids_worker', quote_ident(schemaname)||'.'||quote_ident(tablename), 'TRIGGER')
  ) || ':' ||
  bool_or(has_table_privilege('hidden_evaluator', quote_ident(schemaname)||'.'||quote_ident(tablename), 'SELECT')) || ':' ||
  bool_or(has_table_privilege('agent_controller', quote_ident(schemaname)||'.'||quote_ident(tablename), 'SELECT')) || ':' ||
  count(*)
FROM pg_tables WHERE schemaname='public'" "$database")"
  [[ "$privilege_state" == "true:false:false:true:false:false:false:4" ]] || {
    echo "database privilege policy failed: $database" >&2
    exit 3
  }
  PGPASSWORD="$PIDS_WORKER_PASSWORD" psql -X -h 127.0.0.1 -U pids_worker \
    -d "$database" -Atqc "SELECT 1 FROM public.event_table LIMIT 1" >/dev/null
  if PGPASSWORD="$HIDDEN_EVALUATOR_PASSWORD" psql -X -h 127.0.0.1 \
    -U hidden_evaluator -d "$database" -Atqc "SELECT 1" >/dev/null 2>&1; then
    echo "hidden evaluator unexpectedly connected to provenance database" >&2
    exit 3
  fi
  printf 'verified_database=%s\n' "$database"
done
echo "role_policy=verified"
