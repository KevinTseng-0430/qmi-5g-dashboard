#!/bin/sh
set -eu
ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
HOST="${QMI5G_HOST:-0.0.0.0}"
PORT="${QMI5G_PORT:-8000}"
export QMI5G_STATUS_FILE="${QMI5G_STATUS_FILE:-/tmp/qmi5g-dashboard/status.json}"
cd "$ROOT"
exec "$ROOT/.venv/bin/python" -m uvicorn backend.app:app --host "$HOST" --port "$PORT"
