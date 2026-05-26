#!/usr/bin/env bash
set -euo pipefail

: "${CONCIERGE_APP_PASSWORD:?CONCIERGE_APP_PASSWORD is required}"
: "${CONCIERGE_MANAGER_PASSWORD:?CONCIERGE_MANAGER_PASSWORD is required}"

psql \
  --username "$POSTGRES_USER" \
  --dbname "$POSTGRES_DB" \
  -v ON_ERROR_STOP=1 \
  -v app_password="$CONCIERGE_APP_PASSWORD" \
  -v manager_password="$CONCIERGE_MANAGER_PASSWORD" \
  -v db_name="$POSTGRES_DB" <<'EOSQL'
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'concierge_app') THEN
        CREATE ROLE concierge_app LOGIN;
    END IF;
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'concierge_manager') THEN
        CREATE ROLE concierge_manager LOGIN;
    END IF;
END
$$;

ALTER ROLE concierge_app WITH LOGIN PASSWORD :'app_password';
ALTER ROLE concierge_manager WITH LOGIN PASSWORD :'manager_password';
GRANT CONNECT ON DATABASE :"db_name" TO concierge_app, concierge_manager;
GRANT USAGE ON SCHEMA public TO concierge_app, concierge_manager;
EOSQL
