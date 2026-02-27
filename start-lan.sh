#!/bin/bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${VENV_DIR:-$ROOT_DIR/.venv}"
HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8000}"
APP_MODULE="${APP_MODULE:-app.main:app}"
SKIP_PIP_INSTALL="${SKIP_PIP_INSTALL:-0}"

cd "$ROOT_DIR"

if ! command -v python3 >/dev/null 2>&1; then
    echo "ERROR: python3 not found."
    exit 1
fi

if [[ ! -d "$VENV_DIR" ]]; then
    python3 -m venv "$VENV_DIR"
fi

source "$VENV_DIR/bin/activate"

if [[ "$SKIP_PIP_INSTALL" != "1" ]]; then
    pip install -r requirements.txt
fi

if ! command -v uvicorn >/dev/null 2>&1; then
    echo "ERROR: uvicorn not found in virtualenv."
    exit 1
fi

LAN_IP="$(ipconfig getifaddr en0 2>/dev/null || true)"
if [[ -z "$LAN_IP" ]]; then
    LAN_IP="$(ipconfig getifaddr en1 2>/dev/null || true)"
fi

echo "Starting LAN server on http://$HOST:$PORT"
if [[ -n "$LAN_IP" ]]; then
    echo "Open from other devices: http://$LAN_IP:$PORT"
fi

exec uvicorn "$APP_MODULE" --host "$HOST" --port "$PORT"
