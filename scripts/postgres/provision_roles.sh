#!/usr/bin/env bash
# Provision only the approved least-privilege PostgreSQL roles and grants.
# Requirements: REQ-DB-001..003, REQ-LABEL-001, REQ-REPRO-001.
set -euo pipefail

[[ $EUID -eq 0 ]] || { echo "must run as root on the approved AutoDL host" >&2; exit 2; }
[[ $# -ge 2 ]] || {
  echo "usage: $0 ROOT_ONLY_SECRET_FILE DATABASE [DATABASE ...]" >&2
  exit 2
}

SECRET_FILE="$1"
shift
[[ -f "$SECRET_FILE" && ! -L "$SECRET_FILE" ]] || {
  echo "secret file must be a regular non-symlink file" >&2
  exit 2
}
mode="$(stat -c '%a' "$SECRET_FILE")"
[[ "$mode" == "400" || "$mode" == "600" ]] || {
  echo "secret file mode must be 400 or 600" >&2
  exit 2
}

PIDS_WORKER_PASSWORD=""
HIDDEN_EVALUATOR_PASSWORD=""
while IFS='=' read -r key value; do
  case "$key" in
    PIDS_WORKER_PASSWORD) PIDS_WORKER_PASSWORD="$value" ;;
    HIDDEN_EVALUATOR_PASSWORD) HIDDEN_EVALUATOR_PASSWORD="$value" ;;
    "") ;;
    *) echo "unknown key in secret file" >&2; exit 2 ;;
  esac
done <"$SECRET_FILE"
[[ "$PIDS_WORKER_PASSWORD" =~ ^[a-f0-9]{64}$ ]] || {
  echo "invalid pids worker secret format" >&2
  exit 2
}
[[ "$HIDDEN_EVALUATOR_PASSWORD" =~ ^[a-f0-9]{64}$ ]] || {
  echo "invalid hidden evaluator secret format" >&2
  exit 2
}

databases=("$@")
for database in "${databases[@]}"; do
  [[ "$database" =~ ^[a-z][a-z0-9_]{0,62}$ ]] || {
    echo "invalid database identifier" >&2
    exit 2
  }
done

command -v runuser >/dev/null
runuser -u postgres -- psql -X --set=ON_ERROR_STOP=1 --dbname=postgres >/dev/null <<SQL
DO \$apt_roles\$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'db_admin') THEN
    CREATE ROLE db_admin NOLOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION;
  END IF;
  ALTER ROLE db_admin NOLOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION;

  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'pids_worker') THEN
    CREATE ROLE pids_worker LOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE
      NOREPLICATION PASSWORD '$PIDS_WORKER_PASSWORD';
  ELSE
    ALTER ROLE pids_worker LOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE
      NOREPLICATION PASSWORD '$PIDS_WORKER_PASSWORD';
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'hidden_evaluator') THEN
    CREATE ROLE hidden_evaluator LOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE
      NOREPLICATION PASSWORD '$HIDDEN_EVALUATOR_PASSWORD';
  ELSE
    ALTER ROLE hidden_evaluator LOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE
      NOREPLICATION PASSWORD '$HIDDEN_EVALUATOR_PASSWORD';
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'agent_controller') THEN
    CREATE ROLE agent_controller NOLOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE
      NOREPLICATION;
  END IF;
  ALTER ROLE agent_controller NOLOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE
    NOREPLICATION;
END
\$apt_roles\$;
GRANT db_admin TO postgres;
SQL

for database in "${databases[@]}"; do
  exists="$(runuser -u postgres -- psql -X -Atqc \
    "SELECT 1 FROM pg_database WHERE datname = '$database'" postgres)"
  [[ "$exists" == "1" ]] || { echo "approved database is absent: $database" >&2; exit 3; }
  runuser -u postgres -- psql -X --set=ON_ERROR_STOP=1 --dbname="$database" >/dev/null <<SQL
REVOKE CONNECT ON DATABASE "$database" FROM PUBLIC;
REVOKE ALL PRIVILEGES ON DATABASE "$database" FROM pids_worker, hidden_evaluator, agent_controller;
GRANT CONNECT ON DATABASE "$database" TO pids_worker;
REVOKE ALL PRIVILEGES ON SCHEMA public FROM pids_worker, hidden_evaluator, agent_controller;
GRANT USAGE ON SCHEMA public TO pids_worker;
REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA public FROM PUBLIC;
REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA public
  FROM pids_worker, hidden_evaluator, agent_controller;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO pids_worker;
SQL
  printf 'provisioned_database=%s\n' "$database"
done
echo "role_policy=provisioned"
