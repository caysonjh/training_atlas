#!/usr/bin/env bash
set -euo pipefail

: "${LOCAL_DATABASE_URL:?Set LOCAL_DATABASE_URL to the source PostgreSQL URL}"
: "${PRODUCTION_DATABASE_URL:?Set PRODUCTION_DATABASE_URL to the destination PostgreSQL URL}"

DUMP_FILE="${1:-atlas-local.dump}"
LOCAL_PG_URL="${LOCAL_DATABASE_URL/postgresql+psycopg:\/\//postgresql:\/\/}"
PRODUCTION_PG_URL="${PRODUCTION_DATABASE_URL/postgresql+psycopg:\/\//postgresql:\/\/}"

pg_dump --format=custom --no-owner --no-privileges "$LOCAL_PG_URL" --file "$DUMP_FILE"
pg_restore --clean --if-exists --no-owner --no-privileges --dbname "$PRODUCTION_PG_URL" "$DUMP_FILE"
