#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-3000}"

port_in_use() {
  local port="$1"
  lsof -nP -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1
}

print_port_owner() {
  local port="$1"
  lsof -nP -iTCP:"$port" -sTCP:LISTEN || true
}

check_free_port() {
  local port="$1"
  local label="$2"
  if port_in_use "$port"; then
    echo "Cannot start Atlas: $label port $port is already in use."
    print_port_owner "$port"
    echo
    return 1
  fi
  return 0
}

if [ ! -f .env ]; then
  cp .env.example .env
  echo "Created .env from .env.example. Add STRAVA_CLIENT_ID and STRAVA_CLIENT_SECRET before connecting Strava."
fi

ports_available=1
check_free_port "$BACKEND_PORT" "Backend" || ports_available=0
check_free_port "$FRONTEND_PORT" "Frontend" || ports_available=0
if [ "$ports_available" = "0" ]; then
  echo "Stop the existing process or choose different ports, then rerun ./scripts/start_app.sh."
  echo "Example: kill <PID from the output above>"
  echo "Alternative: BACKEND_PORT=8010 FRONTEND_PORT=3002 ./scripts/start_app.sh"
  exit 1
fi

if command -v docker >/dev/null 2>&1 && [ "${ATLAS_SKIP_DOCKER:-0}" != "1" ]; then
  docker compose up -d db minio
else
  echo "Skipping Docker startup. Ensure Postgres/PostGIS is already running."
fi

if [ ! -d backend/.venv ]; then
  python3 -m venv backend/.venv
fi

if [ ! -x backend/.venv/bin/uvicorn ]; then
  backend/.venv/bin/pip install -e "backend[dev]"
fi

if [ ! -d frontend/node_modules ]; then
  (cd frontend && npm install)
fi

cleanup() {
  if [ -n "${BACKEND_PID:-}" ]; then kill "$BACKEND_PID" 2>/dev/null || true; fi
  if [ -n "${FRONTEND_PID:-}" ]; then kill "$FRONTEND_PID" 2>/dev/null || true; fi
}
trap cleanup EXIT INT TERM

(
  cd backend
  ../backend/.venv/bin/uvicorn app.main:app --reload --port "$BACKEND_PORT"
) &
BACKEND_PID=$!

(
  cd frontend
  npm run dev -- --port "$FRONTEND_PORT"
) &
FRONTEND_PID=$!

if [ "${OPEN_BROWSER:-1}" = "1" ]; then
  sleep 3
  open "http://localhost:$FRONTEND_PORT" >/dev/null 2>&1 || true
fi

echo "Atlas is starting: frontend http://localhost:$FRONTEND_PORT, backend http://localhost:$BACKEND_PORT"
wait "$BACKEND_PID" "$FRONTEND_PID"
