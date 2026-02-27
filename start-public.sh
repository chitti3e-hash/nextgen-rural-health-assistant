#!/bin/bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${VENV_DIR:-$ROOT_DIR/.venv}"
HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8000}"
APP_MODULE="${APP_MODULE:-app.main:app}"
TUNNEL_NAME="${TUNNEL_NAME:-nextgen-health}"
CONFIG_PATH="${CONFIG_PATH:-$HOME/.cloudflared/config.yml}"
SERVER_LOG="${SERVER_LOG:-$ROOT_DIR/server-public.log}"
TUNNEL_LOG="${TUNNEL_LOG:-$ROOT_DIR/tunnel-public.log}"
SKIP_PIP_INSTALL="${SKIP_PIP_INSTALL:-0}"

SERVER_PID=""

cleanup() {
    if [[ -n "$SERVER_PID" ]] && kill -0 "$SERVER_PID" >/dev/null 2>&1; then
        kill "$SERVER_PID" >/dev/null 2>&1 || true
        wait "$SERVER_PID" 2>/dev/null || true
    fi
}
trap cleanup EXIT INT TERM

cd "$ROOT_DIR"

if ! command -v python3 >/dev/null 2>&1; then
    echo "ERROR: python3 not found."
    exit 1
fi

if ! command -v cloudflared >/dev/null 2>&1; then
    echo "ERROR: cloudflared not found. Install it first."
    exit 1
fi

if [[ ! -d "$VENV_DIR" ]]; then
    echo "Creating virtual environment at $VENV_DIR"
    python3 -m venv "$VENV_DIR"
fi

source "$VENV_DIR/bin/activate"

if [[ "$SKIP_PIP_INSTALL" != "1" ]]; then
    echo "Installing/updating Python dependencies..."
    pip install -r requirements.txt
fi

if ! command -v uvicorn >/dev/null 2>&1; then
    echo "ERROR: uvicorn not available in virtualenv. Install requirements first."
    exit 1
fi

if [[ ! -f "$CONFIG_PATH" ]]; then
    echo "ERROR: Cloudflare config not found at $CONFIG_PATH"
    echo "Create named tunnel first with:"
    echo "  cloudflared tunnel login"
    echo "  cloudflared tunnel create $TUNNEL_NAME"
    echo "  cloudflared tunnel route dns $TUNNEL_NAME app.YOURDOMAIN.com"
    exit 1
fi

PUBLIC_HOSTNAME="$(sed -n 's/^[[:space:]]*hostname:[[:space:]]*//p' "$CONFIG_PATH" | head -n 1)"

echo "Starting FastAPI server on http://$HOST:$PORT"
nohup uvicorn "$APP_MODULE" --host "$HOST" --port "$PORT" >"$SERVER_LOG" 2>&1 &
SERVER_PID=$!
sleep 1

if ! kill -0 "$SERVER_PID" >/dev/null 2>&1; then
    echo "ERROR: Server failed to start. Check log:"
    echo "  $SERVER_LOG"
    tail -n 40 "$SERVER_LOG" || true
    exit 1
fi

echo "Server PID: $SERVER_PID"
echo "Server log: $SERVER_LOG"
if [[ -n "$PUBLIC_HOSTNAME" ]]; then
    echo "Expected public URL: https://$PUBLIC_HOSTNAME"
fi
echo "Starting Cloudflare tunnel '$TUNNEL_NAME'..."
echo "Tunnel log: $TUNNEL_LOG"
echo "Press Ctrl+C to stop both server and tunnel."

cloudflared tunnel run "$TUNNEL_NAME" 2>&1 | tee -a "$TUNNEL_LOG"
