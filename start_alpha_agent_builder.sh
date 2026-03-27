#!/usr/bin/env bash

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$PROJECT_DIR/backend"
FRONTEND_DIR="$PROJECT_DIR/frontend"
BACKEND_VENV="$BACKEND_DIR/.venv"

BACKEND_HOST="${BACKEND_HOST:-127.0.0.1}"
BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_HOST="${FRONTEND_HOST:-127.0.0.1}"
FRONTEND_PORT="${FRONTEND_PORT:-5173}"

BACKEND_PID=""
FRONTEND_PID=""

cleanup() {
  if [[ -n "$BACKEND_PID" ]] && kill -0 "$BACKEND_PID" 2>/dev/null; then
    kill "$BACKEND_PID" 2>/dev/null || true
  fi

  if [[ -n "$FRONTEND_PID" ]] && kill -0 "$FRONTEND_PID" 2>/dev/null; then
    kill "$FRONTEND_PID" 2>/dev/null || true
  fi
}

trap cleanup EXIT INT TERM

require_command() {
  local command_name="$1"
  if ! command -v "$command_name" >/dev/null 2>&1; then
    echo "Missing required command: $command_name"
    exit 1
  fi
}

require_command python3
require_command npm

echo "Project directory: $PROJECT_DIR"

if [[ ! -d "$BACKEND_VENV" ]]; then
  echo "Creating backend virtual environment..."
  python3 -m venv "$BACKEND_VENV"
fi

echo "Installing backend dependencies..."
"$BACKEND_VENV/bin/pip" install -r "$BACKEND_DIR/requirements.txt" >/dev/null

if [[ ! -d "$FRONTEND_DIR/node_modules" ]]; then
  echo "Installing frontend dependencies..."
  (
    cd "$FRONTEND_DIR"
    npm install >/dev/null
  )
fi

echo "Starting backend on http://$BACKEND_HOST:$BACKEND_PORT ..."
(
  cd "$PROJECT_DIR"
  "$BACKEND_VENV/bin/python" -m uvicorn backend.main:app --host "$BACKEND_HOST" --port "$BACKEND_PORT" --reload
) &
BACKEND_PID=$!

echo "Starting frontend on http://$FRONTEND_HOST:$FRONTEND_PORT ..."
(
  cd "$FRONTEND_DIR"
  npm run dev -- --host "$FRONTEND_HOST" --port "$FRONTEND_PORT"
) &
FRONTEND_PID=$!

echo
echo "Alpha Agent Builder is starting."
echo "Backend:  http://$BACKEND_HOST:$BACKEND_PORT"
echo "Frontend: http://$FRONTEND_HOST:$FRONTEND_PORT"
echo "Press Ctrl+C to stop both services."
echo

wait "$BACKEND_PID" "$FRONTEND_PID"
