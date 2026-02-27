#!/bin/bash

# Helper script to run the NextGen Multilingual AI Health Assistant
# Based on the Quick Start instructions in README.md

set -e # Exit if any command fails

echo "--- Checking environment ---"

if [ ! -d ".venv" ]; then
    echo "Creating virtual environment (.venv)..."
    python3 -m venv .venv
fi

echo "Activating virtual environment..."
source .venv/bin/activate

echo "Installing/Updating dependencies..."
pip install -r requirements.txt

if [ "$1" == "--share" ]; then
    echo "--- Starting Public Share Mode ---"
    echo "Starting local server (HTTP)..."
    # Start uvicorn in background, logging to app.log
    uvicorn app.main:app --port 8000 > app.log 2>&1 &
    SERVER_PID=$!
    
    # Ensure we kill the server when the script exits
    trap "kill $SERVER_PID" EXIT

    echo "Waiting for server to start..."
    sleep 3
    if ! kill -0 $SERVER_PID 2>/dev/null; then
        echo "CRITICAL ERROR: Local server failed to start. Check app.log:"
        cat app.log
        exit 1
    fi

    echo "Creating public tunnel..."
    echo "NOTE: If you see '404 Not Found', try adding '/docs' to the end of the URL."
    echo "Using localhost.run (random URL) for better reliability..."
    ssh -R 80:localhost:8000 nokey@localhost.run
else
    echo "--- Checking SSL Certificates ---"
    if [ ! -f "key.pem" ] || [ ! -f "cert.pem" ]; then
        echo "Generating self-signed certificates for localhost..."
        openssl req -x509 -newkey rsa:4096 -keyout key.pem -out cert.pem -days 365 -nodes -subj '/CN=localhost'
    fi

    echo "--- Starting Server (HTTPS) ---"
    echo "Open https://<YOUR_COMPUTER_IP>:8000 on other devices (LAN/WiFi)"
    uvicorn app.main:app --host 0.0.0.0 --reload --ssl-keyfile key.pem --ssl-certfile cert.pem
fi