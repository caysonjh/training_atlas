#!/usr/bin/env bash
set -euo pipefail
"$(dirname "$0")/migrate_postgres.sh" "$@"
