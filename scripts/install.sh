#!/bin/sh
set -eu
ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
python3 -m venv "$ROOT/.venv"
"$ROOT/.venv/bin/pip" install --upgrade pip
"$ROOT/.venv/bin/pip" install -r "$ROOT/requirements.txt"
sudo mkdir -p /tmp/qmi5g-dashboard
sudo chmod 777 /tmp/qmi5g-dashboard
echo "Install complete."
