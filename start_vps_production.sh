#!/bin/bash
# Production All-in-One Runner for ManusTrade on Debian VPS
set -e

echo "[STEP 1] Starting Virtual Screen Xvfb..."
export DISPLAY=:99
export WINEARCH=win64
export WINEPREFIX="/root/.wine"
export WINEDEBUG=-all
rm -f /tmp/.X99-lock /tmp/.X11-unix/X99 || true
Xvfb :99 -screen 0 1024x768x16 &
sleep 2

echo "[STEP 2] Ensuring MT5 Windows Terminal is running in Wine..."
cd "/root/.wine/drive_c/Program Files/MetaTrader 5"
wine terminal64.exe /login:108074548 "/password:9200Eazer." "/server:XMGlobal-MT5 5" &
sleep 5

echo "[STEP 3] Launching Python MT5 Real Gateway under Wine..."
cd /root/discord_aibot/ManusTrade
wine "/root/.wine/drive_c/Python311/python.exe" -m src.web_gateway &
sleep 3

echo "[STEP 4] Launching Web Dashboard on port 3496..."
cd /root/discord_aibot/ManusTrade/web
npm run start
