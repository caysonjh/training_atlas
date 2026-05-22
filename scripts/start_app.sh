#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [ ! -f .env ]; then
  cp .env.example .env
  echo "Created .env from .env.example. Add STRAVA_CLIENT_ID and STRAVA_CLIENT_SECRET before connecting Strava."
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
  ../backend/.venv/bin/uvicorn app.main:app --reload --port 8000
) &
BACKEND_PID=$!

(
  cd frontend
  npm run dev
) &
FRONTEND_PID=$!

if [ "${OPEN_BROWSER:-1}" = "1" ]; then
  sleep 3
  open http://localhost:3000 >/dev/null 2>&1 || true
fi

echo "Atlas is starting: frontend http://localhost:3000, backend http://localhost:8000"
wait "$BACKEND_PID" "$FRONTEND_PID"
