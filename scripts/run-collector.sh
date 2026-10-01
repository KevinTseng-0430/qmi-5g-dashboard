#!/bin/sh
set -eu
ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
STATUS_FILE="${QMI5G_STATUS_FILE:-/tmp/qmi5g-dashboard/status.json}"
mkdir -p "$(dirname "$STATUS_FILE")"
exec sudo "$ROOT/.venv/bin/python" "$ROOT/collector/qmi5g_collector.py" --config "$ROOT/config.yaml" --output "$STATUS_FILE" "$@"
