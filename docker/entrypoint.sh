#!/bin/bash
set -e

# Activate Debian Python virtual environment
source /app/.venv/bin/activate

# Remove stale Xvfb locks if present
rm -f /tmp/.X99-lock /tmp/.X11-unix/X99

echo "[STARTUP] Starting virtual display Xvfb on DISPLAY :99..."
Xvfb :99 -screen 0 1024x768x16 &
sleep 1

# Ensure Node binary permissions
chmod -R +x /app/web/node_modules/.bin || true

echo "[STARTUP] Launching Python MT5 Web Gateway on Debian..."
python3 -m src.web_gateway &
sleep 2

echo "[STARTUP] Launching Node.js TypeScript Web Dashboard on Port 3496..."
cd /app/web
npm run start
